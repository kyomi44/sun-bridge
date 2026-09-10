"""Offline workspace/CLI checks using only temporary private synthetic data."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunbridge.__main__ import main
from sunbridge.events import parse_message
from sunbridge.registry import integration_registry, render_integrations
from sunbridge.validation import ROOT
from sunbridge.workspace import create_workspace, doctor, run_workspace, validate_workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        private = ROOT / "private"
        private.mkdir(mode=0o700, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-workspace-", dir=private)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.network = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline workspace test attempted a network request"))
        self.opened = self.network.start()
        self.addCleanup(self.network.stop)
        self.sockets = patch("socket.create_connection", side_effect=AssertionError("Offline workspace test attempted a socket connection"))
        self.sockets.start()
        self.addCleanup(self.sockets.stop)

    def cli(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(list(arguments))
        return status, out.getvalue(), err.getvalue()

    def setup(self, mode="demo", name="workspace"):
        path = create_workspace(self.root / name, mode)
        return path, json.loads(path.read_text(encoding="utf-8"))

    def save(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def enable_test_llm(self, path, config):
        llm_path = path.parent / "llm-config.json"
        self.save(llm_path, {"protocol": "openai_compatible", "base_url": "https://provider.example.invalid/v1",
                             "model": "synthetic-model", "api_key_env": "SUNBRIDGE_TEST_KEY",
                             "max_output_tokens": 1200, "token_parameter": "max_completion_tokens"})
        config["llm_config_path"] = str(llm_path)
        self.save(path, config)

    def prepare_test_pipedrive(self, path, config):
        mapping_path = path.parent / "pipedrive-mapping.json"
        # Made-up local field codes. No real account's metadata is used.
        self.save(mapping_path, {"schema_version": 1, "ahj_field": "org_id",
                                 "permit_fields": ["a" * 40],
                                 "address_field": "b" * 40, "customer_name_field": None,
                                 "ahj_map": {"101": "example-training-county"}})
        config["messages_path"] = "examples/messages.json"
        config["crm"] = {"adapter": "pipedrive", "mapping_path": str(mapping_path),
                          "deal_ids": [101], "token_file": None}
        self.save(path, config)

    def test_cli_no_account_setup_doctor_run_produces_private_review(self):
        directory = self.root / "first-run"
        status, stdout, stderr = self.cli("setup", "--output", str(directory))
        self.assertEqual(status, 0, stderr)
        self.assertIn("No accounts connected", stdout)
        path = directory / "sunbridge.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(config["llm_config_path"])
        self.assertEqual(config["crm"]["adapter"], "json_file")
        self.assertTrue((directory / "START-HERE.md").is_file())
        status, stdout, stderr = self.cli("doctor", "--config", str(path))
        self.assertEqual(status, 0, stderr)
        self.assertIn("Disabled", stdout)
        with patch("webbrowser.open") as browser:
            status, stdout, stderr = self.cli("run", "--config", str(path))
        self.assertEqual(status, 0, stderr)
        browser.assert_not_called()
        output = ROOT / config["output_dir"]
        self.assertTrue(output.is_relative_to(self.root))
        self.assertEqual({p.name for p in output.iterdir()}, {"review.json", "review.md", "review.html"})
        report = json.loads((output / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["input_messages"], 14)
        self.assertEqual(report["summary"]["duplicates_skipped"], 1)
        self.assertEqual(report["summary"]["match_results"], {"matched": 9, "unmatched": 3, "ambiguous": 1})
        self.assertEqual(report["crm_writes"], 0)
        self.assertTrue(all(row["event"]["review_required"] for row in report["items"]))
        self.assertIn("Sun Bridge", (output / "review.html").read_text(encoding="utf-8"))
        for file in output.iterdir():
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.opened.assert_not_called()

    def test_setup_refuses_to_overwrite_or_partially_replace_existing_files(self):
        path, _ = self.setup()
        before = {p.name: p.read_bytes() for p in path.parent.iterdir()}
        with self.assertRaisesRegex(ValueError, "not empty"):
            create_workspace(path.parent, "pipedrive")
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.parent.iterdir()})
        status, _, error = self.cli("setup", "--output", str(path.parent))
        self.assertEqual(status, 1)
        self.assertIn("not empty", error)

    def test_private_path_guards_reject_public_root_and_symlink_aliases(self):
        for directory in (ROOT, ROOT / "private", ROOT / "profiles", ROOT / "private/../profiles"):
            with self.subTest(directory=str(directory)), self.assertRaises(ValueError):
                create_workspace(directory)
        actual = self.root / "actual"
        actual.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            create_workspace(alias / "setup")
        self.assertEqual(list(actual.iterdir()), [])
        path, config = self.setup()
        config["output_dir"] = "profiles/not-a-private-output"
        with self.assertRaises(ValueError):
            validate_workspace(config)

    def test_doctor_reports_missing_or_invalid_inputs_without_network(self):
        path, baseline = self.setup()
        empty = self.root / "empty.json"
        self.save(empty, [])
        bad_messages = self.root / "unknown-ahj.json"
        self.save(bad_messages, [{"message_id": "synthetic@example.invalid", "ahj_id": "unknown-profile"}])
        variants = [
            ({"messages_path": str(self.root / "missing.json")}, "messages"),
            ({"messages_path": str(empty)}, "messages"),
            ({"messages_path": str(bad_messages)}, "messages"),
            ({"max_messages": 1}, "messages"),
            ({"profiles_path": str(self.root / "missing-profiles")}, "profiles"),
            ({"crm": {"adapter": "json_file", "permits_path": str(empty)}}, "permit records"),
        ]
        for change, failing_check in variants:
            with self.subTest(change=change):
                config = {**copy.deepcopy(baseline), **change}
                self.save(path, config)
                result = doctor(path)
                self.assertFalse(result["ready"])
                checks = {c["name"]: c for c in result["checks"]}
                self.assertEqual(checks[failing_check]["status"], "needs_attention")
                self.assertEqual(result["network_requests"], 0)
                with self.assertRaisesRegex(ValueError, "needs attention"):
                    run_workspace(path)
        self.assertFalse((path.parent / "review").exists())
        self.opened.assert_not_called()

    def test_pipedrive_mapping_and_credentials_need_attention_offline(self):
        path, config = self.setup("pipedrive")
        config["messages_path"] = "examples/messages.json"
        config["crm"]["mapping_path"] = str(self.root / "missing-mapping.json")
        self.save(path, config)
        result = doctor(path)
        checks = {c["name"]: c for c in result["checks"]}
        self.assertEqual(checks["Pipedrive mapping and deal selection"]["status"], "needs_attention")
        self.assertEqual(checks["Pipedrive credential"]["status"], "needs_attention")
        self.prepare_test_pipedrive(path, config)
        mapping_path = Path(config["crm"]["mapping_path"])
        original = json.loads(mapping_path.read_text())
        with patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "synthetic-token"}):
            for ahj_map in ({}, {"101": "unknown-profile"}):
                self.save(mapping_path, {**original, "ahj_map": ahj_map})
                self.assertFalse(doctor(path)["ready"])
            self.save(mapping_path, original)
            config["crm"]["deal_ids"] = []
            self.save(path, config)
            self.assertFalse(doctor(path)["ready"])
        self.opened.assert_not_called()

    def test_unsupported_adapter_and_unbounded_batch_are_rejected(self):
        _, config = self.setup()
        for adapter in ("hubspot", "salesforce", "zoho"):
            candidate = {**config, "crm": {"adapter": adapter}}
            with self.subTest(adapter=adapter), self.assertRaisesRegex(ValueError, "implemented"):
                validate_workspace(candidate)
        for size in (0, 101, True, "100"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_workspace({**config, "max_messages": size})

    def test_llm_consent_is_required_before_provider_or_crm_calls(self):
        for mode in ("demo", "pipedrive"):
            with self.subTest(mode=mode):
                path, config = self.setup(mode, name="consent-" + mode)
                if mode == "pipedrive":
                    self.prepare_test_pipedrive(path, config)
                self.enable_test_llm(path, config)
                with patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "synthetic-token"}), patch("sunbridge.llm.LLMClient") as provider, patch("sunbridge.crm.import_deal_permits") as crm:
                    readiness = doctor(path)
                    self.assertTrue(readiness["ready"], readiness)
                    self.assertEqual(readiness["llm_target"], "https://provider.example.invalid/v1")
                    with self.assertRaisesRegex(ValueError, "allow-llm-data-transfer"):
                        run_workspace(path)
                    provider.assert_not_called()
                    crm.assert_not_called()
                self.assertFalse((path.parent / "review").exists())
        self.opened.assert_not_called()

    def test_explicit_llm_consent_uses_mocked_extraction_only(self):
        path, config = self.setup()
        self.enable_test_llm(path, config)
        with patch("sunbridge.llm.LLMClient") as provider:
            provider.return_value.extract.side_effect = parse_message
            result = run_workspace(path, allow_data_transfer=True)
            self.assertTrue(provider.call_args.kwargs["allow_data_transfer"])
            self.assertTrue(provider.return_value.extract.called)
        self.assertTrue(result["llm_enabled"])
        self.assertEqual(result["crm_writes"], 0)
        self.opened.assert_not_called()

    def test_cli_analyze_and_connection_check_require_llm_consent(self):
        path, config = self.setup()
        self.enable_test_llm(path, config)
        with patch("sunbridge.llm.LLMClient") as provider:
            status, _, error = self.cli("analyze", "--messages", str(ROOT / "examples/messages.json"),
                                        "--permits", str(ROOT / "examples/permits.json"),
                                        "--llm-config", config["llm_config_path"], "--output", str(self.root / "analysis"))
            self.assertEqual(status, 1)
            self.assertIn("allow-llm-data-transfer", error)
            provider.assert_not_called()
        status, _, error = self.cli("llm-check", "--config", config["llm_config_path"])
        self.assertEqual(status, 1)
        self.assertIn("allow-llm-data-transfer", error)
        self.assertFalse((self.root / "analysis").exists())
        self.opened.assert_not_called()


class IntegrationRegistryTests(unittest.TestCase):
    def test_current_claims_match_capabilities_and_have_real_source_and_tests(self):
        registry = integration_registry()
        by_id = {entry["id"]: entry for entry in registry["crms"]}
        self.assertEqual(by_id["json_file"]["status"], "available")
        self.assertFalse(by_id["json_file"]["organization_discovery"])
        self.assertEqual(by_id["pipedrive"]["status"], "experimental")
        self.assertTrue(by_id["pipedrive"]["organization_discovery"])
        self.assertTrue(by_id["pipedrive"]["permit_reads"])
        for entry in registry["crms"]:
            self.assertIs(entry["crm_writes"], False)
            if entry["status"] != "planned":
                self.assertTrue(entry["implementation"])
                self.assertTrue(entry["tests"])
                for filename in entry["implementation"] + entry["tests"]:
                    self.assertTrue((ROOT / filename).is_file(), filename)
        for name in ("hubspot", "salesforce", "zoho"):
            self.assertEqual(by_id[name]["status"], "planned")
            self.assertFalse(by_id[name]["permit_reads"])
            self.assertFalse(by_id[name]["organization_discovery"])
            self.assertEqual(by_id[name]["implementation"], [])
        self.assertIn("read-only", render_integrations())

    def test_cli_json_registry_matches_the_public_registry(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["integrations", "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue()), integration_registry())


if __name__ == "__main__":
    unittest.main()
