"""Fictional, offline catalog tests; never load private source workbooks or CRM data."""
import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunbridge.catalog import (
    attach_review, export_catalog, init_catalog, reconcile_organizations,
    search_catalog, show_entity,
)
from sunbridge.validation import ROOT


def entity(ident="ahj-one", *, kind="building_department", name="Example City", states=None,
           source_identifiers=None, identity_status="source_id"):
    return {"entity_id": ident, "kind": kind, "name": name, "states": states or ["FL"],
            "source_identifiers": source_identifiers if source_identifiers is not None else {"geo_id": "1234"},
            "identity_status": identity_status, "aliases": [{"name": name, "state": "FL"}],
            "source_refs": [{"sheet": "Fictional Requirements", "row": 2}]}


def benchmark(ident="permit-benchmark", *, entity_id="ahj-one", metric="ahj_permit", value=0,
              values=None, state="FL", status="reported"):
    return {"benchmark_id": ident, "entity_id": entity_id, "state": state, "year": 2024,
            "size_band": "0-10kW", "technology": "PV Only", "metric": metric,
            "unit": "business_days", "statistic": "median", "value": value,
            "values": [value] if values is None else values, "status": status, "sample_n": None,
            "source_refs": [{"sheet": "Fictional Timelines", "row": 2, "column": 6, "value": value}],
            "unknown_references_count": 1, "flags": ["fictional_training_data"]}


def snapshot(digest="a" * 64, version="fictional-v1"):
    return {"source": {"dataset_id": "solartrace", "version": version, "source_sha256": digest,
                       "source_url": "https://example.invalid/fictional-source"},
            "entities": [entity(), entity("utility-one", kind="utility_company", name="Example Power",
                                          states=["FL", "GA"], source_identifiers={"eia_id": "77"})],
            "requirements": [{"entity_id": "ahj-one", "state": "FL", "source_sheet": "Fictional Requirements",
                              "source_row": 2, "fields": {"Source requirement": "NA", "Original numeric zero": 0}}],
            "benchmarks": [benchmark(), benchmark("ix-conflict", entity_id="utility-one", metric="pre_install_ix",
                                                   value=None, values=[0, 2], status="conflict"),
                           benchmark("ga-ix", entity_id="utility-one", metric="pre_install_ix", state="GA", value=4)],
            "installations": [{"ahj_id": "ahj-one", "utility_id": "utility-one", "state": "FL", "year": 2024,
                               "size_band": "0-10kW", "technology": "PV Only", "count": 12, "source_row": 2, "column": 5}],
            "source_rows": [{"sheet": "Fictional Timelines", "row": 2, "values": ["FL", "Example City", 1234, "NA", 0, None]}],
            "stats": {"fixture": True}}


