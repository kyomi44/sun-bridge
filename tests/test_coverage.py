"""Offline, synthetic checks for presence-only public email coverage artifacts.

Never load mailbox exports, private pilot reports, or CRM records in these tests.
"""

import copy
import contextlib
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from sunbridge.coverage import (
    load_registry, render_candidate_svg, render_markdown, render_pilot_svg,
    validate_registry,
)
from scripts import render_email_coverage as coverage_cli


ROOT = Path(__file__).resolve().parent.parent
SVG = "{http://www.w3.org/2000/svg}"
TOP_KEYS = {
    "schema_version", "evidence_reviewed_on", "evidence_basis", "identity_status",
    "public_runtime", "entries",
}
ENTRY_KEYS = {"id", "name", "candidate_signals", "pilot_events", "identity_note"}


def registry():
    return {
        "schema_version": "v1",
        "evidence_reviewed_on": "2026-02-01",
        "evidence_basis": "historical_private_review",
        "identity_status": "provisional",
        "public_runtime": "not_enabled",
        "entries": [
            {"id": "example-candidate-city", "name": "Example Candidate City",
             "candidate_signals": ["submission", "review_or_correction", "approval",
                                   "issuance", "inspection", "payment"],
             "pilot_events": [], "identity_note": "none"},
            {"id": "example-receipt-county", "name": "Example Receipt County",
             "candidate_signals": ["approval"],
             "pilot_events": ["submission_received", "plans_approved", "action_required"],
             "identity_note": "historical_domain_aliases"},
            {"id": "example-inspection-city", "name": "Example Inspection City",
             "candidate_signals": ["inspection"],
             "pilot_events": ["inspection_passed", "inspection_failed"],
             "identity_note": "cross_platform_identity"},
        ],
    }


