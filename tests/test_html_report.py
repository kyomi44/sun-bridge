import copy
import unittest
from html.parser import HTMLParser

from sunbridge.html_report import render_html


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)


class HTMLReportTests(unittest.TestCase):
    def report(self):
        return {"warning": "Review only", "summary": {"input_messages": 1, "review_items": 1, "duplicates_skipped": 0},
                "items": [{"input_position": 1, "decision": "needs_operator_review",
                           "event": {"event_type": "permit_issued", "message_id": "demo@example.invalid", "scope": "permit", "permit_id": "DEMO-001", "received_at": "", "issues": [], "evidence": {"field": "body", "text": "Permit DEMO-001 issued"}},
                           "match": {"status": "ambiguous", "issues": ["multiple_matching_permit_records"]},
                           "original_message": {"subject": "A different original subject", "sender": "notice@example.invalid", "date_header_at": "2026-01-01T00:00:00+00:00", "timestamp_source": "date_header_unverified", "import_issues": ["date_header_is_not_receipt_time"]}}]}

    def test_friendly_evidence_distinct_from_original_subject(self):
        report = self.report()
        saved = copy.deepcopy(report)
        output = render_html(report)
        for value in ("Sun Bridge", "Permit issued", "Original subject", "A different original subject", "Source evidence · body", "Permit DEMO-001 issued", "Operator review needed", "date header is not receipt time", "Claimed sent date (not receipt or event time)"):
            self.assertIn(value, output)
        self.assertEqual(report, saved)

    def test_every_dynamic_value_is_text_and_report_has_no_active_elements(self):
        payload = '<img src="https://example.invalid/pixel" onerror="alert(1)"><script>run()</script><a href="https://example.invalid/">open</a> & " '
        report = self.report()
        report["warning"] = payload
        report["summary"] = dict.fromkeys(report["summary"], payload)
        row = report["items"][0]
        row["input_position"] = payload
        row["decision"] = payload
        row["event"] = {key: payload for key in ("event_type", "message_id", "scope", "permit_id", "address", "ahj_id", "received_at", "rule_id")}
        row["event"].update({"evidence": {"field": payload, "text": payload}, "issues": [payload]})
        row["event"]["llm"] = dict.fromkeys(("provider", "model", "prompt_version"), payload)
        row["match"] = {"status": payload, "deal_id": payload, "method": payload, "issues": [payload]}
        row["original_message"] = {key: payload for key in ("sender", "subject", "body", "timestamp_source", "date_header_at", "ignored_attachment_count")}
        row["original_message"]["import_issues"] = [payload]
        output = render_html(report)
        tags = Tags()
        tags.feed(output)
        self.assertIn("&lt;img", output)
        for forbidden in ("script", "img", "a", "form", "input", "button", "iframe", "link", "object"):
            self.assertNotIn(forbidden, tags.tags)
        self.assertFalse(any(name in {"src", "href", "action"} or name.startswith("on") for name, _ in tags.attributes))
        self.assertIn("default-src 'none'; style-src 'unsafe-inline'", output)

    def test_empty_report(self):
        self.assertIn("No messages to review", render_html({"summary": {}, "items": []}))

    def test_crm_import_issues_show_affected_record_field_and_next_step(self):
        report = self.report()
        report["crm_import"] = {
            "summary": {"requested_unique_deals": 3, "deals_read": 2, "deals_with_permits": 1,
                        "permit_rows": 1, "issue_count": 2, "duplicate_input_ids_ignored": 0},
            "issues": [{"deal_id": 101, "code": "deal_read_failed"},
                       {"deal_id": 102, "code": "missing_or_unmapped_ahj", "source_field": "synthetic-ahj-field"}],
        }
        original = copy.deepcopy(report)
        output = render_html(report)
        for text in ("CRM import checks", "Selected deals", "Selected deal 101", "Selected deal 102",
                     "deal_read_failed", "synthetic-ahj-field", "Check access", "add an explicit mapping",
                     "An unmatched notice does not prove that no permit exists"):
            self.assertIn(text, output)
        self.assertLess(output.index("CRM import checks"), output.index("Review queue"))
        self.assertEqual(report, original)

    def test_crm_import_text_is_escaped_and_unrelated_payload_is_omitted(self):
        payload = '<img src="https://example.invalid/pixel"><script>run()</script><a href="https://example.invalid/">Open</a>'
        report = self.report()
        report["crm_import"] = {
            "summary": {key: payload for key in ("requested_unique_deals", "deals_read", "deals_with_permits", "permit_rows", "issue_count", "duplicate_input_ids_ignored")},
            "issues": [{"deal_id": payload, "code": payload, "source_field": payload,
                        "raw_response": "UNRELATED_SYNTHETIC_RESPONSE"}],
            "raw_deals": "UNRELATED_SYNTHETIC_DEALS",
        }
        report["crm_import"]["summary"]["raw_secret"] = "UNRELATED_SYNTHETIC_SECRET"
        output = render_html(report)
        self.assertIn("&lt;img", output)
        self.assertIn("Ask a technical helper", output)
        for excluded in ("UNRELATED_SYNTHETIC_RESPONSE", "UNRELATED_SYNTHETIC_DEALS", "UNRELATED_SYNTHETIC_SECRET"):
            self.assertNotIn(excluded, output)
        tags = Tags()
        tags.feed(output)
        for forbidden in ("img", "script", "a", "iframe", "form"):
            self.assertNotIn(forbidden, tags.tags)
        self.assertFalse(any(name in {"src", "href", "action"} or name.startswith("on") for name, _ in tags.attributes))

    def test_crm_section_only_appears_after_an_import(self):
        report = self.report()
        self.assertNotIn("CRM import checks", render_html(report))
        report["crm_import"] = {"summary": {}, "issues": []}
        self.assertIn("No import issues were reported", render_html(report))


if __name__ == "__main__":
    unittest.main()
