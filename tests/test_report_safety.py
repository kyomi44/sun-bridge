"""Report files are private from creation and never truncate another inode."""

import copy
import html
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunbridge.workflow import _md, render_markdown, review_messages, write_report


NAMES = ("review.json", "review.md", "review.html")


class ReportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.report = review_messages([], [], {})

    def test_arbitrary_component_temp_directory_gets_three_private_reports(self):
        write_report(self.report, self.base)
        self.assertEqual(json.loads((self.base / "review.json").read_text())["crm_writes"], 0)
        self.assertIn("Permit notification review", (self.base / "review.md").read_text())
        self.assertIn("<!doctype html>", (self.base / "review.html").read_text())
        for name in NAMES:
            self.assertEqual(stat.S_IMODE((self.base / name).stat().st_mode), 0o600)
        self.assertFalse(list(self.base.glob(".sunbridge-report-*")))

    def test_markdown_surfaces_crm_import_counts_and_actionable_issues(self):
        self.report["crm_import"] = {
            "summary": {"requested_unique_deals": 3, "deals_read": 2, "deals_with_permits": 1,
                        "permit_rows": 2, "issue_count": 2, "duplicate_input_ids_ignored": 0},
            "issues": [{"deal_id": 101, "code": "deal_read_failed"},
                       {"deal_id": 102, "source_field": "example_permit_field", "code": "missing_permit_identifier"}],
        }
        rendered = render_markdown(self.report)
        self.assertIn("Selected deals: 3", rendered)
        self.assertIn("Deals read: 2", rendered)
        self.assertIn("| 101 |", rendered)
        self.assertIn(_md("example_permit_field"), rendered)
        self.assertIn(_md("missing_permit_identifier"), rendered)
        self.assertIn("Do not guess a match", rendered)
        self.assertLess(rendered.index("CRM import checks"), rendered.index("| Message |"))

    def test_markdown_crm_import_fields_are_literal_and_unknown_fields_are_not_copied(self):
        payload = '<script>bad()</script> ![image](https://example.invalid/pixel) | [link](https://example.invalid)'
        self.report["crm_import"] = {
            "summary": {"requested_unique_deals": payload, "private_extra": "do-not-copy-this-value"},
            "issues": [{"deal_id": payload, "source_field": payload, "code": payload,
                        "raw_response": "do-not-copy-this-value"}],
        }
        original = copy.deepcopy(self.report)
        rendered = render_markdown(self.report)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("![image]", rendered)
        self.assertNotIn("https://", rendered)
        self.assertNotIn("do-not-copy-this-value", rendered)
        self.assertEqual(rendered.count(_md(payload)), 4)
        self.assertIn(payload, html.unescape(rendered))
        self.assertEqual(self.report, original)

    def test_empty_crm_issue_list_does_not_claim_complete_coverage(self):
        self.report["crm_import"] = {"summary": {}, "issues": []}
        rendered = render_markdown(self.report)
        self.assertIn("No CRM import issues were reported", rendered)
        self.assertIn("does not certify", rendered)

    def test_replacing_world_readable_files_uses_private_new_inodes(self):
        old_inodes = {}
        for name in NAMES:
            path = self.base / name
            path.write_text("previous report")
            path.chmod(0o644)
            old_inodes[name] = path.stat().st_ino
        write_report(self.report, self.base)
        for name in NAMES:
            path = self.base / name
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotEqual(path.stat().st_ino, old_inodes[name])

    def test_hard_linked_report_does_not_truncate_or_chmod_other_path(self):
        original = self.base / "original.txt"
        original.write_text("preserve this source")
        original.chmod(0o644)
        os.link(original, self.base / "review.json")
        write_report(self.report, self.base)
        self.assertEqual(original.read_text(), "preserve this source")
        self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o644)
        self.assertNotEqual(original.stat().st_ino, (self.base / "review.json").stat().st_ino)

    def test_any_symlink_leaf_is_rejected_before_other_reports_change(self):
        for name in NAMES:
            with self.subTest(name=name):
                output = self.base / name.replace(".", "-")
                output.mkdir()
                for other in NAMES:
                    if other != name:
                        (output / other).write_text("unchanged")
                target = self.base / "missing-private-source"
                (output / name).symlink_to(target)
                with self.assertRaises(ValueError):
                    write_report(self.report, output)
                for other in NAMES:
                    if other != name:
                        self.assertEqual((output / other).read_text(), "unchanged")
                self.assertFalse(target.exists())
                self.assertFalse(list(output.glob(".sunbridge-report-*")))

    def test_any_directory_leaf_is_rejected_before_other_reports_change(self):
        for name in NAMES:
            with self.subTest(name=name):
                output = self.base / name.replace(".", "-")
                output.mkdir()
                for other in NAMES:
                    if other != name:
                        (output / other).write_text("unchanged")
                (output / name).mkdir()
                with self.assertRaises(ValueError):
                    write_report(self.report, output)
                for other in NAMES:
                    if other != name:
                        self.assertEqual((output / other).read_text(), "unchanged")
                self.assertFalse(list(output.glob(".sunbridge-report-*")))

    def test_user_created_parent_and_output_symlink_aliases_are_rejected(self):
        real = self.base / "real"
        real.mkdir()
        alias = self.base / "alias"
        alias.symlink_to(real, target_is_directory=True)
        for output in (alias, alias / "nested", alias / "nested" / ".."):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    write_report(self.report, output)
        self.assertEqual(list(real.iterdir()), [])

    def test_file_parent_is_rejected(self):
        parent = self.base / "not-a-directory"
        parent.write_text("keep")
        with self.assertRaises(ValueError):
            write_report(self.report, parent / "nested")
        self.assertEqual(parent.read_text(), "keep")

    def test_staging_failure_keeps_previous_reports_and_cleans_temporary_files(self):
        for name in NAMES:
            (self.base / name).write_text("unchanged")
        original = tempfile.mkstemp
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated staging failure")
            fd, name = original(*args, **kwargs)
            self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
            return fd, name

        with patch("sunbridge.workflow.tempfile.mkstemp", side_effect=fail_second):
            with self.assertRaises(OSError):
                write_report(self.report, self.base)
        for name in NAMES:
            self.assertEqual((self.base / name).read_text(), "unchanged")
        self.assertFalse(list(self.base.glob(".sunbridge-report-*")))

    def test_replace_failure_cleans_staged_files(self):
        for name in NAMES:
            (self.base / name).write_text("unchanged")
        with patch("sunbridge.workflow.os.replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                write_report(self.report, self.base)
        for name in NAMES:
            self.assertEqual((self.base / name).read_text(), "unchanged")
        self.assertFalse(list(self.base.glob(".sunbridge-report-*")))


if __name__ == "__main__":
    unittest.main()