class CoverageValidationTests(unittest.TestCase):
    def assert_invalid(self, value):
        errors = validate_registry(value)
        self.assertIsInstance(errors, list)
        self.assertTrue(errors)
        self.assertTrue(all(isinstance(error, str) for error in errors))

    def test_valid_synthetic_registry_is_not_mutated(self):
        value = registry()
        original = copy.deepcopy(value)
        self.assertEqual(validate_registry(value), [])
        self.assertEqual(value, original)

    def test_topology_and_required_keys_are_strict(self):
        for value in (None, True, 1, "registry", [], {}, {"entries": []}):
            with self.subTest(value=value):
                self.assert_invalid(value)
        for key in TOP_KEYS:
            value = registry()
            del value[key]
            with self.subTest(missing=key):
                self.assert_invalid(value)
        for key in ENTRY_KEYS:
            value = registry()
            del value["entries"][0][key]
            with self.subTest(missing_entry=key):
                self.assert_invalid(value)

    def test_literal_metadata_rejects_enabled_or_validated_claims(self):
        changes = {
            "schema_version": (1, True, "v2", None),
            "evidence_basis": ("human_validated", "live_monitoring", [], None),
            "identity_status": ("verified", True, {}, None),
            "public_runtime": ("enabled", "production", True, None),
        }
        for key, replacements in changes.items():
            for replacement in replacements:
                value = registry()
                value[key] = replacement
                with self.subTest(key=key, replacement=replacement):
                    self.assert_invalid(value)

    def test_review_date_is_an_actual_exact_iso_date(self):
        for date in ("2026-02-30", "2026-2-01", "20260201", "2026-02-01T00:00:00Z",
                     " 2026-02-01", "2026-02-01\n", "", None, 20260201, True):
            value = registry()
            value["evidence_reviewed_on"] = date
            with self.subTest(date=date):
                self.assert_invalid(value)
        value = registry()
        value["evidence_reviewed_on"] = "2024-02-29"
        self.assertEqual(validate_registry(value), [])

    def test_extra_metrics_private_fields_and_nested_payloads_are_rejected(self):
        additions = {
            "count": 12, "message_count": 12, "supporting_ordinals": [4, 8],
            "source": {"path": "private/synthetic-source.json"},
            "sender": "nobody@example.invalid", "subject": "Synthetic private subject",
            "body": "Synthetic private body", "permit_id": "DEMO-PERMIT",
            "crm_org_id": "fictional-org", "address": "Fictional service address",
            "customer_name": "Fictional Customer", "archive_sha256": "a" * 64,
        }
        for key, replacement in additions.items():
            for entry_level in (False, True):
                value = registry()
                destination = value["entries"][0] if entry_level else value
                destination[key] = replacement
                with self.subTest(key=key, entry_level=entry_level):
                    self.assert_invalid(value)

    def test_entries_and_individual_entries_have_bounded_types(self):
        for entries in ([], None, True, "entries", {}, [None], [True], [[]], ["entry"]):
            value = registry()
            value["entries"] = entries
            with self.subTest(entries=entries):
                self.assert_invalid(value)
        value = registry()
        value["entries"] = [dict(value["entries"][0], id=f"example-{index}",
                                 name=f"Example Place {index}") for index in range(2001)]
        self.assert_invalid(value)

    def test_identifiers_are_kebab_case_unique_and_not_private_references(self):
        for ident in ("", "Example-City", "example_city", "../private", "example--city",
                      "example-", "-example", "example city", "example\ncity", "x" * 81,
                      None, 8, True, {}):
            value = registry()
            value["entries"][0]["id"] = ident
            with self.subTest(ident=ident):
                self.assert_invalid(value)
        value = registry()
        value["entries"][1]["id"] = value["entries"][0]["id"]
        self.assert_invalid(value)

    def test_names_are_bounded_nonblank_printable_and_unique_case_insensitively(self):
        for name in ("", "  ", "\n", "Example\tCity", "Example\x00City", "Example\u202eCity",
                     "x" * 101, None, 8, True, [], {}):
            value = registry()
            value["entries"][0]["name"] = name
            with self.subTest(name=name):
                self.assert_invalid(value)
        value = registry()
        value["entries"][1]["name"] = value["entries"][0]["name"].upper()
        self.assert_invalid(value)

    def test_schema_bounds_and_exact_maximum_strings_agree(self):
        schema = json.loads((ROOT / "schemas/email-signal-coverage.schema.json").read_text())
        properties = schema["properties"]["entries"]["items"]["properties"]
        for key, expected in (("id", 80), ("name", 100)):
            self.assertEqual(properties[key]["maxLength"], expected)
            value = registry()
            value["entries"][0][key] = "x" * expected
            self.assertEqual(validate_registry(value), [])
            value["entries"][0][key] += "x"
            self.assert_invalid(value)

    def test_signal_and_event_arrays_accept_only_unique_known_strings(self):
        for key, good in (("candidate_signals", "approval"), ("pilot_events", "plans_approved")):
            for array in (None, True, good, {}, [None], [True], [8], [[]], [{}],
                          ["unsupported"], [good, good], [{"name": good, "count": 12}]):
                value = registry()
                value["entries"][0][key] = array
                with self.subTest(key=key, array=array):
                    self.assert_invalid(value)
        value = registry()
        value["entries"][0]["candidate_signals"] = ["permit_issued"]
        self.assert_invalid(value)
        value = registry()
        value["entries"][0]["pilot_events"] = ["issuance"]
        self.assert_invalid(value)

    def test_identity_notes_are_a_closed_non_free_text_enum(self):
        for note in (None, True, [], {}, "verified", "Free-text private source details"):
            value = registry()
            value["entries"][0]["identity_note"] = note
            with self.subTest(note=note):
                self.assert_invalid(value)
        for note in ("none", "historical_domain_aliases", "sender_spelling_variant",
                     "provisional_office_grouping", "unusual_domain_alias", "cross_platform_identity"):
            value = registry()
            value["entries"][0]["identity_note"] = note
            self.assertEqual(validate_registry(value), [])

    def test_candidate_families_and_body_aware_events_are_independent(self):
        value = registry()
        receipt = value["entries"][1]
        self.assertNotIn("submission", receipt["candidate_signals"])
        self.assertIn("submission_received", receipt["pilot_events"])
        self.assertEqual(validate_registry(value), [])
        self.assertEqual(value["entries"][0]["pilot_events"], [])

    def test_loader_sanitizes_invalid_json_and_private_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic-registry.json"
            path.write_text(json.dumps(registry()), encoding="utf-8")
            self.assertEqual(load_registry(path), registry())
            for contents in ("not json", "null", '{"body":"SYNTHETIC-DO-NOT-ECHO"}'):
                path.write_text(contents, encoding="utf-8")
                with self.subTest(contents=contents), self.assertRaises(ValueError) as caught:
                    load_registry(path)
                self.assertNotIn(contents, str(caught.exception))
                self.assertNotIn("SYNTHETIC-DO-NOT-ECHO", str(caught.exception))
                self.assertNotIn(str(path), str(caught.exception))
            with self.assertRaises(ValueError):
                load_registry(Path(folder) / "missing.json")

    def test_loader_rejects_duplicate_json_keys_invalid_bytes_and_oversized_input(self):
        original = json.dumps(registry())
        duplicate_key = original.replace('"schema_version": "v1"',
                                         '"schema_version": "v1", "schema_version": "v1"')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic-registry.json"
            for contents in (duplicate_key.encode(), b"\xff", b" " * 1_000_001,
                             b"[" * 10_000 + b"]" * 10_000):
                path.write_bytes(contents)
                with self.subTest(kind=contents[:10]), self.assertRaises(ValueError):
                    load_registry(path)


