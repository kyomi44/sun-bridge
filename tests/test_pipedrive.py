"""Synthetic tests; never call Pipedrive or use a real token."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from permitkit.pipedrive import (
    PipedriveClient, PipedriveError, _NoRedirects, build_summary, decode_value,
    discover_metadata_fields, discover_type_field, import_building_departments,
    project_organization, resolve_inventory_relationships,
)


TYPE = {"field_code": "type_code", "field_name": "Type", "field_type": "enum",
        "options": [{"id": 8, "label": "Building Department"}, {"id": 9, "label": "Installer"}]}
JURISDICTION = {"field_code": "jurisdiction_code", "field_name": "Jurisdiction Type", "field_type": "enum",
                "options": [{"id": 11, "label": "City"}, {"id": 12, "label": "County"}]}
COUNTY = {"field_code": "county_code", "field_name": "County", "field_type": "org"}


class EnumTests(unittest.TestCase):
    def test_enum_representations(self):
        for value in [8, "8", {"id": 8}, {"id": 8, "label": "Building Department"}, {"value": 8}]:
            with self.subTest(value=value):
                self.assertEqual(decode_value(value, TYPE), "Building Department")
        self.assertEqual(decode_value([8, {"id": 9}], TYPE), ["Building Department", "Installer"])
        self.assertEqual(decode_value("8,9", {**TYPE, "field_type": "set"}), ["Building Department", "Installer"])
        self.assertEqual(decode_value(None, TYPE), None)

    def test_type_discovery_ambiguity_missing_override(self):
        self.assertIs(discover_type_field([TYPE]), TYPE)
        renamed = {**TYPE, "field_name": "Business Category"}
        self.assertIs(discover_type_field([renamed]), renamed)
        with self.assertRaises(PipedriveError):
            discover_type_field([])
        with self.assertRaises(PipedriveError):
            discover_type_field([TYPE, {**TYPE, "field_code": "another"}])
        with self.assertRaises(PipedriveError):
            discover_type_field([{**TYPE, "options": [{"id": 9, "label": "Installer"}]}])
        duplicate = {**TYPE, "field_code": "another"}
        self.assertIs(discover_type_field([TYPE, duplicate], "another"), duplicate)

    def test_legacy_field_names_and_exact_type_match(self):
        legacy = {"key": "legacy", "name": "Type", "field_type": "enum", "options": TYPE["options"]}
        self.assertIs(discover_type_field([legacy]), legacy)
        metadata = discover_metadata_fields([legacy], legacy)
        self.assertIsNone(project_organization({"id": 1, "name": "Building Department vendor", "legacy": 9}, legacy, metadata))
        self.assertIsNone(project_organization({"id": 1, "legacy": "Building Department vendor"}, legacy, metadata))


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.fields = discover_metadata_fields([TYPE, JURISDICTION, COUNTY], TYPE)

    def row(self, ident, kind=None, county=None, name="Same Name"):
        return {"id": ident, "name": name, "custom_fields": {"type_code": 8, "jurisdiction_code": kind, "county_code": county}}

    def test_city_county_and_office_address_are_distinct(self):
        city = self.row(1, 11, 2)
        city["address"] = {"value": "123 Office Road", "admin_area_level_1": "FL", "locality": "Office City"}
        city["notes"] = "private unrelated note"
        city["open_deals_count"] = 12
        county = self.row(2, 12, name="A County")
        projected = [project_organization(row, TYPE, self.fields) for row in (city, county)]
        resolve_inventory_relationships(projected)
        self.assertEqual(projected[0]["jurisdiction_type"], "city")
        self.assertEqual(projected[1]["jurisdiction_type"], "county")
        self.assertEqual(projected[0]["metadata"]["county_organization_id"], 2)
        self.assertIsNone(projected[0]["metadata"]["county"])
        self.assertIsNone(projected[0]["metadata"]["state"])
        self.assertIsNone(projected[0]["metadata"]["parent_organization"])
        relation = projected[0]["organization_relationships"][0]
        self.assertEqual(relation["scope"], "crm_reference_only")
        self.assertEqual(relation["target_name"], "A County")
        self.assertTrue(relation["target_in_inventory"])
        serialized = json.dumps(projected)
        for unretained in ("Office Road", "private unrelated note", "open_deals_count", "Office City"):
            self.assertNotIn(unretained, serialized)
        summary = build_summary(projected, TYPE, self.fields)
        self.assertEqual(summary["county_relationship_counts"]["target_jurisdiction_types"], {"county": 1})

    def test_unknown_stays_unknown_despite_name_or_address(self):
        row = self.row(1, name="City of Example, Florida")
        row["address_state"] = "Florida"
        record = project_organization(row, TYPE, self.fields)
        self.assertEqual(record["jurisdiction_type"], "unknown")
        self.assertIsNone(record["metadata"]["state"])
        self.assertIsNone(record["public_ahj_id"])
        self.assertEqual(record["local_candidate_id"], "pending/pipedrive/1")

    def test_missing_relation_target_is_not_fetched_or_guessed(self):
        records = [project_organization(self.row(1, 11, 999), TYPE, self.fields)]
        resolve_inventory_relationships(records)
        relation = records[0]["organization_relationships"][0]
        self.assertFalse(relation["target_in_inventory"])
        self.assertIsNone(relation["target_name"])

    def test_address_components_excluded_and_duplicate_names_preserved(self):
        fields = discover_metadata_fields([TYPE, {"field_code": "address_locality", "field_name": "City"}], TYPE)
        self.assertEqual(fields["city"], [])
        records = [project_organization(self.row(i), TYPE, self.fields) for i in (1, 2)]
        self.assertNotEqual(records[0]["local_candidate_id"], records[1]["local_candidate_id"])
        self.assertEqual(build_summary(records, TYPE, self.fields)["duplicate_name_groups"], 1)


class ClientTests(unittest.TestCase):
    def test_pagination_consumes_all_cursors(self):
        client = PipedriveClient("synthetic-token")
        responses = [
            {"success": True, "data": [{"id": 1}], "additional_data": {"next_cursor": "second"}},
            {"success": True, "data": [{"id": 2}], "additional_data": {"pagination": {"next_cursor": "third"}}},
            {"success": True, "data": [{"id": 3}], "additional_data": {}},
        ]
        with patch.object(client, "get", side_effect=responses) as getter:
            self.assertEqual([r["id"] for r in client.pages("/api/v2/organizations")], [1, 2, 3])
            self.assertEqual(getter.call_count, 3)

    def test_cursor_loop_and_missing_cursor_fail(self):
        for responses in [
            [{"data": [], "additional_data": {"next_cursor": "same"}}] * 2,
            [{"data": [], "additional_data": {"more_items_in_collection": True}}],
        ]:
            client = PipedriveClient("synthetic-token")
            with patch.object(client, "get", side_effect=responses), self.assertRaises(PipedriveError):
                list(client.pages("/api/v2/organizationFields"))

    def test_only_gets_official_host_and_token_is_header(self):
        client = PipedriveClient("synthetic-secret")
        with patch.object(client._opener, "open", return_value=io.BytesIO(b'{"success":true,"data":[]}')) as opened:
            client.get("/api/v2/organizations", {"limit": 500})
            request = opened.call_args.args[0]
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.host, "api.pipedrive.com")
            self.assertNotIn("synthetic-secret", request.full_url)
            self.assertEqual(request.get_header("X-api-token"), "synthetic-secret")
        with self.assertRaises(PipedriveError):
            client.get("https://elsewhere.example/steal")
        self.assertIsNone(_NoRedirects().redirect_request(None, None, 302, None, None, "https://elsewhere.example"))

    def test_error_messages_do_not_expose_bodies_urls_or_tokens(self):
        client = PipedriveClient("secret-value")
        error = urllib.error.HTTPError("https://elsewhere.example/secret-value", 401, "secret-value", {}, io.BytesIO(b"secret-value"))
        with patch.object(client._opener, "open", side_effect=error):
            with self.assertRaises(PipedriveError) as caught:
                client.get("/api/v2/organizations")
        self.assertNotIn("secret-value", str(caught.exception))
        self.assertNotIn("https://", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        with patch.object(client._opener, "open", return_value=io.BytesIO(b'{"success":false,"error":"secret-value"}')):
            with self.assertRaises(PipedriveError) as caught:
                client.get("/api/v2/organizations")
        self.assertNotIn("secret-value", str(caught.exception))

    def test_retries_are_bounded_and_retry_after_capped(self):
        client = PipedriveClient("synthetic-token")
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError("hidden", 429, "hidden", {"Retry-After": "1000"}, None)
        with patch.object(client._opener, "open", side_effect=fail) as opened, patch("permitkit.pipedrive.time.sleep") as sleep:
            with self.assertRaises(PipedriveError):
                client.get("/api/v2/organizations")
        self.assertEqual(opened.call_count, 4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [20, 20, 20])


class ImportTests(unittest.TestCase):
    def test_import_retains_only_projection_and_generates_no_public_profile(self):
        rows = [
            {"id": 1, "name": "Example", "custom_fields": {"type_code": [8], "jurisdiction_code": {"id": 11, "label": "City"}}},
            {"id": 2, "name": "Unrelated Customer", "custom_fields": {"type_code": 9}},
        ]
        def pages(client, path, params=None):
            return iter([TYPE, JURISDICTION, COUNTY] if path.endswith("organizationFields") else rows)
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private" / "inventory"
            with patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "synthetic-token"}), patch.object(PipedriveClient, "pages", pages):
                result = import_building_departments(None, private)
            self.assertEqual(result["building_department_count"], 1)
            self.assertEqual({p.name for p in private.iterdir()}, {"building_departments.json", "import_summary.json", "profile_candidates.json", "crm_mapping.json"})
            combined = " ".join(p.read_text() for p in private.iterdir())
            self.assertNotIn("Unrelated Customer", combined)
            self.assertNotIn("synthetic-token", combined)
            self.assertIsNone(json.loads((private / "profile_candidates.json").read_text())[0]["public_ahj_id"])
            for file in private.iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_public_directory_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(PipedriveClient, "pages") as pages:
            with self.assertRaises(PipedriveError):
                import_building_departments(None, Path(temporary) / "profiles")
            pages.assert_not_called()


if __name__ == "__main__":
    unittest.main()
