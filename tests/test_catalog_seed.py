"""Offline release check of the actual public derivative, not a mock catalog."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunbridge.catalog import export_catalog, init_catalog, search_catalog, show_entity
from sunbridge.solartrace import BUNDLE_DIR, SOURCE_SHA256, load_bundle, normalize_snapshot
from sunbridge.validation import ROOT


class BundledSeedTests(unittest.TestCase):
    def test_reviewed_seed_initializes_searches_and_exports_with_exact_provenance(self):
        with patch("socket.socket", side_effect=AssertionError("Bundled catalog must stay offline")):
            snapshot = normalize_snapshot(load_bundle())
            manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["stats"], manifest["stats"])
            self.assertEqual(snapshot["stats"]["building_department_identified"], 11662)
            self.assertEqual(snapshot["stats"]["utility_company_identified"], 1004)
            self.assertEqual(snapshot["stats"]["benchmarks"], 28455)
            self.assertEqual(snapshot["stats"]["unassigned_numeric_timeline_source_cells"], 20)
            (ROOT / "private").mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="seed-test-", dir=ROOT / "private") as folder:
                db = Path(folder) / "catalog.sqlite"
                result = init_catalog(db, snapshot)
                self.assertEqual(result["active_source_sha256"], SOURCE_SHA256)
                self.assertEqual(result["counts"]["source_rows"], 22322)
                match = search_catalog(db, "Cape Coral", state="FL", kind="building_department")
                self.assertEqual([row["entity_id"] for row in match], ["ahj:FL:1210275"])
                shown = show_entity(db, match[0]["entity_id"])
                self.assertTrue(shown["requirements"])
                self.assertTrue(shown["benchmarks"])
                self.assertFalse(shown["proposed_events"])
                exported = export_catalog(db, state="FL")
                self.assertEqual(len(exported["organizations"]), 422)
                self.assertEqual(len(exported["benchmarks"]), 1843)
                self.assertEqual(len(exported["requirements"]), 347)
                self.assertEqual(exported["source"]["license_notice"], (BUNDLE_DIR / "NOTICE.txt").read_text(encoding="utf-8"))
                self.assertTrue(all(row["state"] == "FL" for row in exported["benchmarks"]))


if __name__ == "__main__":
    unittest.main()