class CoverageRenderingTests(unittest.TestCase):
    def test_outputs_are_deterministic_and_need_no_private_files_or_network(self):
        value = registry()
        original = copy.deepcopy(value)
        with patch("socket.socket", side_effect=AssertionError("Must remain offline")), \
             patch("pathlib.Path.read_text", side_effect=AssertionError("Must use supplied public data")):
            for render in (render_markdown, render_pilot_svg, render_candidate_svg):
                with self.subTest(renderer=render.__name__):
                    first = render(value)
                    self.assertIsInstance(first, str)
                    self.assertEqual(first, render(value))
        self.assertEqual(value, original)

    def test_invalid_payload_cannot_hide_private_metrics_in_any_output(self):
        value = registry()
        value["entries"][0]["message_count"] = 12
        for render in (render_markdown, render_pilot_svg, render_candidate_svg):
            with self.subTest(renderer=render.__name__), self.assertRaises(ValueError):
                render(value)

    def test_svgs_are_accessible_xml_without_script_links_or_remote_assets(self):
        for render in (render_pilot_svg, render_candidate_svg):
            with self.subTest(renderer=render.__name__):
                root = ET.fromstring(render(registry()))
                self.assertEqual(root.tag, SVG + "svg")
                self.assertEqual(root.attrib.get("role"), "img")
                self.assertIsNotNone(root.find(SVG + "title"))
                self.assertIsNotNone(root.find(SVG + "desc"))
                self.assertTrue(root.find(SVG + "title").text)
                self.assertTrue(root.find(SVG + "desc").text)
                for element in root.iter():
                    self.assertNotIn(element.tag.rsplit("}", 1)[-1].lower(),
                                     {"script", "foreignobject", "image", "a", "iframe"})
                    for attr, value in element.attrib.items():
                        name = attr.rsplit("}", 1)[-1].lower()
                        self.assertFalse(name.startswith("on"), name)
                        self.assertNotIn(name, {"href", "src"})
                        self.assertNotIn("url(", value.lower())

    def test_candidate_only_agency_is_not_shown_as_a_pilot(self):
        value = registry()
        pilot_text = " ".join(ET.fromstring(render_pilot_svg(value)).itertext())
        candidate_text = " ".join(ET.fromstring(render_candidate_svg(value)).itertext())
        self.assertNotIn("Example Candidate City", pilot_text)
        for entry in value["entries"]:
            self.assertIn(entry["name"], candidate_text)
        self.assertIn("Example Receipt County", pilot_text)
        self.assertIn("Example Inspection City", pilot_text)

    def test_markup_is_escaped_not_interpreted_as_svg_or_markdown(self):
        value = registry()
        hostile = 'Example <script>alert("x")</script> & [link](https://example.invalid) | City'
        value["entries"][1]["name"] = hostile
        for render in (render_pilot_svg, render_candidate_svg):
            root = ET.fromstring(render(value))
            self.assertIn(hostile, " ".join(root.itertext()))
            self.assertFalse(any(element.tag.rsplit("}", 1)[-1] in {"script", "a"}
                                 for element in root.iter()))
        markdown = render_markdown(value)
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("[link](https://example.invalid)", markdown)
        self.assertNotIn(" | City", markdown)

    def test_public_artifact_language_keeps_historical_and_runtime_limits_visible(self):
        output = render_markdown(registry()).lower()
        self.assertIn("historical", output)
        self.assertIn("subject", output)
        self.assertIn("pilot", output)
        self.assertTrue("not enabled" in output or "not_enabled" in output)

    def test_published_registry_contains_only_allowlisted_presence_values(self):
        value = load_registry(ROOT / "coverage/ahj-email-signals.json")
        self.assertEqual(set(value), TOP_KEYS)
        for entry in value["entries"]:
            self.assertEqual(set(entry), ENTRY_KEYS)

        def check_types(item):
            if isinstance(item, dict):
                for child in item.values():
                    check_types(child)
            elif isinstance(item, list):
                for child in item:
                    check_types(child)
            else:
                self.assertIsInstance(item, str)

        check_types(value)

    def test_coverage_does_not_enable_real_ahj_profiles(self):
        paths = list((ROOT / "profiles/us").rglob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            profile = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(profile=path.name):
                self.assertEqual(profile["parser"]["status"], "not_implemented")
                self.assertFalse(profile["parser"].get("subject_rules"))


class CoverageCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "coverage/ahj-email-signals.json"
        self.source.parent.mkdir()
        self.source.write_text(json.dumps(registry()), encoding="utf-8")
        self.outputs = {
            "markdown": self.root / "docs/email-coverage.md",
            "pilot": self.root / "docs/assets/email-pilot-milestones.svg",
            "candidate": self.root / "docs/assets/email-candidate-signals.svg",
        }
        for name, value in (("ROOT", self.root), ("REGISTRY_PATH", self.source),
                            ("OUTPUT_PATHS", self.outputs)):
            patcher = patch.object(coverage_cli, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *arguments):
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr), \
             patch("socket.socket", side_effect=AssertionError("Must remain offline")):
            return coverage_cli.main(list(arguments))

    def test_generation_and_check_are_reproducible_from_only_public_registry(self):
        self.assertEqual(self.run_cli(), 0)
        expected = {
            "markdown": render_markdown(registry()),
            "pilot": render_pilot_svg(registry()),
            "candidate": render_candidate_svg(registry()),
        }
        original = {key: path.read_bytes() for key, path in self.outputs.items()}
        for key, content in original.items():
            self.assertEqual(content, expected[key].encode())
        with patch.object(coverage_cli, "_write_atomic", side_effect=AssertionError("Check cannot write")):
            self.assertEqual(self.run_cli("--check"), 0)
        self.assertEqual({key: path.read_bytes() for key, path in self.outputs.items()}, original)

    def test_missing_and_stale_outputs_fail_check_without_rewriting(self):
        self.assertEqual(self.run_cli("--check"), 1)
        self.assertFalse(any(path.exists() for path in self.outputs.values()))
        self.assertEqual(self.run_cli(), 0)
        path = self.outputs["pilot"]
        path.write_text("Synthetic stale artifact", encoding="utf-8")
        with patch.object(coverage_cli, "_write_atomic", side_effect=AssertionError("Check cannot write")):
            self.assertEqual(self.run_cli("--check"), 1)
        self.assertEqual(path.read_text(), "Synthetic stale artifact")
        self.assertIn("stale", self.stderr.getvalue().lower())

    def test_unexpected_input_path_argument_is_not_available(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("--input", "synthetic-unreviewed.json")
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(any(path.exists() for path in self.outputs.values()))

    def test_invalid_registry_does_not_write_or_echo_payload(self):
        self.source.write_text('{"body":"SYNTHETIC-PRIVATE-PAYLOAD"}')
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(any(path.exists() for path in self.outputs.values()))
        self.assertNotIn("SYNTHETIC-PRIVATE-PAYLOAD", self.stdout.getvalue() + self.stderr.getvalue())

    def test_registry_symbolic_link_and_parent_alias_fail_closed(self):
        saved_source = self.root / "synthetic-source.json"
        self.source.rename(saved_source)
        self.source.symlink_to(saved_source)
        self.assertEqual(self.run_cli(), 1)
        self.source.unlink()
        self.source.parent.rmdir()
        target = self.root / "synthetic-unreviewed-folder"
        target.mkdir()
        (target / self.source.name).write_text(json.dumps(registry()))
        self.source.parent.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(any(path.exists() for path in self.outputs.values()))

    def test_output_parent_alias_is_rejected_for_generation_and_check(self):
        self.assertEqual(self.run_cli(), 0)
        original_parent = self.root / "docs/assets"
        target = self.root / "synthetic-unreviewed-output"
        original_parent.rename(target)
        original_parent.symlink_to(target, target_is_directory=True)
        before = {path.name: path.read_bytes() for path in target.iterdir()}
        self.assertEqual(self.run_cli("--check"), 1)
        self.assertEqual(self.run_cli(), 1)
        self.assertEqual({path.name: path.read_bytes() for path in target.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
