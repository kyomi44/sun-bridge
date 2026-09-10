"""Offline tests for explicit deal scope, mappings and selected-data projection."""

import http.client
import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from sunbridge import crm
from sunbridge.pipedrive import PipedriveClient, PipedriveError
from sunbridge.reconcile import match_event


AHJ, PERMIT, SECOND, ADDRESS, CUSTOMER = (letter * 40 for letter in "abcde")
FIELDS = [
    {"code": "id", "name": "ID", "type": "int"},
    {"code": "title", "name": "Title", "type": "varchar"},
    {"code": "org_id", "name": "Organization", "type": "org"},
    {"code": AHJ, "name": "Authority", "type": "org"},
    {"code": PERMIT, "name": "Permit number", "type": "varchar"},
    {"code": SECOND, "name": "Another permit", "type": "varchar"},
    {"code": ADDRESS, "name": "Service address", "type": "address"},
    {"code": CUSTOMER, "name": "Customer name", "type": "varchar"},
]


def mapping(**changes):
    return {"schema_version": 1, "ahj_field": AHJ, "permit_fields": [PERMIT],
            "address_field": ADDRESS, "customer_name_field": None,
            "ahj_map": {"991": "example-training-county"}, **changes}


def deal(ident=101, **custom_changes):
    return {"success": True, "data": {
        "id": ident, "title": "Display title only", "org_id": 991,
        "notes": "unrelated-private-note", "person": {"name": "unrelated-private-contact"},
        "custom_fields": {AHJ: 991, PERMIT: "001-SOLAR / A", SECOND: "ELECTRICAL-002",
                          ADDRESS: "100 Example Way, Unit A, Example City, ZZ 00000",
                          CUSTOMER: "Optional Example", **custom_changes},
    }}


class MappingTests(unittest.TestCase):
    def test_offline_validation_allows_setup_and_copies_containers(self):
        original = mapping(ahj_map={})
        with patch.object(crm.DealClient, "get") as get:
            result = crm.validate_mapping(original)
        get.assert_not_called()
        result["permit_fields"].append(SECOND)
        self.assertEqual(original["permit_fields"], [PERMIT])
        template = json.loads((Path(__file__).resolve().parent.parent / "templates/pipedrive-deal-mapping.json").read_text())
        self.assertEqual(crm.validate_mapping(template), template)

    def test_invalid_mapping_shapes_are_rejected(self):
        for value in [None, {}, mapping(schema_version=True), mapping(extra="unexpected"),
                      mapping(permit_fields=[]), mapping(permit_fields=[PERMIT, PERMIT]),
                      mapping(customer_name_field=12), mapping(ahj_map={991: "profile"})]:
            with self.subTest(value=type(value)), self.assertRaises(crm.DealAdapterError):
                crm.validate_mapping(value)

    def test_labels_unknown_codes_and_unsafe_builtins_are_not_mappings(self):
        for selected in [mapping(permit_fields=["Permit number"]), mapping(permit_fields=["f" * 40]),
                         mapping(permit_fields=["id"]), mapping(address_field="title"),
                         mapping(ahj_field="title")]:
            with self.assertRaises(crm.DealAdapterError):
                crm._validate_mapping(selected, FIELDS)

    def test_numeric_permit_field_type_is_rejected_before_deal_read(self):
        fields = [{**f, "type": "double"} if f["code"] == PERMIT else f for f in FIELDS]
        with patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "synthetic-token"}), patch.object(crm.DealClient, "fields", return_value=fields), patch.object(crm.DealClient, "get") as get:
            with self.assertRaises(crm.DealAdapterError):
                crm.import_deal_permits(None, mapping(), [101])
        get.assert_not_called()

    def test_custom_field_limit(self):
        codes = [f"{i:040x}" for i in range(1, 16)]
        fields = FIELDS + [{"code": code, "name": "Synthetic extra", "type": "varchar"} for code in codes]
        with self.assertRaises(crm.DealAdapterError):
            crm._validate_mapping(mapping(permit_fields=codes), fields)

    def test_bad_or_oversized_id_selection_fails_before_reading_credentials(self):
        for ids in [[], [True], ["101"], [0], [-1], list(range(1, 102))]:
            with patch.object(crm, "read_token") as token, self.assertRaises(crm.DealAdapterError):
                crm.import_deal_permits(None, mapping(), ids)
            token.assert_not_called()


