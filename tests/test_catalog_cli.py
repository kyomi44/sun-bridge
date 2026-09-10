"""Catalog CLI integration tests using a tiny fictional, fully offline snapshot."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunbridge.__main__ import main
from sunbridge.catalog import export_catalog, show_entity


def tiny_snapshot():
    def entity(ident, kind, name, states, identifiers):
        return {"entity_id": ident, "kind": kind, "name": name, "states": states,
                "source_identifiers": identifiers, "identity_status": "source_id",
                "aliases": [{"name": name, "state": state} for state in states],
                "source_refs": [{"sheet": "Fictional Requirements", "row": 2}]}

    def benchmark(ident, entity_id, state, metric, value):
        return {"benchmark_id": ident, "entity_id": entity_id, "state": state, "year": 2024,
                "size_band": "0-10kW", "technology": "PV Only", "metric": metric,
                "unit": "business_days", "statistic": "median", "value": value,
                "values": [value], "status": "reported", "sample_n": None,
                "source_refs": [{"sheet": "Fictional Timelines", "row": 2, "column": 6, "value": value}],
                "unknown_references_count": 0, "flags": ["fictional_fixture"]}

    return {
        "source": {"dataset_id": "solartrace", "version": "fictional-cli-v1", "source_sha256": "a" * 64,
                   "source_url": "https://example.invalid/fictional-source",
                   "license_notice": "Fictional source license notice. Test data only."},
        "entities": [entity("ahj-example", "building_department", "Example City", ["FL"], {"geo_id": "1234"}),
                     entity("utility-example", "utility_company", "Example Power", ["FL", "GA"], {"eia_id": "77"})],
        "requirements": [{"entity_id": "ahj-example", "state": "FL", "source_sheet": "Fictional Requirements",
                          "source_row": 2, "fields": {"Original unknown": "NA", "Original zero": 0}}],
        "benchmarks": [benchmark("ahj-permit", "ahj-example", "FL", "ahj_permit", 0),
                       benchmark("utility-ix", "utility-example", "GA", "pre_install_ix", 4)],
        "installations": [],
        "source_rows": [{"sheet": "Fictional Timelines", "row": 2, "values": ["FL", "Example City", "NA", 0, None]}],
        "stats": {"fictional_fixture": True},
    }


class CatalogCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sunbridge-catalog-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private = self.root / "private"
        self.private.mkdir()
        self.db = self.private / "catalog/sunbridge.sqlite"
        for target in ("sunbridge.__main__.ROOT", "sunbridge.privateio.ROOT"):
            patched = patch(target, self.root)
            patched.start()
            self.addCleanup(patched.stop)
        no_network = patch("socket.socket", side_effect=AssertionError("Catalog CLI attempted network access"))
        self.network = no_network.start()
        self.addCleanup(no_network.stop)
        no_crm = patch("sunbridge.crm.import_deal_permits", side_effect=AssertionError("Catalog CLI accessed CRM deals"))
        self.crm = no_crm.start()
        self.addCleanup(no_crm.stop)
        no_orgs = patch("sunbridge.pipedrive.import_building_departments", side_effect=AssertionError("Catalog CLI accessed CRM organizations"))
        self.organizations = no_orgs.start()
        self.addCleanup(no_orgs.stop)

    @staticmethod
    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @staticmethod
    def cli(*arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = main(list(arguments))
            except SystemExit as error:
                code = error.code
        return code, out.getvalue(), err.getvalue()

    def initialize(self):
        bundle = {"fictional_bundle": True}
        with patch("sunbridge.solartrace.load_bundle", return_value=bundle) as load, patch("sunbridge.solartrace.normalize_snapshot", return_value=tiny_snapshot()) as normalize:
            code, out, err = self.cli("catalog", "init")
        self.assertEqual(code, 0, err)
        load.assert_called_once_with()
        normalize.assert_called_once_with(bundle)
        return out

    def test_init_search_show_and_state_filtered_export_use_default_private_database(self):
        self.initialize()
        self.assertTrue(self.db.is_file())
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        code, out, err = self.cli("catalog", "search", "--state", "FL", "--kind", "building_department", "--query", "Example City")
        self.assertEqual(code, 0, err)
        self.assertIn("ahj-example", out)
        self.assertNotIn("utility-example", out)
        code, out, err = self.cli("catalog", "show", "--id", "ahj-example")
        self.assertEqual(code, 0, err)
        self.assertIn("business_days", out)
        self.assertIn("median", out)
        output = self.private / "catalog-export"
        code, _, err = self.cli("catalog", "export", "--state", "FL", "--output", str(output))
        self.assertEqual(code, 0, err)
        self.assertEqual({path.name for path in output.iterdir()},
                         {"organizations.json", "benchmarks.json", "requirements.json", "source.json", "NOTICE.txt"})
        organizations = json.loads((output / "organizations.json").read_text())
        self.assertEqual({row["entity_id"] for row in organizations}, {"ahj-example", "utility-example"})
        benchmarks = json.loads((output / "benchmarks.json").read_text())
        self.assertEqual([row["state"] for row in benchmarks], ["FL"])
        self.assertEqual(benchmarks[0]["value"], 0)
        self.assertIsNone(benchmarks[0]["sample_n"])
        requirements = json.loads((output / "requirements.json").read_text())
        self.assertEqual(requirements[0]["fields"], {"Original unknown": "NA", "Original zero": 0})
        self.assertEqual(json.loads((output / "source.json").read_text())["source_sha256"], "a" * 64)
        self.assertIn("Fictional source license notice", (output / "NOTICE.txt").read_text())
        for path in output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.network.assert_not_called()
        self.crm.assert_not_called()
        self.organizations.assert_not_called()

    def test_reconcile_writes_candidates_only_and_preserves_opaque_source_identifiers(self):
        self.initialize()
        records = [{"organization_id": "crm-example-1", "name": "Example City", "kind": "building_department", "state": "FL", "geo_id": "1234"},
                   {"organization_id": "crm-example-2", "name": "Example City", "kind": "building_department", "state": "FL", "geo_id": "01234"}]
        source = self.save(self.private / "organizations.json", records)
        output = self.private / "reconciliation"
        baseline = self.db.read_bytes()
        code, _, err = self.cli("catalog", "reconcile", "--organizations", str(source), "--output", str(output))
        self.assertEqual(code, 0, err)
        review = json.loads((output / "review.json").read_text())
        self.assertEqual(review["mode"], "review_only")
        self.assertEqual(review["crm_writes"], 0)
        self.assertEqual([row["status"] for row in review["items"]], ["exact_identifier_candidate", "unmatched"])
        self.assertTrue(all(row["review_required"] for row in review["items"]))
        self.assertEqual(json.loads(source.read_text()), records)
        self.assertEqual(self.db.read_bytes(), baseline)
        self.assertEqual((output / "review.json").stat().st_mode & 0o777, 0o600)

    def test_attach_review_uses_explicit_links_and_does_not_rewrite_historical_data(self):
        self.initialize()
        report = {"mode": "review_only", "crm_writes": 0, "items": [{"input_position": 1,
                  "event": {"ahj_id": "fictional-profile", "event_type": "permit_issued", "permit_id": "DEMO-001",
                            "review_required": True}, "original_message": {"body": "Fictional private evidence"}}]}
        report_path = self.save(self.private / "event-review.json", report)
        links = self.save(self.private / "catalog-links.json", {"fictional-profile": "ahj-example"})
        baseline = copy.deepcopy(export_catalog(self.db))
        code, _, err = self.cli("catalog", "attach-review", "--report", str(report_path), "--links", str(links))
        self.assertEqual(code, 0, err)
        proposals = show_entity(self.db, "ahj-example")["proposed_events"]
        self.assertEqual(len(proposals), 1)
        self.assertTrue(proposals[0]["proposal"]["event"]["review_required"])
        self.assertEqual(proposals[0]["proposal"]["event"]["permit_id"], "DEMO-001")
        self.assertEqual(export_catalog(self.db), baseline)
        self.assertEqual(json.loads(report_path.read_text()), report)
        code, _, err = self.cli("catalog", "attach-review", "--report", str(report_path), "--links", str(links))
        self.assertEqual(code, 0, err)
        self.assertEqual(len(show_entity(self.db, "ahj-example")["proposed_events"]), 1)

    def test_import_workbook_uses_explicit_local_source_and_retains_source_versions(self):
        self.initialize()
        workbook = self.private / "fictional-workbook.xlsx"
        workbook.write_bytes(b"Fictional workbook bytes; parser is mocked for this CLI wiring test.")
        original = workbook.read_bytes()
        snapshot = tiny_snapshot()
        snapshot["source"].update(version="fictional-cli-v2", source_sha256="b" * 64)
        snapshot["benchmarks"][0]["value"] = 3
        snapshot["benchmarks"][0]["values"] = [3]
        bundle = {"fictional_workbook": True}
        with patch("sunbridge.solartrace.read_workbook", return_value=bundle) as read, patch("sunbridge.solartrace.normalize_snapshot", return_value=snapshot) as normalize, patch("sunbridge.solartrace.load_bundle", side_effect=AssertionError("Explicit import must not use the bundle")) as load:
            code, out, err = self.cli("catalog", "import-workbook", "--input", str(workbook))
        self.assertEqual(code, 0, err)
        read.assert_called_once_with(workbook)
        normalize.assert_called_once_with(bundle)
        load.assert_not_called()
        result = json.loads(out)
        self.assertEqual(result["source_versions"], 2)
        self.assertEqual(result["active_source_sha256"], "b" * 64)
        self.assertEqual(export_catalog(self.db)["benchmarks"][0]["value"], 3)
        self.assertEqual(workbook.read_bytes(), original)
        self.network.assert_not_called()
        self.crm.assert_not_called()
        self.organizations.assert_not_called()

    def test_workbook_database_collision_is_refused_before_reading_or_normalizing(self):
        self.initialize()
        baseline = self.db.read_bytes()
        alias = self.private / "database-alias.xlsx"
        os.link(self.db, alias)
        for source in (self.db, alias):
            with self.subTest(source=source.name), patch("sunbridge.solartrace.read_workbook", side_effect=AssertionError("Source collision must fail before parsing")) as read, patch("sunbridge.solartrace.normalize_snapshot") as normalize:
                code, _, _ = self.cli("catalog", "import-workbook", "--input", str(source))
            self.assertNotEqual(code, 0)
            read.assert_not_called()
            normalize.assert_not_called()
            self.assertEqual(self.db.read_bytes(), baseline)
            self.assertEqual(alias.read_bytes(), baseline)

    def test_export_missing_attribution_fails_before_creating_output(self):
        snapshot = tiny_snapshot()
        snapshot["source"].pop("license_notice")
        with patch("sunbridge.solartrace.load_bundle", return_value={}), patch("sunbridge.solartrace.normalize_snapshot", return_value=snapshot):
            code, _, err = self.cli("catalog", "init")
        self.assertEqual(code, 0, err)
        baseline = self.db.read_bytes()
        output = self.private / "unattributed-export"
        code, _, err = self.cli("catalog", "export", "--output", str(output))
        self.assertNotEqual(code, 0)
        self.assertIn("attribution", err)
        self.assertFalse(output.exists())
        self.assertEqual(self.db.read_bytes(), baseline)

    def test_attach_review_invalid_crosswalk_and_source_collision_leave_database_unchanged(self):
        self.initialize()
        report = {"mode": "review_only", "crm_writes": 0, "items": [{"input_position": 1,
                  "event": {"ahj_id": "fictional-profile", "event_type": "permit_issued", "review_required": True}}]}
        report_path = self.save(self.private / "event-review.json", report)
        links = self.save(self.private / "catalog-links.json", {"fictional-profile": "utility-example"})
        baseline = self.db.read_bytes()
        code, _, _ = self.cli("catalog", "attach-review", "--report", str(report_path), "--links", str(links))
        self.assertNotEqual(code, 0)
        self.assertEqual(self.db.read_bytes(), baseline)
        self.assertEqual(show_entity(self.db, "ahj-example")["proposed_events"], [])
        for source_flag in ("--report", "--links"):
            arguments = {"--report": report_path, "--links": links}
            arguments[source_flag] = self.db
            with self.subTest(source_flag=source_flag), patch("sunbridge.catalog.attach_review", side_effect=AssertionError("Source collision must fail before attaching")) as attach:
                code, _, _ = self.cli("catalog", "attach-review", "--report", str(arguments["--report"]), "--links", str(arguments["--links"]))
            self.assertNotEqual(code, 0)
            attach.assert_not_called()
            self.assertEqual(self.db.read_bytes(), baseline)
        self.assertEqual(json.loads(report_path.read_text()), report)

    def test_missing_catalog_unknown_entity_and_malformed_input_fail_without_remote_or_output_writes(self):
        output = self.private / "missing-db-export"
        code, _, _ = self.cli("catalog", "export", "--output", str(output))
        self.assertNotEqual(code, 0)
        self.assertFalse(self.db.exists())
        self.assertFalse(output.exists())
        self.initialize()
        baseline = self.db.read_bytes()
        code, _, _ = self.cli("catalog", "show", "--id", "does-not-exist")
        self.assertNotEqual(code, 0)
        malformed = self.save(self.private / "malformed-organizations.json", {"not": "an array"})
        output = self.private / "invalid-reconciliation"
        code, _, _ = self.cli("catalog", "reconcile", "--organizations", str(malformed), "--output", str(output))
        self.assertNotEqual(code, 0)
        self.assertFalse(output.exists())
        self.assertEqual(self.db.read_bytes(), baseline)
        self.network.assert_not_called()
        self.crm.assert_not_called()
        self.organizations.assert_not_called()

    def test_reconciliation_source_output_collision_is_refused_before_reconciliation(self):
        self.initialize()
        output = self.private / "source-collision"
        records = [{"organization_id": "example-1", "name": "Example City", "kind": "building_department", "state": "FL"}]
        source = self.save(output / "review.json", records)
        original = source.read_bytes()
        with patch("sunbridge.catalog.reconcile_organizations", side_effect=AssertionError("Collision should fail preflight")) as reconcile:
            code, _, _ = self.cli("catalog", "reconcile", "--organizations", str(source), "--output", str(output))
        self.assertNotEqual(code, 0)
        reconcile.assert_not_called()
        self.assertEqual(source.read_bytes(), original)

    def test_export_symlink_and_database_hard_link_are_refused_without_changing_sources(self):
        self.initialize()
        baseline = self.db.read_bytes()
        protected = self.private / "protected.txt"
        protected.write_text("preserve", encoding="utf-8")
        for kind in ("symlink", "database-hard-link"):
            output = self.private / kind
            output.mkdir()
            target = output / "source.json"
            if kind == "symlink":
                target.symlink_to(protected)
            else:
                os.link(self.db, target)
            with patch("sunbridge.catalog.export_catalog", side_effect=AssertionError("Unsafe target should fail preflight")) as exporter:
                code, _, _ = self.cli("catalog", "export", "--output", str(output))
            self.assertNotEqual(code, 0)
            exporter.assert_not_called()
            self.assertEqual([path.name for path in output.iterdir()], ["source.json"])
            self.assertEqual(protected.read_text(), "preserve")
            self.assertEqual(self.db.read_bytes(), baseline)
            target.unlink()


if __name__ == "__main__":
    unittest.main()
