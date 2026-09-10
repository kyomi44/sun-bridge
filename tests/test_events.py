import copy
import unittest

from sunbridge.events import parse_message


def profile():
    return {
        "id": "example-city", "permit_types": ["residential_solar"],
        "parser": {
            "status": "experimental", "sender_allowlist": ["permits@example.org"],
            "subject_rules": [
                {"id": rule_id, "event_type": event, "scope": scope,
                 "pattern": rf"Permit (?P<permit_id>SOL-\d{{4}}): {text}"}
                for rule_id, event, scope, text in [
                    ("received", "submission_received", "permit", "submission received"),
                    ("approved", "plans_approved", "review", "plans approved"),
                    ("ready", "permit_ready_to_issue", "permit", "ready to issue"),
                    ("issued", "permit_issued", "permit", "issued"),
                    ("review", "review_completed", "review", "review completed"),
                    ("closed", "permit_closed", "permit", "closed"),
                    ("failed", "inspection_failed", "inspection", "inspection failed"),
                ]
            ],
        },
    }


def message(subject="Permit SOL-0001: plans approved", **changes):
    result = {"message_id": "synthetic-001", "ahj_id": "example-city",
              "sender": "Example City <permits@example.org>", "subject": subject,
              "body": "", "received_at": "2026-01-01T12:00:00Z"}
    result.update(changes)
    return result


class EventTests(unittest.TestCase):
    def test_supported_event_retains_evidence_and_is_only_a_proposal(self):
        source = message()
        config = profile()
        original = copy.deepcopy((source, config))
        event = parse_message(source, config)
        self.assertEqual(event["event_type"], "plans_approved")
        self.assertEqual(event["scope"], "review")
        self.assertEqual(event["permit_id"], "SOL-0001")
        self.assertEqual(event["evidence"], {"field": "subject", "text": source["subject"]})
        self.assertTrue(event["review_required"])
        self.assertEqual(event["sender_authentication"], "not_verified")
        self.assertIn("experimental_parser", event["issues"])
        self.assertEqual((source, config), original)

    def test_negation_unfamiliar_suffix_and_forwarded_subject_abstain(self):
        for subject in ["Permit SOL-0001: plans not approved",
                        "Permit SOL-0001: plans approved pending corrections",
                        "Re: Permit SOL-0001: plans approved",
                        "Permit SOL-0001: plans approved\nnot approved"]:
            with self.subTest(subject=subject):
                self.assertEqual(parse_message(message(subject), profile())["event_type"], "unknown")

    def test_quoted_body_cannot_change_interpretation(self):
        event = parse_message(message("An update", body="> Permit SOL-0001: issued"), profile())
        self.assertEqual(event["event_type"], "unknown")
        self.assertIsNone(event["permit_id"])

    def test_ready_to_issue_review_and_inspection_remain_distinct(self):
        for text, event_type in [("ready to issue", "permit_ready_to_issue"),
                                 ("issued", "permit_issued"),
                                 ("review completed", "review_completed"),
                                 ("inspection failed", "inspection_failed")]:
            with self.subTest(text=text):
                self.assertEqual(parse_message(message(f"Permit SOL-0001: {text}"), profile())["event_type"], event_type)

    def test_multiple_rules_abstain_even_if_same_event_type(self):
        config = profile()
        duplicate = dict(config["parser"]["subject_rules"][1], id="duplicate")
        config["parser"]["subject_rules"].append(duplicate)
        event = parse_message(message(), config)
        self.assertEqual(event["event_type"], "unknown")
        self.assertIn("multiple_matching_subject_rules", event["issues"])

    def test_sender_and_ahj_are_required_routing_metadata(self):
        for changes in [{"sender": "permits@evil.example.org"},
                        {"sender": "permits@example.org, attacker@example.org"},
                        {"sender": "\"permits@example.org\" <attacker@example.org>"},
                        {"ahj_id": "other-city"}, {"ahj_id": ""}]:
            with self.subTest(changes=changes):
                self.assertEqual(parse_message(message(**changes), profile())["event_type"], "unknown")

    def test_invalid_regex_or_duplicate_rule_id_abstains(self):
        config = profile()
        config["parser"]["subject_rules"].append({"id": "bad", "event_type": "permit_issued", "scope": "permit", "pattern": "["})
        self.assertIn("invalid_rule_pattern", parse_message(message(), config)["issues"])
        config = profile()
        config["parser"]["subject_rules"][0]["id"] = "approved"
        self.assertIn("invalid_rule_configuration", parse_message(message(), config)["issues"])

    def test_invoice_number_is_not_a_permit_identifier(self):
        event = parse_message(message("Invoice 0001 paid", body="Permit SOL-0001"), profile())
        self.assertEqual(event["event_type"], "unknown")
        self.assertIsNone(event["permit_id"])

    def test_malformed_configuration_abstains(self):
        config = profile()
        config["parser"]["subject_rules"][0]["event_type"] = []
        self.assertIn("invalid_rule_configuration", parse_message(message(), config)["issues"])
        config = profile()
        config["parser"]["status"] = []
        self.assertIn("parser_not_enabled", parse_message(message(), config)["issues"])


if __name__ == "__main__":
    unittest.main()