class ImportTests(unittest.TestCase):
    def import_rows(self, responses, selected=None, ids=None, fields=None):
        with patch.dict(os.environ, {"PIPEDRIVE_API_TOKEN": "synthetic-token"}), patch.object(crm.DealClient, "fields", return_value=fields or FIELDS), patch.object(crm.DealClient, "get", side_effect=responses) as get:
            result = crm.import_deal_permits(None, selected or mapping(), ids or [101])
        return result, get.call_args_list

    def test_unique_ids_only_and_selected_fields_only(self):
        result, calls = self.import_rows([deal(102), deal(101)], ids=[102, 101, 102])
        self.assertEqual([call.args[0] for call in calls], ["/api/v2/deals/102", "/api/v2/deals/101"])
        self.assertEqual(set(calls[0].args[1]["custom_fields"].split(",")), {AHJ, PERMIT, ADDRESS})
        self.assertEqual(calls[0].args[1]["include_option_labels"], "true")
        self.assertEqual(result["summary"]["duplicate_input_ids_ignored"], 1)
        self.assertEqual(result["summary"]["crm_writes"], 0)
        public_result = json.dumps(result)
        for excluded in ("unrelated-private-note", "unrelated-private-contact", "Display title only", "Optional Example"):
            self.assertNotIn(excluded, public_result)
        self.assertEqual(result["permits"][0]["permit_id"], "001-SOLAR / A")

    def test_multiple_fields_stay_distinct_and_existing_matcher_is_conservative(self):
        selected = mapping(permit_fields=[PERMIT, SECOND])
        result, _ = self.import_rows([deal(**{SECOND: "001-SOLAR / A"})], selected)
        self.assertEqual(len(result["permits"]), 2)
        self.assertEqual({r["source_field"] for r in result["permits"]}, {PERMIT, SECOND})
        event = {"ahj_id": "example-training-county", "permit_id": "001-SOLAR / A"}
        self.assertEqual(match_event(event, result["permits"])["status"], "ambiguous")

    def test_missing_and_numeric_permit_values_never_become_ids(self):
        for value in [None, "", 123, ["001"], {"label": "001", "id": 4}]:
            with self.subTest(value=value):
                result, _ = self.import_rows([deal(**{PERMIT: value})])
                self.assertEqual(result["permits"], [])
                self.assertIn(result["issues"][0]["code"], {"missing_permit_identifier", "non_string_permit_identifier"})

    def test_string_wrapper_preserves_leading_zero(self):
        result, _ = self.import_rows([deal(**{PERMIT: {"value": "001"}})])
        self.assertEqual(result["permits"][0]["permit_id"], "001")

    def test_unmapped_and_multivalue_ahj_never_use_name_or_address(self):
        for value in [None, [991], 992, "Training County"]:
            with self.subTest(value=value):
                result, _ = self.import_rows([deal(**{AHJ: value})])
                self.assertEqual(result["permits"], [])
                self.assertEqual(result["issues"][0]["code"], "missing_or_unmapped_ahj")
                self.assertNotIn("Training County", json.dumps(result))

    def test_ahj_enum_uses_exact_option_id_not_label(self):
        fields = [{**f, "type": "enum"} if f["code"] == AHJ else f for f in FIELDS]
        result, _ = self.import_rows([deal(**{AHJ: {"id": 991, "label": "Do not infer from this name"}})], fields=fields)
        self.assertEqual(result["permits"][0]["ahj_id"], "example-training-county")

    def test_explicit_builtin_org_and_optional_title(self):
        result, calls = self.import_rows([deal()], mapping(ahj_field="org_id", customer_name_field="title"))
        self.assertEqual(result["permits"][0]["customer_name"], "Display title only")
        self.assertNotIn("org_id", calls[0].args[1]["custom_fields"])
        self.assertNotIn("title", calls[0].args[1]["custom_fields"])

    def test_address_unit_is_retained_without_duplication(self):
        for address, expected in [
            ({"value": "100 Example Way, Example City, ZZ 00000", "subpremise": "A"}, "100 Example Way, Example City, ZZ 00000, Unit A"),
            ({"value": "100 Example Way, Apt A, Example City, ZZ 00000", "subpremise": "A"}, "100 Example Way, Apt A, Example City, ZZ 00000"),
        ]:
            with self.subTest(address=address):
                result, _ = self.import_rows([deal(**{ADDRESS: address})])
                self.assertEqual(result["permits"][0]["service_address"], expected)

    def test_conflicting_or_invalid_address_excludes_the_deal(self):
        for address in [{"value": "100 Example Way, Unit B", "subpremise": "A"}, {"route": "Example Way"}, 123]:
            result, _ = self.import_rows([deal(**{ADDRESS: address})])
            self.assertEqual(result["permits"], [])
            self.assertIn(result["issues"][0]["code"], {"conflicting_address_unit", "invalid_service_address"})

    def test_missing_address_is_reported_without_fabrication(self):
        result, _ = self.import_rows([deal(**{ADDRESS: None})])
        self.assertIsNone(result["permits"][0]["service_address"])
        self.assertEqual(result["issues"][0]["code"], "missing_service_address")

    def test_failed_or_wrong_deal_responses_are_omitted_safely(self):
        response = deal(999)
        result, _ = self.import_rows([crm.DealAdapterError("synthetic-sensitive-error"), response], ids=[101, 102])
        self.assertEqual(result["permits"], [])
        self.assertEqual([i["code"] for i in result["issues"]], ["deal_read_failed", "unexpected_deal_response"])
        self.assertNotIn("synthetic-sensitive-error", json.dumps(result))


