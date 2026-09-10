import copy
import html
import json
import tempfile
import unittest
from pathlib import Path

from permitkit.__main__ import private_output
from permitkit.events import parse_message
from permitkit.validation import ROOT, load_profiles, validate_profile, validate_schema
from permitkit.workflow import _md, review_messages, render_markdown, write_report


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.profiles = load_profiles(ROOT / "profiles")
        self.messages = json.loads((ROOT / "examples/messages.json").read_text())
        self.permits = json.loads((ROOT / "examples/permits.json").read_text())

    def test_training_results_are_explicitly_reviewed_and_no_current_status_inferred(self):
        report = review_messages(self.messages, self.permits, self.profiles)
        self.assertEqual(report["crm_writes"], 0)
        self.assertEqual(report["summary"]["duplicates_skipped"], 1)
        self.assertTrue(all(row["event"]["review_required"] for row in report["items"]))
        self.assertTrue(all(row["event"]["observed_event_time"] is None for row in report["items"]))
        expected = json.loads((ROOT / "examples/expected-results.json").read_text())
        actual = {str(row["input_position"]): {"event_type": row["event"]["event_type"], "match": row["match"]["status"], "decision": row["decision"]} for row in report["items"]}
        self.assertEqual(actual, expected)

    def test_message_id_collision_holds_all_occurrences(self):
        first = copy.deepcopy(self.messages[0])
        changed = {**first, "subject": "Permit DEMO-SOLAR-001 issued"}
        report = review_messages([first, changed], self.permits, self.profiles)
        self.assertTrue(all(row["decision"] == "hold_conflicting_message_id" for row in report["items"]))
        self.assertTrue(all(row["match"]["deal_id"] is None for row in report["items"]))

    def test_unknown_profile_abstains_and_invalid_date_is_flagged(self):
        message = {**self.messages[0], "ahj_id": "unmapped", "received_at": "yesterday"}
        row = review_messages([message], self.permits, self.profiles)["items"][0]
        self.assertEqual(row["event"]["event_type"], "unknown")
        self.assertIn("unknown_ahj_profile", row["event"]["issues"])
        self.assertIn("missing_or_invalid_receipt_time", row["event"]["issues"])

    def test_markdown_treats_email_as_text_and_writes_local_review(self):
        message = {**self.messages[0], "subject": "<script>alert(1)</script> | test"}
        report = review_messages([message], self.permits, self.profiles)
        rendered = render_markdown(report)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&#124;", rendered)
        with tempfile.TemporaryDirectory() as directory:
            write_report(report, Path(directory))
            self.assertEqual(json.loads((Path(directory) / "review.json").read_text())["crm_writes"], 0)

    def test_markdown_links_images_and_autolinks_are_literal_and_json_is_original(self):
        payload = r"![notice](https://example.invalid/pixel) [open][ref] <https://example.invalid> www.example.invalid notice@example.invalid `code` \\[x] &lt;img&gt; | **bold**"
        message = {**self.messages[0], "message_id": payload, "subject": payload,
                   "sender": payload, "received_at": payload}
        report = review_messages([message], self.permits, self.profiles)
        original = copy.deepcopy(report)
        rendered = render_markdown(report)
        encoded = _md(payload)
        self.assertIn(encoded, rendered)
        self.assertEqual(html.unescape(encoded), payload)
        for active in ["![notice]", "[open]", "<https://", "https://", "www.", "notice@", "`code`", "**bold**", "&lt;img&gt;"]:
            with self.subTest(active=active):
                self.assertNotIn(active, rendered)
        self.assertEqual(report, original)
        self.assertEqual(report["items"][0]["original_message"]["subject"], payload)

    def test_all_dynamic_report_fields_use_literal_rendering(self):
        report = review_messages(self.messages[:1], self.permits, self.profiles)
        payload = "![notice](https://example.invalid/pixel)"
        row = report["items"][0]
        row["event"].update({"permit_id": payload, "rule_id": payload, "issues": [payload]})
        row["match"].update({"deal_id": payload, "method": payload, "issues": [payload]})
        report["warning"] = payload
        rendered = render_markdown(report)
        self.assertNotIn(payload, rendered)
        self.assertEqual(rendered.count(_md(payload)), 7)

    def test_public_output_and_symlink_escape_are_rejected(self):
        with self.assertRaises(ValueError):
            private_output(str(ROOT / "profiles"))
        with self.assertRaises(ValueError):
            private_output(str(ROOT / "private/../../public"))

    def test_disabled_real_profile_cannot_classify_training_email(self):
        profile = self.profiles["us-fl-lee-cape-coral-building"]
        message = {**self.messages[0], "ahj_id": profile["id"]}
        row = review_messages([message], self.permits, self.profiles)["items"][0]
        self.assertEqual(row["event"]["event_type"], "unknown")


class ValidationTests(unittest.TestCase):
    def test_profile_contract_detects_extra_missing_and_enum_fields(self):
        profile = json.loads((ROOT / "templates/ahj-profile.json").read_text())
        self.assertEqual(validate_profile(profile), [])
        del profile["jurisdiction"]["level"]
        profile["private_customer"] = "should not exist in a profile"
        profile["capabilities"]["submission_method"] = "guess"
        errors = validate_profile(profile)
        self.assertTrue(any("level" in e for e in errors))
        self.assertTrue(any("private_customer" in e for e in errors))
        self.assertTrue(any("submission_method" in e for e in errors))

    def test_documentation_status_requires_sources_and_dates(self):
        profile = json.loads((ROOT / "templates/ahj-profile.json").read_text())
        profile["verification"]["status"] = "documented"
        self.assertTrue(validate_profile(profile))

    def test_number_type_does_not_accept_boolean(self):
        self.assertTrue(validate_schema(True, {"type": "integer"}))

    def test_blank_and_whitespace_duplicate_rule_ids_fail_validation(self):
        for value in ["", " \t "]:
            profile = json.loads((ROOT / "profiles/examples/training-county.json").read_text())
            profile["parser"]["subject_rules"][0]["id"] = value
            with self.subTest(value=value):
                self.assertTrue(validate_profile(profile))
        profile = json.loads((ROOT / "profiles/examples/training-county.json").read_text())
        profile["parser"]["subject_rules"][1]["id"] = " submission "
        self.assertTrue(any("unique" in error for error in validate_profile(profile)))

    def test_sender_validation_matches_runtime_mailbox_checks(self):
        for sender in ["", "  ", "notifications", "@example.invalid", "example.invalid",
                       "one@example.invalid, two@example.invalid", "one@example.invalid\nBcc:two@example.invalid"]:
            profile = json.loads((ROOT / "profiles/examples/training-county.json").read_text())
            profile["parser"]["sender_allowlist"] = [sender]
            with self.subTest(sender=sender):
                self.assertTrue(validate_profile(profile))
        profile = json.loads((ROOT / "profiles/examples/training-county.json").read_text())
        profile["parser"]["sender_allowlist"] = ["Example County <NOTIFICATIONS@example.invalid>"]
        self.assertEqual(validate_profile(profile), [])
        message = json.loads((ROOT / "examples/messages.json").read_text())[0]
        self.assertEqual(parse_message(message, profile)["event_type"], "submission_received")


if __name__ == "__main__":
    unittest.main()