def report():
    return {"mode": "review_only", "crm_writes": 0, "items": [
        {"input_position": 1, "event": {"ahj_id": "fictional-profile", "event_type": "permit_issued",
         "permit_id": "DEMO-001-R2", "review_required": True}, "original_message": {"body": "Fictional evidence"}}
    ]}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "private").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="catalog-test-", dir=ROOT / "private")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.db = self.folder / "catalog.sqlite"
        self.no_network = patch("socket.socket", side_effect=AssertionError("Catalog must stay offline"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def sql(self, query, params=()):
        connection = sqlite3.connect(self.db)
        try:
            with connection:
                return connection.execute(query, params).fetchall()
        finally:
            connection.close()

    def test_initialization_idempotency_source_history_and_explicit_reactivation(self):
        original = snapshot()
        first = init_catalog(self.db, original)
        self.assertEqual(first["status"], "imported")
        self.assertEqual(first["counts"]["entities"], 2)
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        self.assertEqual(init_catalog(self.db, original)["status"], "already_present")
        newer = snapshot("b" * 64, "fictional-v2")
        newer["entities"][0]["name"] = "Revised source name"
        self.assertEqual(init_catalog(self.db, newer)["source_versions"], 2)
        self.assertEqual(show_entity(self.db, "ahj-one")["entity"]["name"], "Revised source name")
        init_catalog(self.db, original)
        self.assertEqual(show_entity(self.db, "ahj-one")["entity"]["name"], "Example City")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM sources"), [(2,)])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM entities"), [(4,)])

    def test_values_conflicts_scope_and_raw_source_cells_survive_without_averaging(self):
        original = snapshot()
        original["benchmarks"].append(benchmark("unknown", metric="inspection", value=None, values=[]))
        init_catalog(self.db, original)
        shown = show_entity(self.db, "utility-one")
        by_id = {item["benchmark_id"]: item for item in shown["benchmarks"]}
        self.assertIsNone(by_id["ix-conflict"]["value"])
        self.assertEqual(by_id["ix-conflict"]["values"], [0, 2])
        self.assertEqual(by_id["ga-ix"]["state"], "GA")
        ahj = show_entity(self.db, "ahj-one")
        self.assertEqual(ahj["benchmarks"][0]["value"], 0)
        self.assertTrue(all(item["sample_n"] is None for item in ahj["benchmarks"]))
        stored = json.loads(self.sql("SELECT payload_json FROM source_rows")[0][0])
        self.assertEqual(stored["values"], ["FL", "Example City", 1234, "NA", 0, None])
        self.assertEqual(ahj["requirements"][0]["fields"], original["requirements"][0]["fields"])

    def test_read_queries_filters_exports_and_sql_punctuation_are_literal(self):
        original = snapshot()
        original["entities"][0]["aliases"].append({"name": "Former Example", "state": "FL"})
        init_catalog(self.db, original)
        before = self.db.read_bytes()
        self.assertEqual(search_catalog(self.db, "former", state="fl")[0]["entity_id"], "ahj-one")
        self.assertEqual(len(search_catalog(self.db, state="GA")), 1)
        self.assertEqual(search_catalog(self.db, kind="utility_company")[0]["entity_id"], "utility-one")
        self.assertEqual(search_catalog(self.db, "' OR 1=1; --"), [])
        exported = export_catalog(self.db, state="FL")
        self.assertEqual(len(exported["organizations"]), 2)
        self.assertEqual({item["state"] for item in exported["benchmarks"]}, {"FL"})
        self.assertNotIn("proposed_events", exported)
        self.assertEqual(self.db.read_bytes(), before)
        for kwargs in ({"limit": True}, {"limit": 0}, {"limit": 1001}, {"kind": "installer"}, {"state": ""}):
            with self.assertRaises(ValueError):
                search_catalog(self.db, **kwargs)

    def test_paths_are_private_uri_escaped_and_invalid_files_are_not_modified(self):
        for path in (ROOT / "catalog.sqlite", ROOT / "private", ROOT / "private/../catalog.sqlite"):
            with self.assertRaises(ValueError):
                init_catalog(path, snapshot())
        odd = self.folder / "catalog ?#%.sqlite"
        init_catalog(odd, snapshot())
        self.assertEqual(len(search_catalog(odd)), 2)
        link = self.folder / "linked.sqlite"
        link.symlink_to(odd)
        with self.assertRaises(ValueError):
            search_catalog(link)
        linked_parent = self.folder / "alias"
        linked_parent.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(ValueError):
            search_catalog(linked_parent / odd.name)
        self.db.write_bytes(b"not a SQLite database; keep unchanged")
        self.db.chmod(0o600)
        original = self.db.read_bytes()
        with self.assertRaises(ValueError):
            init_catalog(self.db, snapshot())
        self.assertEqual(self.db.read_bytes(), original)
        self.assertFalse(any(path.name.startswith(".sunbridge-catalog-") for path in self.folder.iterdir()))

    def test_world_readable_hard_linked_and_foreign_schema_databases_are_rejected(self):
        init_catalog(self.db, snapshot())
        self.db.chmod(0o644)
        with self.assertRaises(ValueError):
            search_catalog(self.db)
        self.db.chmod(0o600)
        link = self.folder / "hard.sqlite"
        os.link(self.db, link)
        with self.assertRaises(ValueError):
            init_catalog(self.db, snapshot("b" * 64, "fictional-v2"))
        link.unlink()
        self.sql("CREATE TABLE surprise (payload TEXT)")
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            init_catalog(self.db, snapshot("b" * 64, "fictional-v2"))
        self.assertEqual(self.db.read_bytes(), before)

    def test_failed_creation_is_atomic_and_does_not_replace_a_racing_target(self):
        with patch("sunbridge.catalog._insert_snapshot", side_effect=ValueError("synthetic failure")):
            with self.assertRaises(ValueError):
                init_catalog(self.db, snapshot())
        self.assertFalse(self.db.exists())
        self.assertEqual(list(self.folder.iterdir()), [])
        def raced_link(source, target):
            Path(target).write_bytes(b"independent file")
            raise FileExistsError()
        with patch("sunbridge.catalog.os.link", side_effect=raced_link):
            with self.assertRaises(ValueError):
                init_catalog(self.db, snapshot())
        self.assertEqual(self.db.read_bytes(), b"independent file")

    def test_invalid_snapshots_do_not_create_or_mutate_catalogs(self):
        init_catalog(self.db, snapshot())
        before = self.db.read_bytes()
        invalid = []
        for key, value in (("source_sha256", "bad"), ("dataset_id", "other")):
            row = snapshot("b" * 64, "fictional-v2")
            row["source"][key] = value
            invalid.append(row)
        for key, value in (("sample_n", 12), ("entity_id", "utility-one"), ("value", float("nan"))):
            row = snapshot("b" * 64, "fictional-v2")
            row["benchmarks"][0][key] = value
            invalid.append(row)
        duplicate = snapshot("b" * 64, "fictional-v2")
        duplicate["entities"].append(copy.deepcopy(duplicate["entities"][0]))
        invalid.append(duplicate)
        for value in invalid:
            with self.assertRaises(ValueError):
                init_catalog(self.db, value)
            self.assertEqual(self.db.read_bytes(), before)

    def test_reconciliation_uses_opaque_identifiers_state_and_kind_without_name_fallback(self):
        init_catalog(self.db, snapshot())
        base = {"organization_id": "fictional-org", "kind": "building_department", "name": "Example City", "state": "FL"}
        records = [{**base, "geo_id": "1234"}, base, {**base, "geo_id": "01234"},
                   {**base, "geo_id": "unknown"}, {**base, "state": None},
                   {**base, "kind": "utility_company", "name": "Example Power", "eia_id": "77", "state": "GA"},
                   {**base, "kind": "utility_company", "eia_id": "77", "state": None},
                   {**base, "geo_id": 1234}, {**base, "eia_id": "77"}]
        plan = reconcile_organizations(self.db, records)
        self.assertEqual([row["status"] for row in plan["items"]], ["exact_identifier_candidate", "name_candidate", "unmatched", "unmatched", "held", "exact_identifier_candidate", "held", "held", "held"])
        self.assertEqual(plan["crm_writes"], 0)
        self.assertTrue(all(row["review_required"] for row in plan["items"]))
        self.assertIn("no_name_fallback", plan["items"][3]["issues"][0])

    def test_ambiguous_and_unresolved_entities_never_become_exact_matches(self):
        original = snapshot()
        original["entities"] += [entity("duplicate", name="Example City"),
                                 entity("unresolved", name="Mystery City", source_identifiers={"geo_id": "5678"}, identity_status="unresolved")]
        init_catalog(self.db, original)
        base = {"organization_id": 1, "kind": "building_department", "name": "Example City", "state": "FL"}
        plan = reconcile_organizations(self.db, [{**base, "geo_id": "1234"}, base, {**base, "geo_id": "5678", "name": "Mystery City"}])
        self.assertEqual([item["status"] for item in plan["items"]], ["ambiguous", "ambiguous", "unmatched"])

    def test_native_pipedrive_inventory_needs_explicit_kind_and_jurisdiction_state_projection(self):
        from sunbridge.pipedrive import discover_metadata_fields, project_organization
        type_field = {"field_code": "fictional_type", "field_name": "Type", "field_type": "enum",
                      "options": [{"id": 1, "label": "Building Department"}]}
        state_field = {"field_code": "fictional_state", "field_name": "Jurisdiction State", "field_type": "enum",
                       "options": [{"id": 2, "label": "Florida"}]}
        office_field = {"field_code": "address_admin_area_level_1", "field_name": "State", "field_type": "varchar"}
        fields = discover_metadata_fields([type_field, state_field, office_field], type_field)
        raw = project_organization({"id": 71, "name": "Example City",
            "custom_fields": {"fictional_type": 1, "fictional_state": 2},
            "address_admin_area_level_1": "GA"}, type_field, fields)
        init_catalog(self.db, snapshot())
        self.assertEqual(reconcile_organizations(self.db, [raw])["items"][0]["status"], "held")
        # This explicit, fictional mapping represents an operator-reviewed projection,
        # not an implemented automatic Pipedrive inventory conversion.
        state_map = {"Florida": "FL"}
        kind_map = {"Building Department": "building_department"}
        normalized = {"organization_id": raw["crm"]["organization_id"], "name": raw["organization_name"],
                      "kind": kind_map[raw["organization_type"]], "state": state_map[raw["metadata"]["state"]]}
        candidate = reconcile_organizations(self.db, [normalized])["items"][0]
        self.assertEqual(candidate["status"], "name_candidate")
        self.assertEqual(candidate["candidates"], ["ahj-one"])
        self.assertNotIn("geo_id", normalized)
        self.assertTrue(candidate["review_required"])
        missing_state = {**normalized, "state": None}
        self.assertEqual(reconcile_organizations(self.db, [missing_state])["items"][0]["status"], "held")

    def test_review_attachments_are_idempotent_and_do_not_change_baselines_or_annotations(self):
        init_catalog(self.db, snapshot())
        self.sql("INSERT INTO operator_annotations(source_id,entity_id,payload_json) VALUES (1,?,?)", ("ahj-one", '{"note":"Fictional operator observation"}'))
        baseline = export_catalog(self.db)
        original = report()
        links = {"fictional-profile": "ahj-one"}
        result = attach_review(self.db, original, links)
        self.assertEqual(result["attached"], 1)
        self.assertEqual(attach_review(self.db, original, links)["already_present"], 1)
        stored = show_entity(self.db, "ahj-one")["proposed_events"]
        self.assertEqual(stored[0]["proposal"]["event"]["permit_id"], "DEMO-001-R2")
        self.assertTrue(stored[0]["proposal"]["event"]["review_required"])
        self.assertEqual(export_catalog(self.db), baseline)
        init_catalog(self.db, snapshot("b" * 64, "fictional-v2"))
        self.assertEqual(len(show_entity(self.db, "ahj-one")["proposed_events"]), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM operator_annotations"), [(1,)])

    def test_attachment_validation_is_all_or_nothing_and_crosswalk_cannot_be_reassigned(self):
        original = snapshot()
        original["entities"].append(entity("ahj-two", name="Second City", source_identifiers={"geo_id": "5678"}))
        init_catalog(self.db, original)
        invalid = report()
        invalid["items"].append({"input_position": 2, "event": {"ahj_id": "unmapped", "review_required": True}})
        for value, links in ((invalid, {"fictional-profile": "ahj-one"}), (report(), {"fictional-profile": "utility-one"}),
                             ({**report(), "crm_writes": True}, {"fictional-profile": "ahj-one"}),
                             ({**report(), "mode": "write"}, {"fictional-profile": "ahj-one"})):
            with self.assertRaises(ValueError):
                attach_review(self.db, value, links)
            self.assertEqual(self.sql("SELECT COUNT(*) FROM proposed_events"), [(0,)])
            self.assertEqual(self.sql("SELECT COUNT(*) FROM review_reports"), [(0,)])
        attach_review(self.db, report(), {"fictional-profile": "ahj-one"})
        with self.assertRaises(ValueError):
            attach_review(self.db, report(), {"fictional-profile": "ahj-two"})
        self.assertEqual(self.sql("SELECT entity_id FROM proposed_events"), [("ahj-one",)])

    def test_malformed_collections_and_unsafe_review_rows_fail_without_partial_data(self):
        for field in ("entities", "requirements", "benchmarks", "installations", "source_rows"):
            value = snapshot()
            value[field] = "not a collection"
            with self.assertRaises(ValueError):
                init_catalog(self.db, value)
        value = snapshot()
        value["entities"][0]["kind"] = []
        with self.assertRaises(ValueError):
            init_catalog(self.db, value)
        init_catalog(self.db, snapshot())
        invalid = []
        value = report()
        value["items"][0]["event"]["review_required"] = False
        invalid.append(value)
        value = report()
        value["items"].append(copy.deepcopy(value["items"][0]))
        invalid.append(value)
        value = report()
        value["items"][0]["input_position"] = True
        invalid.append(value)
        for value in invalid:
            with self.assertRaises(ValueError):
                attach_review(self.db, value, {"fictional-profile": "ahj-one"})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM review_reports"), [(0,)])
        oversized = report()
        oversized["extra"] = "x" * 1000
        from sunbridge.catalog import _json
        with self.assertRaises(ValueError):
            _json(oversized, limit=100)

    def test_empty_ahj_is_skipped_but_report_is_retained_and_database_version_is_checked(self):
        init_catalog(self.db, snapshot())
        value = report()
        value["items"][0]["event"]["ahj_id"] = ""
        result = attach_review(self.db, value, {})
        self.assertEqual(result["attached"], 0)
        self.assertEqual(result["skipped_empty_ahj"], 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM review_reports"), [(1,)])
        self.sql("PRAGMA user_version=99")
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            search_catalog(self.db)
        with self.assertRaises(ValueError):
            init_catalog(self.db, snapshot())
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
