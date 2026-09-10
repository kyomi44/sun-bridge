import copy
import unittest

from sunbridge.reconcile import match_event, normalize_address


def permit(**changes):
    record = {"deal_id": "demo-001", "ahj_id": "example-city", "permit_id": "SOL-0001",
              "service_address": "123 Example Street, Unit A, Example City, FL 00000",
              "customer_name": "Fictional Customer"}
    record.update(changes)
    return record


def event(**changes):
    result = {"ahj_id": "example-city", "permit_id": "SOL-0001", "address": None}
    result.update(changes)
    return result


class ReconciliationTests(unittest.TestCase):
    def test_exact_id_matches_without_mutating_source(self):
        proposal, records = event(permit_id=" sol-0001 "), [permit()]
        before = copy.deepcopy((proposal, records))
        result = match_event(proposal, records)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["deal_id"], "demo-001")
        self.assertEqual(result["method"], "ahj_permit_id")
        self.assertEqual((proposal, records), before)

    def test_id_collision_in_another_ahj_does_not_match(self):
        self.assertEqual(match_event(event(ahj_id="other-city"), [permit()])["status"], "unmatched")

    def test_wrong_id_never_falls_back_to_matching_address(self):
        result = match_event(event(permit_id="SOL-9999", address=permit()["service_address"]), [permit()])
        self.assertEqual(result["status"], "unmatched")
        self.assertIn("permit_id_not_found_no_address_fallback", result["issues"])

    def test_non_string_identifier_does_not_silently_fall_back(self):
        result = match_event(event(permit_id=1, address=permit()["service_address"]), [permit()])
        self.assertEqual(result["status"], "unmatched")
        self.assertIn("invalid_permit_id_type", result["issues"])

    def test_city_zip_is_not_a_service_address(self):
        result = match_event(event(permit_id=None, address="Example City FL 00000"),
                             [permit(service_address="Example City FL 00000")])
        self.assertEqual(result["status"], "unmatched")

    def test_identifier_punctuation_revision_and_leading_zeros_are_significant(self):
        for identifier in ["SOL0001", "SOL-1", "SOL-0001-R1"]:
            with self.subTest(identifier=identifier):
                self.assertEqual(match_event(event(permit_id=identifier), [permit()])["status"], "unmatched")

    def test_normalized_complete_address_can_match(self):
        result = match_event(event(permit_id=None, address="123 EXAMPLE ST. # A, Example City FL 00000"), [permit()])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["method"], "ahj_full_address")

    def test_unit_missing_different_unit_and_partial_address_do_not_match(self):
        for address in ["123 Example Street, Example City FL 00000",
                        "123 Example Street Unit B, Example City FL 00000",
                        "123 Example Street Unit A"]:
            with self.subTest(address=address):
                self.assertEqual(match_event(event(permit_id=None, address=address), [permit()])["status"], "unmatched")

    def test_numeric_unit_punctuation_is_preserved(self):
        self.assertNotEqual(normalize_address("123 Example St Unit 1.2"), normalize_address("123 Example St Unit 12"))

    def test_duplicate_id_is_ambiguous_even_on_same_deal(self):
        result = match_event(event(), [permit(), permit()])
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["deal_id"])

    def test_address_shared_by_several_permits_is_ambiguous(self):
        records = [permit(), permit(permit_id="ELEC-0001")]
        result = match_event(event(permit_id=None, address=records[0]["service_address"]), records)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(match_event(event(), records)["status"], "matched")

    def test_conflicting_address_blocks_exact_identifier(self):
        result = match_event(event(address="999 Different Street, Example City FL 00000"), [permit()])
        self.assertEqual(result["status"], "ambiguous")
        self.assertIn("permit_id_address_conflict", result["issues"])

    def test_customer_name_alone_never_matches(self):
        result = match_event(event(permit_id=None, customer_name="Fictional Customer"), [permit()])
        self.assertEqual(result["status"], "unmatched")

    def test_matched_record_must_have_deal_id(self):
        for deal_id in [None, "", False]:
            with self.subTest(deal_id=deal_id):
                self.assertEqual(match_event(event(), [permit(deal_id=deal_id)])["status"], "unmatched")


if __name__ == "__main__":
    unittest.main()
