"""Offline readiness checks for Pipedrive setup; no files or network required."""

import contextlib
import io
import os
import shlex
import unittest
from pathlib import Path
from unittest.mock import patch

from permitkit import __main__ as cli
from permitkit import workspace
from permitkit.crm import validate_mapping


PROFILE = "example-training-county"
PERMIT, ADDRESS = (letter * 40 for letter in "ab")


def mapping(**changes):
    return {"schema_version": 1, "ahj_field": "org_id", "permit_fields": [PERMIT],
            "address_field": ADDRESS, "customer_name_field": None,
            "ahj_map": {"991": PROFILE}, **changes}


def config():
    return {"schema_version": 1, "messages_path": "synthetic-messages.json", "profiles_path": "profiles",
            "crm": {"adapter": "pipedrive", "mapping_path": "synthetic-mapping.json", "deal_ids": [101], "token_file": None},
            "llm_config_path": None, "output_dir": "private/synthetic-test-unused", "max_messages": 100}


class CRMReadinessTests(unittest.TestCase):
    def test_template_shape_is_allowed_but_not_live_ready(self):
        value = mapping(permit_fields=["REPLACE_WITH_EXACT_PERMIT_FIELD_CODE"])
        self.assertEqual(validate_mapping(value), value)
        with self.assertRaises(ValueError):
            workspace.ready_pipedrive_mapping(value, {PROFILE: {}})
        empty = mapping(ahj_map={})
        self.assertEqual(validate_mapping(empty), empty)
        with self.assertRaises(ValueError):
            workspace.ready_pipedrive_mapping(empty, {PROFILE: {}})

    def test_role_specific_standard_fields_and_custom_codes(self):
        valid = mapping(customer_name_field="title")
        self.assertEqual(workspace.ready_pipedrive_mapping(valid, {PROFILE: {}}), valid)
        for invalid in [mapping(permit_fields=["title"]), mapping(address_field="org_id"),
                        mapping(customer_name_field="Customer Name"), mapping(ahj_field="Authority"),
                        mapping(ahj_map={"fictional_org_id": PROFILE}), mapping(ahj_map={"991": "unloaded-profile"})]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                workspace.ready_pipedrive_mapping(invalid, {PROFILE: {}})

    def test_preflight_rejects_more_than_fifteen_custom_fields(self):
        fields = [f"{i:040x}" for i in range(1, 17)]
        with self.assertRaises(ValueError):
            workspace.ready_pipedrive_mapping(mapping(permit_fields=fields), {PROFILE: {}})

    def doctor(self, value):
        def read(path, **kwargs):
            if Path(path).name == "synthetic-mapping.json":
                return value
            if Path(path).name == "synthetic-messages.json":
                return [{"ahj_id": PROFILE}]
            return config()
        with patch.object(workspace, "read_json_file", side_effect=read), patch.object(workspace, "load_profiles", return_value={PROFILE: {}}), patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "synthetic-token"}), patch("permitkit.crm.DealClient.get") as get:
            result = workspace.doctor(Path("synthetic-config.json"))
        get.assert_not_called()
        return result

    def test_doctor_is_not_ready_with_generated_placeholders(self):
        result = self.doctor(mapping(permit_fields=["REPLACE_WITH_EXACT_PERMIT_FIELD_CODE"]))
        self.assertFalse(result["ready"])
        failure = next(c for c in result["checks"] if c["status"] == "needs_attention")
        self.assertIn("pipedrive-fields", failure["message"])
        self.assertIn("No network requests", failure["message"])
        self.assertEqual(result["network_requests"], 0)

    def test_doctor_accepts_complete_local_syntax_without_testing_connection(self):
        result = self.doctor(mapping())
        self.assertTrue(result["ready"])
        self.assertEqual(result["network_requests"], 0)

    def test_doctor_guidance_does_not_echo_arbitrary_private_values(self):
        secret = "synthetic-sensitive-field-name"
        result = self.doctor(mapping(address_field=secret))
        self.assertFalse(result["ready"])
        self.assertNotIn(secret, str(result))

    def test_standalone_rejects_unfinished_map_before_import_or_write(self):
        for value in [mapping(ahj_map={}), mapping(permit_fields=["REPLACE_WITH_EXACT_PERMIT_FIELD_CODE"]), mapping(ahj_map={"991": "unloaded-profile"})]:
            with patch.object(cli, "read_json", return_value=value), patch.object(cli, "load_profiles", return_value={PROFILE: {}}), patch.object(cli, "write_private_json") as write, patch("permitkit.crm.import_deal_permits") as importer, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = cli.main(["pipedrive-deals", "--mapping", "synthetic-mapping.json", "--deal-ids", "101", "--output", "private/synthetic-crm-test-unused"])
            self.assertEqual(status, 1)
            importer.assert_not_called()
            write.assert_not_called()

    def test_run_revalidates_mapping_before_detail_import(self):
        def read(path, **kwargs):
            return mapping(permit_fields=["placeholder"]) if Path(path).name == "synthetic-mapping.json" else config()
        with patch.object(workspace, "read_json_file", side_effect=read), patch.object(workspace, "doctor", return_value={"ready": True}), patch.object(workspace, "_messages", return_value=[{"ahj_id": PROFILE}]), patch.object(workspace, "load_profiles", return_value={PROFILE: {}}), patch("permitkit.crm.import_deal_permits") as importer, self.assertRaises(ValueError):
            workspace.run_workspace(Path("synthetic-config.json"))
        importer.assert_not_called()

    def test_custom_setup_prints_the_correct_config_command(self):
        path = workspace.ROOT / "private" / "custom space" / "sunbridge.json"
        output = io.StringIO()
        with patch.object(workspace, "create_workspace", return_value=path), contextlib.redirect_stdout(output):
            status = cli.main(["setup", "--output", "private/custom space"])
        self.assertEqual(status, 0)
        self.assertIn("doctor --config " + shlex.quote(str(path)), output.getvalue())


if __name__ == "__main__":
    unittest.main()
