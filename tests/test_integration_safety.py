"""Offline end-to-end consent, preflight, and LLM review integration checks."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from sunbridge.__main__ import main
from sunbridge.llm import LLMError, PROMPT_VERSION
from sunbridge.validation import ROOT, load_profiles
from sunbridge.workspace import doctor, llm_parser, run_workspace


class FakeResponse:
    def __init__(self, value):
        self.data = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.data[:size]

    def getcode(self):
        return 200


class IntegrationSafetyTests(unittest.TestCase):
    def setUp(self):
        private = ROOT / "private"
        private.mkdir(mode=0o700, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-integration-safety-", dir=private)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profiles = load_profiles(ROOT / "profiles")
        self.ahj = "example-training-county"
        self.message = {
            "message_id": "integration-demo@example.invalid", "ahj_id": self.ahj,
            "sender": "notifications@example.invalid", "subject": "Permit DEMO-SOLAR-001 issued",
            "body": "Permit DEMO-SOLAR-001 issued", "received_at": "2026-01-01T12:00:00Z",
        }
        self.permits = [{"deal_id": "local-only-deal-701", "ahj_id": self.ahj,
                         "permit_id": "DEMO-SOLAR-001", "service_address": "100 Example Way, Unit A, Example City, ZZ 00000",
                         "customer_name": "Synthetic Person Not Sent"}]
        self.llm_config = {"protocol": "openai_compatible", "base_url": "https://provider.example.invalid/v1",
                           "model": "fictional-integration-model", "api_key_env": "SUNBRIDGE_INTEGRATION_TEST_KEY",
                           "max_output_tokens": 1200}
        self.messages_path = self.save(self.root / "messages.json", [self.message])
        self.permits_path = self.save(self.root / "permits.json", self.permits)
        self.llm_path = self.save(self.root / "provider.json", self.llm_config)
        self.config = {
            "schema_version": 1, "messages_path": str(self.messages_path), "profiles_path": str(ROOT / "profiles"),
            "crm": {"adapter": "json_file", "permits_path": str(self.permits_path)},
            "llm_config_path": str(self.llm_path), "output_dir": str(self.root / "review"), "max_messages": 100,
        }
        self.config_path = self.save(self.root / "sunbridge.json", self.config)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        network = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected real network request"))
        self.network = network.start()
        self.addCleanup(network.stop)
        sockets = patch("socket.create_connection", side_effect=AssertionError("Unexpected socket connection"))
        self.sockets = sockets.start()
        self.addCleanup(sockets.stop)

    @staticmethod
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    @staticmethod
    def cli(*arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(arguments))
        return code, out.getvalue(), err.getvalue()

    def analyze(self, output, *, messages=None, permits=None, llm=None, profiles=None):
        return self.cli("analyze", "--messages", str(messages or self.messages_path),
                        "--permits", str(permits or self.permits_path),
                        "--profiles", str(profiles or ROOT / "profiles"),
                        "--llm-config", str(llm or self.llm_path), "--allow-llm-data-transfer",
                        "--output", str(output))

    def test_analyze_refuses_message_permit_and_llm_config_collisions_before_extraction(self):
        for source_name, content in (("messages", [self.message]), ("permits", self.permits), ("llm", self.llm_config)):
            with self.subTest(source=source_name):
                output = self.root / ("analyze-" + source_name)
                collision = self.save(output / "review.json", content)
                original = collision.read_bytes()
                with patch("sunbridge.llm.LLMClient.extract") as extraction:
                    code, _, error = self.analyze(output, **{source_name: collision})
                self.assertEqual(code, 1)
                self.assertIn("overwrite an input or configuration", error)
                extraction.assert_not_called()
                self.assertEqual(collision.read_bytes(), original)
                self.assertFalse((output / "review.md").exists())
        self.network.assert_not_called()

    def test_analyze_refuses_output_nested_inside_profiles_before_extraction(self):
        profiles = self.root / "private-profiles"
        self.save(profiles / "example.json", self.profiles[self.ahj])
        with patch("sunbridge.llm.LLMClient.extract") as extraction:
            code, _, error = self.analyze(profiles / "reports", profiles=profiles)
        self.assertEqual(code, 1)
        self.assertIn("overwrite an input or configuration", error)
        extraction.assert_not_called()
        self.assertFalse((profiles / "reports").exists())

    def test_workspace_refuses_input_and_both_config_collisions_before_network(self):
        for source_name in ("messages", "permits", "llm", "workspace"):
            with self.subTest(source=source_name):
                config = copy.deepcopy(self.config)
                output = self.root / ("workspace-" + source_name)
                collision = output / "review.json"
                config["output_dir"] = str(output)
                config_path = self.root / (source_name + "-workspace.json")
                if source_name == "messages":
                    self.save(collision, [self.message])
                    config["messages_path"] = str(collision)
                elif source_name == "permits":
                    self.save(collision, self.permits)
                    config["crm"]["permits_path"] = str(collision)
                elif source_name == "llm":
                    self.save(collision, self.llm_config)
                    config["llm_config_path"] = str(collision)
                else:
                    config_path = collision
                self.save(config_path, config)
                original = collision.read_bytes()
                with patch("sunbridge.llm.LLMClient.extract") as extraction, patch("sunbridge.crm.import_deal_permits") as crm:
                    readiness = doctor(config_path)
                    self.assertFalse(readiness["ready"])
                    check = next(item for item in readiness["checks"] if item["name"] == "private outputs")
                    self.assertEqual(check["status"], "needs_attention")
                    with self.assertRaisesRegex(ValueError, "needs attention"):
                        run_workspace(config_path, allow_data_transfer=True)
                    extraction.assert_not_called()
                    crm.assert_not_called()
                self.assertEqual(collision.read_bytes(), original)
                self.assertFalse((output / "review.html").exists())
        self.network.assert_not_called()

    def test_report_leaf_symlinks_refused_before_analyze_or_workspace_network(self):
        protected = self.root / "protected-source.txt"
        protected.write_text("preserve source", encoding="utf-8")
        for mode in ("analyze", "workspace"):
            for name in ("review.json", "review.md", "review.html"):
                with self.subTest(mode=mode, name=name):
                    output = self.root / (mode + "-" + name.replace(".", "-"))
                    output.mkdir()
                    link = output / name
                    link.symlink_to(protected)
                    with patch("sunbridge.llm.LLMClient.extract") as extraction, patch("sunbridge.crm.import_deal_permits") as crm:
                        if mode == "analyze":
                            code, _, error = self.analyze(output)
                            self.assertEqual(code, 1)
                            self.assertIn("symbolic", error)
                        else:
                            config = {**self.config, "output_dir": str(output)}
                            self.save(self.config_path, config)
                            self.assertFalse(doctor(self.config_path)["ready"])
                            with self.assertRaisesRegex(ValueError, "needs attention"):
                                run_workspace(self.config_path, allow_data_transfer=True)
                        extraction.assert_not_called()
                        crm.assert_not_called()
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(protected.read_text(), "preserve source")
                    self.assertEqual([p.name for p in output.iterdir()], [name])
        self.network.assert_not_called()

    def test_pipedrive_mapping_or_credential_collision_refused_before_any_account_call(self):
        mapping = {"schema_version": 1, "ahj_field": "org_id", "permit_fields": ["a" * 40],
                   "address_field": "b" * 40, "customer_name_field": None, "ahj_map": {"101": self.ahj}}
        for source_name in ("mapping", "credential"):
            with self.subTest(source=source_name):
                output = self.root / ("pipedrive-" + source_name)
                output.mkdir()
                mapping_path = output / "permits.json" if source_name == "mapping" else self.root / "pipedrive-mapping.json"
                self.save(mapping_path, mapping)
                token_path = None
                if source_name == "credential":
                    token_path = output / "review.md"
                    token_path.write_text("fictional-token", encoding="utf-8")
                config = {**self.config, "output_dir": str(output), "crm": {
                    "adapter": "pipedrive", "mapping_path": str(mapping_path), "deal_ids": [101],
                    "token_file": str(token_path) if token_path else None,
                }}
                config_path = self.save(self.root / (source_name + "-pipedrive.json"), config)
                with patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "fictional-token"}), patch("sunbridge.crm.import_deal_permits") as crm, patch("sunbridge.crm.DealClient.fields") as fields, patch("sunbridge.llm.LLMClient.extract") as extraction:
                    self.assertFalse(doctor(config_path)["ready"])
                    with self.assertRaisesRegex(ValueError, "needs attention"):
                        run_workspace(config_path, allow_data_transfer=True)
                    crm.assert_not_called()
                    fields.assert_not_called()
                    extraction.assert_not_called()
                if token_path:
                    self.assertEqual(token_path.read_text(), "fictional-token")
                self.assertEqual(json.loads(mapping_path.read_text()), mapping)

    def test_hard_link_to_input_is_refused_before_extraction(self):
        output = self.root / "hard-linked-input"
        output.mkdir()
        os.link(self.messages_path, output / "review.json")
        original = self.messages_path.read_bytes()
        with patch("sunbridge.llm.LLMClient.extract") as extraction:
            code, _, error = self.analyze(output)
        self.assertEqual(code, 1)
        self.assertIn("linked to an input", error)
        extraction.assert_not_called()
        self.assertEqual(self.messages_path.read_bytes(), original)

    def test_llm_parser_requires_literal_true_before_config_or_client_access(self):
        for consent in (False, "false", 1, None):
            with self.subTest(consent=consent):
                with patch("sunbridge.workspace.read_json_file") as read, patch("sunbridge.llm.LLMClient") as client:
                    with self.assertRaisesRegex(ValueError, "allow-llm-data-transfer"):
                        llm_parser(self.llm_path, consent)
                    read.assert_not_called()
                    client.assert_not_called()

    def test_transport_error_retains_safe_provenance_without_rule_fallback(self):
        parser = llm_parser(self.llm_path, True)
        with patch("sunbridge.llm.LLMClient.extract", side_effect=LLMError("fictional-sensitive-response-detail", "llm_http_error")), patch("sunbridge.events.parse_message", side_effect=AssertionError("Rule fallback is not permitted")):
            event = parser(self.message, self.profiles[self.ahj])
        self.assertEqual(event["event_type"], "unknown")
        self.assertEqual(event["scope"], "unknown")
        self.assertIsNone(event["permit_id"])
        self.assertIsNone(event["rule_id"])
        self.assertTrue(event["review_required"])
        self.assertEqual(event["ahj_id"], self.ahj)
        self.assertEqual(event["llm"], {"protocol": "openai_compatible", "provider": "provider.example.invalid",
                                       "model": "fictional-integration-model", "prompt_version": PROMPT_VERSION})
        self.assertIn("llm_http_error", event["issues"])
        self.assertIn("llm_request_failed_no_fallback", event["issues"])
        self.assertNotIn("ahj_mismatch_or_missing", event["issues"])
        self.assertNotIn("fictional-sensitive-response-detail", json.dumps(event))
        self.network.assert_not_called()

    def test_mocked_provider_body_evidence_runs_through_separate_local_matching(self):
        source = {**self.message, "subject": "Current application update",
                  "body": "Current update: Permit DEMO-SOLAR-001 issued"}
        self.save(self.messages_path, [source])
        proposed = {"event_type": "permit_issued", "scope": "permit", "permit_id": "DEMO-SOLAR-001",
                    "address": None, "evidence": {"field": "body", "text": "Permit DEMO-SOLAR-001 issued"}}
        response = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(proposed)}}]}
        opener = Mock()
        opener.open.return_value = FakeResponse(response)
        with patch.dict(os.environ, {"SUNBRIDGE_INTEGRATION_TEST_KEY": "fictional-key"}), patch("sunbridge.llm.urllib.request.build_opener", return_value=opener):
            result = run_workspace(self.config_path, allow_data_transfer=True)
        self.assertTrue(result["llm_enabled"])
        self.assertEqual(result["crm_writes"], 0)
        output = Path(self.config["output_dir"])
        report = json.loads((output / "review.json").read_text(encoding="utf-8"))
        row = report["items"][0]
        self.assertEqual(row["event"]["evidence"], proposed["evidence"])
        self.assertEqual(row["event"]["event_type"], "permit_issued")
        self.assertTrue(row["event"]["review_required"])
        self.assertIsNone(row["event"]["observed_event_time"])
        self.assertEqual(row["match"]["status"], "matched")
        self.assertEqual(row["match"]["method"], "ahj_permit_id")
        self.assertEqual(row["match"]["deal_id"], "local-only-deal-701")
        self.assertEqual(row["decision"], "needs_operator_review")
        self.assertIn("Evidence (body):", (output / "review.md").read_text(encoding="utf-8"))
        self.assertIn("Source evidence · body", (output / "review.html").read_text(encoding="utf-8"))
        sent = json.loads(opener.open.call_args.args[0].data)
        self.assertNotIn("local-only-deal-701", json.dumps(sent))
        self.assertNotIn("Synthetic Person Not Sent", json.dumps(sent))
        self.assertNotIn("fictional-key", json.dumps(sent))
        self.assertNotIn("tools", sent)
        opener.open.assert_called_once()
        self.network.assert_not_called()
        self.sockets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