class ClientTests(unittest.TestCase):
    def test_transport_is_fixed_host_get_with_header_and_explicit_allowlist(self):
        client = crm.DealClient("synthetic-secret", [101])
        with patch.object(client._opener, "open", return_value=io.BytesIO(b'{"success":true,"data":{}}')) as opened:
            client.get("/api/v2/deals/101", {"custom_fields": PERMIT, "include_option_labels": "true"})
            request = opened.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.host, "api.pipedrive.com")
        self.assertNotIn("synthetic-secret", request.full_url)
        self.assertEqual(request.get_header("X-api-token"), "synthetic-secret")
        self.assertTrue(any(isinstance(h, crm._NoRedirects) for h in client._opener.handlers))
        for path in ["/api/v2/deals", "/api/v2/deals/102", "/api/v2/deals/101/notes", "/api/v2/persons", "https://elsewhere.example/api/v2/deals/101"]:
            with self.subTest(path=path), patch.object(client._opener, "open") as opened, self.assertRaises(crm.DealAdapterError):
                client.get(path)
            opened.assert_not_called()

    def test_metadata_client_has_no_deal_access_and_org_client_is_unchanged(self):
        with self.assertRaises(crm.DealAdapterError):
            crm.DealClient("synthetic-token").get("/api/v2/deals/101")
        with self.assertRaises(PipedriveError):
            PipedriveClient("synthetic-token").get("/api/v2/deals/101")

    def test_unsupported_query_expansion_is_rejected(self):
        client = crm.DealClient("synthetic-token", [101])
        for params in [{"include_fields": "notes_count"}, {"custom_fields": "unknown"}, {"custom_fields": ",".join([PERMIT] * 16)}]:
            with self.assertRaises(crm.DealAdapterError):
                client.get("/api/v2/deals/101", params)

    def test_metadata_paginates_and_projects_only_code_name_type(self):
        client = crm.DealClient("synthetic-token")
        pages = [
            {"data": [{"field_code": AHJ, "field_name": "Authority", "field_type": "org", "description": "excluded-description"}], "additional_data": {"next_cursor": "next"}},
            {"data": [{"key": PERMIT, "name": "Permit", "field_type": "varchar", "options": [{"id": 1, "label": "excluded-option"}]}]},
        ]
        with patch.object(client, "get", side_effect=pages) as getter:
            fields = client.fields()
        self.assertEqual(fields, [{"code": AHJ, "name": "Authority", "type": "org"}, {"code": PERMIT, "name": "Permit", "type": "varchar"}])
        self.assertEqual(getter.call_args_list[1].args[1]["cursor"], "next")

    def test_metadata_cursor_failures_and_duplicate_codes_fail_closed(self):
        one = {"field_code": AHJ, "field_name": "Authority", "field_type": "org"}
        for pages in [
            [{"data": [], "additional_data": {"next_cursor": "loop"}}] * 2,
            [{"data": [], "additional_data": {"more_items_in_collection": True}}],
            [{"data": [one, one]}],
        ]:
            client = crm.DealClient("synthetic-token")
            with patch.object(client, "get", side_effect=pages), self.assertRaises(crm.DealAdapterError):
                client.fields()

    def test_enum_and_set_options_are_projected_without_other_metadata(self):
        rows = [
            {"field_code": AHJ, "field_name": "Authority", "field_type": "enum",
             "options": [{"id": 991, "label": "Example Training County", "color": "hidden-color", "extra": "hidden-extra"}],
             "description": "hidden-description", "actual_deal_value": "hidden-value"},
            {"field_code": SECOND, "field_name": "Choices", "field_type": "set",
             "options": [{"id": 992, "label": "Example Choice"}]},
            {"field_code": "status", "field_name": "Status", "field_type": "enum",
             "options": [{"id": "open", "label": "Open"}]},
        ]
        with patch.object(crm, "read_token", return_value="synthetic-token"), patch.object(crm.DealClient, "get", return_value={"data": rows}) as get:
            fields = crm.discover_deal_fields()
        self.assertEqual(fields[0], {"code": AHJ, "name": "Authority", "type": "enum", "options": [{"id": 991, "label": "Example Training County"}]})
        self.assertEqual(fields[1]["options"], [{"id": 992, "label": "Example Choice"}])
        self.assertEqual(fields[2]["options"], [{"id": "open", "label": "Open"}])
        self.assertNotIn("hidden-", json.dumps(fields))
        self.assertEqual(get.call_args_list[0].args[0], crm.FIELDS_PATH)
        self.assertEqual(get.call_count, 1)

    def test_unsupplied_and_empty_options_remain_distinguishable(self):
        for supplied, expected in [({}, None), ({"options": None}, None), ({"options": []}, [])]:
            row = {"field_code": AHJ, "field_name": "Authority", "field_type": "enum", **supplied}
            with patch.object(crm.DealClient, "get", return_value={"data": [row]}):
                field = crm.DealClient("synthetic-token").fields()[0]
            self.assertEqual(field.get("options"), expected)
            self.assertEqual("options" in field, expected is not None)

    def test_malformed_option_metadata_fails_without_exposing_values(self):
        secret = "synthetic-sensitive-value"
        invalid = [
            secret, {}, [secret], [{}], [{"id": True, "label": secret}],
            [{"id": 0, "label": secret}], [{"id": -1, "label": secret}],
            [{"id": 2 ** 63, "label": secret}], [{"id": 1.5, "label": secret}],
            [{"id": "991", "label": secret}], [{"id": 991, "label": None}],
            [{"id": 991, "label": " "}], [{"id": 991, "label": secret + "\n"}],
            [{"id": 991, "label": "x" * 1001}],
            [{"id": 991, "label": secret}, {"id": 991, "label": "Other"}],
        ]
        for options in invalid:
            row = {"field_code": AHJ, "field_name": "Authority", "field_type": "enum", "options": options}
            with self.subTest(options_type=type(options).__name__), patch.object(crm.DealClient, "get", return_value={"data": [row]}), self.assertRaises(crm.DealAdapterError) as caught:
                crm.DealClient("synthetic-token").fields()
            self.assertNotIn(secret, str(caught.exception))

    def test_builtin_option_ids_are_bounded_exact_strings(self):
        for ident in ["", " open", "open\n", "o\tpen", "x" * 129, {}, []]:
            row = {"field_code": "status", "field_name": "Status", "field_type": "enum", "options": [{"id": ident, "label": "Open"}]}
            with patch.object(crm.DealClient, "get", return_value={"data": [row]}), self.assertRaises(crm.DealAdapterError):
                crm.DealClient("synthetic-token").fields()

    def test_option_label_horizontal_tabs_are_preserved_not_normalized(self):
        # Pasted labels can contain tabs even though the option is valid metadata.
        # This must not prevent discovery of unrelated fields or alter identity.
        label = "  Example\t\tChoice\t"
        for code, kind, ident in [(AHJ, "enum", 991), (SECOND, "set", 992), ("status", "enum", "open")]:
            with self.subTest(code=code, kind=kind):
                rows = [
                    {"field_code": code, "field_name": "Choices", "field_type": kind,
                     "options": [{"id": ident, "label": label}]},
                    {"field_code": PERMIT, "field_name": "Permit", "field_type": "varchar"},
                ]
                with patch.object(crm.DealClient, "get", return_value={"data": rows}) as get:
                    fields = crm.DealClient("synthetic-token").fields()
                self.assertEqual(fields[0]["options"], [{"id": ident, "label": label}])
                self.assertEqual(fields[1]["code"], PERMIT)
                self.assertNotIn("\t", json.dumps(fields))
                self.assertIn("\\t", json.dumps(fields))
                self.assertEqual(get.call_count, 1)

    def test_label_tab_support_does_not_allow_blank_or_other_controls(self):
        labels = ["\t", " \t ", "Example\nChoice", "Example\rChoice",
                  "Example\x00Choice", "Example\x1bChoice", "Example\x7fChoice",
                  "Example\u200bChoice", "Example\u2028Choice"]
        for label in labels:
            row = {"field_code": AHJ, "field_name": "Authority", "field_type": "enum",
                   "options": [{"id": 991, "label": label}]}
            with self.subTest(label=repr(label)), patch.object(crm.DealClient, "get", return_value={"data": [row]}), self.assertRaises(crm.DealAdapterError):
                crm.DealClient("synthetic-token").fields()

    def test_metadata_option_counts_are_bounded_per_field_and_across_pages(self):
        option = {"id": 1, "label": "Example"}
        row = {"field_code": AHJ, "field_name": "Authority", "field_type": "enum", "options": [option] * 10_001}
        with patch.object(crm.DealClient, "get", return_value={"data": [row]}), self.assertRaisesRegex(crm.DealAdapterError, "oversized"):
            crm.DealClient("synthetic-token").fields()
        options = [{"id": i, "label": "Example"} for i in range(1, 6001)]
        pages = [
            {"data": [{**row, "options": options}], "additional_data": {"next_cursor": "next"}},
            {"data": [{**row, "field_code": SECOND, "options": options}]},
        ]
        with patch.object(crm.DealClient, "get", side_effect=pages), self.assertRaisesRegex(crm.DealAdapterError, "option-count"):
            crm.DealClient("synthetic-token").fields()

    def test_metadata_field_limit_accepts_boundary_and_rejects_overflow(self):
        rows = [{"field_code": f"{i:040x}", "field_name": "Example", "field_type": "varchar"} for i in range(10_001)]
        for count in [10_000, 10_001]:
            pages = [{"data": rows[start:min(start + 500, count)],
                      "additional_data": {"next_cursor": str(start + 500) if start + 500 < count else None}}
                     for start in range(0, count, 500)]
            with patch.object(crm.DealClient, "get", side_effect=pages) as get:
                if count == 10_000:
                    self.assertEqual(len(crm.DealClient("synthetic-token").fields()), count)
                else:
                    with self.assertRaisesRegex(crm.DealAdapterError, "field-count"):
                        crm.DealClient("synthetic-token").fields()
            self.assertEqual(get.call_count, len(pages))

    def test_metadata_page_limit_stops_even_when_cursors_keep_changing(self):
        pages = [{"data": [], "additional_data": {"next_cursor": str(index)}} for index in range(100)]
        with patch.object(crm.DealClient, "get", side_effect=pages) as get, self.assertRaisesRegex(crm.DealAdapterError, "page-count"):
            crm.DealClient("synthetic-token").fields()
        self.assertEqual(get.call_count, 100)
        pages[-1] = {"data": []}
        with patch.object(crm.DealClient, "get", side_effect=pages) as get:
            self.assertEqual(crm.DealClient("synthetic-token").fields(), [])
        self.assertEqual(get.call_count, 100)

    def test_http_protocol_failures_are_sanitized_at_open_and_read(self):
        secret = "synthetic-sensitive-value"
        client = crm.DealClient("synthetic-token", [101])
        with patch.object(client._opener, "open", side_effect=http.client.BadStatusLine(secret)), self.assertRaises(crm.DealAdapterError) as caught:
            client.get("/api/v2/deals/101")
        self.assertNotIn(secret, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        response = io.BytesIO()
        with patch.object(response, "read", side_effect=http.client.IncompleteRead(secret.encode())), patch.object(client._opener, "open", return_value=response), self.assertRaises(crm.DealAdapterError) as caught:
            client.get("/api/v2/deals/101")
        self.assertNotIn(secret, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_errors_never_expose_response_bodies_urls_or_credentials(self):
        secret = "synthetic-sensitive-value"
        client = crm.DealClient(secret, [101])
        error = urllib.error.HTTPError("https://elsewhere.example/" + secret, 401, secret, {}, io.BytesIO(secret.encode()))
        for response in [error, urllib.error.URLError(secret)]:
            with patch.object(client._opener, "open", side_effect=response), self.assertRaises(crm.DealAdapterError) as caught:
                client.get("/api/v2/deals/101")
            self.assertNotIn(secret, str(caught.exception))
            self.assertNotIn("https://", str(caught.exception))
        for raw in [secret.encode(), json.dumps({"success": False, "error": secret}).encode()]:
            with patch.object(client._opener, "open", return_value=io.BytesIO(raw)), self.assertRaises(crm.DealAdapterError) as caught:
                client.get("/api/v2/deals/101")
            self.assertNotIn(secret, str(caught.exception))

    def test_retry_count_and_delay_are_bounded(self):
        client = crm.DealClient("synthetic-token", [101])
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError("hidden", 503, "hidden", {"Retry-After": "1000"}, None)
        with patch.object(client._opener, "open", side_effect=fail) as opened, patch.object(crm.time, "sleep") as sleep, self.assertRaises(crm.DealAdapterError):
            client.get("/api/v2/deals/101")
        self.assertEqual(opened.call_count, 4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [20, 20, 20])


if __name__ == "__main__":
    unittest.main()
