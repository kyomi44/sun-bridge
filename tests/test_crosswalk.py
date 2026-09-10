"""Offline checks for registry-to-catalog link proposals and table search output.

Every name, identifier, and state below is synthetic. No private data is read.
"""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunbridge.__main__ import main
from sunbridge.crosswalk import propose_registry_links, reconcile_coverage, registry_search_terms


def entity(ident, kind, name, states, *, identity_status="source_id"):
    key = "geo_id" if kind == "building_department" else "eia_id"
    identifiers = {key: ident.rsplit(":", 1)[-1]} if identity_status == "source_id" else {}
    return {"entity_id": ident, "kind": kind, "name": name, "states": states,
            "source_identifiers": identifiers, "identity_status": identity_status,
            "aliases": [{"name": name, "state": state} for state in states],
            "source_refs": [{"sheet": "Fictional Requirements", "row": 2}]}


def entities():
    return [
        entity("ahj:FL:1", "building_department", "Example Coral city", ["FL"]),
        entity("ahj:FL:2", "building_department", "Lee County", ["FL"]),
        entity("ahj:GA:3", "building_department", "Lee County", ["GA"]),
        entity("utility:9", "utility_company", "Lee County", ["FL"]),
        entity("ahj:FL:4", "building_department", "Palm Springs village", ["FL"]),
        entity("ahj:CA:5", "building_department", "Palm Springs city", ["CA"]),
        entity("ahj:FL:6", "building_department", "Plant City city", ["FL"]),
        entity("ahj:FL:7", "building_department", "Miami-Dade County", ["FL"]),
        entity("ahj:MI:8", "building_department", "Lee township (Midland County)", ["MI"]),
        entity("ahj:PA:10", "building_department", "Pittsburgh city", ["PA"]),
        entity("ahj:unresolved:abc", "building_department", "Example Shore city", ["FL"], identity_status="unresolved"),
    ]


def registry(*entries):
    def row(ident, name, note="none", pilot=()):
        return {"id": ident, "name": name, "candidate_signals": ["inspection"],
                "pilot_events": list(pilot), "identity_note": note}
    return {
        "schema_version": "v1", "evidence_reviewed_on": "2026-02-01",
        "evidence_basis": "historical_private_review", "identity_status": "provisional",
        "public_runtime": "not_enabled",
        "entries": [row(*item) if isinstance(item, tuple) else row(item, item.replace("-", " ").title()) for item in entries],
    }


def by_id(report):
    return {item["id"]: item for item in report["items"]}


class SearchTermTests(unittest.TestCase):
    def test_only_explicit_state_suffix_and_legal_prefix_are_read(self):
        self.assertEqual(registry_search_terms("Apopka, FL"), ("Apopka", "FL", None))
        self.assertEqual(registry_search_terms("Natrona County, WY"), ("Natrona County", "WY", None))
        self.assertEqual(registry_search_terms("Village of Palm Springs"), ("Palm Springs", None, "village"))
        self.assertEqual(registry_search_terms("Plant City"), ("Plant City", None, None))
        self.assertEqual(registry_search_terms("Lee County"), ("Lee County", None, None))
        self.assertEqual(registry_search_terms("  Miami-Dade  "), ("Miami-Dade", None, None))
        # A lowercase or three-letter suffix is part of the name, not a state code.
        self.assertEqual(registry_search_terms("Somewhere, fl"), ("Somewhere, fl", None, None))
        self.assertEqual(registry_search_terms("Somewhere, USA"), ("Somewhere, USA", None, None))


class ProposalTests(unittest.TestCase):
    def test_exact_and_place_name_candidates_are_labelled_and_inputs_unchanged(self):
        data = registry(("example-coral", "Example Coral"), ("miami-dade", "Miami-Dade"),
                        ("plant-city", "Plant City"), ("lee-county", "Lee County"))
        rows = entities()
        snapshot = (copy.deepcopy(data), copy.deepcopy(rows))
        report = propose_registry_links(data, rows)
        self.assertEqual((data, rows), snapshot)
        self.assertEqual(report["mode"], "review_only")
        self.assertEqual((report["crm_writes"], report["registry_writes"], report["catalog_writes"]), (0, 0, 0))
        items = by_id(report)
        coral = items["example-coral"]
        self.assertEqual(coral["status"], "single_candidate")
        self.assertEqual([c["entity_id"] for c in coral["candidates"]], ["ahj:FL:1"])
        self.assertEqual(coral["candidates"][0]["match_method"], "place_name")
        self.assertEqual(coral["candidates"][0]["legal_form"], "city")
        self.assertIn("state_not_specified_all_states_searched", coral["issues"])
        self.assertEqual([(c["entity_id"], c["match_method"]) for c in items["miami-dade"]["candidates"]], [("ahj:FL:7", "county_name")])
        # "Plant City" keeps its own final word; it must not be reduced to "Plant".
        self.assertEqual([c["entity_id"] for c in items["plant-city"]["candidates"]], ["ahj:FL:6"])
        lee = items["lee-county"]
        self.assertEqual(lee["status"], "ambiguous")
        self.assertEqual([c["entity_id"] for c in lee["candidates"]], ["ahj:FL:2", "ahj:GA:3"])
        self.assertTrue(all(c["match_method"] == "exact_name" for c in lee["candidates"]))
        self.assertTrue(all(item["review_required"] is True for item in report["items"]))
        self.assertEqual(report["summary"], {"single_candidate": 3, "ambiguous": 1, "unmatched": 0})

    def test_utilities_and_unrelated_township_are_never_candidates(self):
        report = propose_registry_links(registry(("lee-county", "Lee County"), ("lee", "Lee")), entities())
        items = by_id(report)
        candidates = {c["entity_id"] for item in items.values() for c in item["candidates"]}
        self.assertNotIn("utility:9", candidates)
        self.assertNotIn("ahj:MI:8", {c["entity_id"] for c in items["lee-county"]["candidates"]})
        # A bare "Lee" surfaces the township as a place name and the counties as
        # county names, each labelled so a reviewer can rule them in or out.
        self.assertEqual([(c["entity_id"], c["match_method"]) for c in items["lee"]["candidates"]],
                         [("ahj:FL:2", "county_name"), ("ahj:GA:3", "county_name"), ("ahj:MI:8", "place_name")])
        self.assertEqual(items["lee"]["status"], "ambiguous")

    def test_registry_state_suffix_wins_over_state_option(self):
        data = registry(("lee-county", "Lee County"), ("pittsburgh", "Pittsburgh"),
                        ("cheyenne-wy", "Cheyenne, WY"), ("scranton-pa", "Scranton, PA"))
        report = propose_registry_links(data, entities(), state="fl")
        self.assertEqual(report["state_filter"], "FL")
        items = by_id(report)
        lee = items["lee-county"]
        self.assertEqual((lee["status"], lee["state_hint"], lee["state_hint_source"]), ("single_candidate", "FL", "state_option"))
        self.assertEqual([c["entity_id"] for c in lee["candidates"]], ["ahj:FL:2"])
        self.assertEqual([c["entity_id"] for c in lee["other_state_candidates"]], ["ahj:GA:3"])
        pittsburgh = items["pittsburgh"]
        self.assertEqual(pittsburgh["status"], "unmatched")
        self.assertIn("candidates_only_in_other_states", pittsburgh["issues"])
        self.assertEqual([c["entity_id"] for c in pittsburgh["other_state_candidates"]], ["ahj:PA:10"])
        cheyenne = items["cheyenne-wy"]
        self.assertEqual((cheyenne["state_hint"], cheyenne["state_hint_source"], cheyenne["search_name"]), ("WY", "registry_name", "Cheyenne"))
        self.assertEqual(cheyenne["status"], "unmatched")
        self.assertIn("no_catalog_candidate", cheyenne["issues"])
        self.assertEqual(items["scranton-pa"]["state_hint"], "PA")
        self.assertEqual(report["summary"], {"single_candidate": 1, "ambiguous": 0, "unmatched": 3})

    def test_legal_form_prefix_and_identity_notes_surface_as_review_issues(self):
        data = registry(("village-of-palm-springs", "Village of Palm Springs", "sender_spelling_variant"),
                        ("example-shore", "Example Shore", "none", ("inspection_passed",)))
        report = propose_registry_links(data, entities())
        items = by_id(report)
        village = items["village-of-palm-springs"]
        self.assertEqual((village["search_name"], village["registry_legal_form"]), ("Palm Springs", "village"))
        self.assertEqual(village["status"], "ambiguous")
        self.assertIn("registry_legal_form_differs_from_catalog", village["issues"])
        self.assertIn("registry_identity_note_sender_spelling_variant", village["issues"])
        filtered = by_id(propose_registry_links(data, entities(), state="FL"))["village-of-palm-springs"]
        self.assertEqual(filtered["status"], "single_candidate")
        self.assertEqual(filtered["candidates"][0]["legal_form"], "village")
        self.assertNotIn("registry_legal_form_differs_from_catalog", filtered["issues"])
        shore = items["example-shore"]
        self.assertEqual(shore["status"], "single_candidate")
        self.assertEqual(shore["candidates"][0]["identity_status"], "unresolved")
        self.assertIn("candidate_identity_unresolved_in_source", shore["issues"])
        self.assertEqual(shore["pilot_events"], ["inspection_passed"])

    def test_invalid_registry_or_state_filter_is_rejected_without_echoing_values(self):
        broken = registry(("example-coral", "Example Coral"))
        broken["entries"][0]["message_count"] = 12
        with self.assertRaises(ValueError) as error:
            propose_registry_links(broken, entities())
        self.assertNotIn("12", str(error.exception))
        for state in ("Florida", "F", "F1", 12):
            with self.subTest(state=state), self.assertRaises(ValueError):
                propose_registry_links(registry(("example-coral", "Example Coral")), entities(), state=state)


def tiny_snapshot():
    return {
        "source": {"dataset_id": "solartrace", "version": "fictional-crosswalk-v1", "source_sha256": "b" * 64,
                   "source_url": "https://example.invalid/fictional-source",
                   "license_notice": "Fictional source license notice. Test data only."},
        "entities": entities(), "requirements": [], "benchmarks": [], "installations": [],
        "source_rows": [{"sheet": "Fictional Timelines", "row": 2, "values": ["FL", "Example Coral city", "1"]}],
        "stats": {"fictional_fixture": True},
    }


class CrosswalkCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sunbridge-crosswalk-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private = self.root / "private"
        self.private.mkdir()
        self.db = self.private / "catalog/sunbridge.sqlite"
        for target in ("sunbridge.__main__.ROOT", "sunbridge.privateio.ROOT"):
            patched = patch(target, self.root)
            patched.start()
            self.addCleanup(patched.stop)
        no_network = patch("socket.socket", side_effect=AssertionError("Crosswalk CLI attempted network access"))
        self.network = no_network.start()
        self.addCleanup(no_network.stop)
        with patch("sunbridge.solartrace.load_bundle", return_value={"fictional_bundle": True}), \
                patch("sunbridge.solartrace.normalize_snapshot", return_value=tiny_snapshot()):
            code, _, err = self.cli("catalog", "init")
        self.assertEqual(code, 0, err)

    @staticmethod
    def cli(*arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = main(list(arguments))
            except SystemExit as error:
                code = error.code
        return code, out.getvalue(), err.getvalue()

    def write_registry(self, data):
        path = self.root / "coverage/ahj-email-signals.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    def test_reconcile_coverage_writes_private_proposals_and_changes_no_inputs(self):
        data = registry(("example-coral", "Example Coral"), ("lee-county", "Lee County"), ("cheyenne-wy", "Cheyenne, WY"))
        path = self.write_registry(data)
        registry_bytes, db_bytes = path.read_bytes(), self.db.read_bytes()
        output = self.private / "coverage-reconciliation"
        code, out, err = self.cli("catalog", "reconcile-coverage", "--registry", str(path), "--state", "FL", "--output", str(output))
        self.assertEqual(code, 0, err)
        self.assertEqual((path.read_bytes(), self.db.read_bytes()), (registry_bytes, db_bytes))
        printed = json.loads(out.rsplit("\n}", 1)[0] + "\n}")
        self.assertEqual(printed["summary"], {"single_candidate": 2, "ambiguous": 0, "unmatched": 1})
        self.assertEqual((printed["crm_writes"], printed["registry_writes"]), (0, 0))
        review = json.loads((output / "review.json").read_text(encoding="utf-8"))
        self.assertEqual((output / "review.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(review["mode"], "review_only")
        self.assertEqual(review["source"]["source_sha256"], "b" * 64)
        self.assertEqual(review["state_filter"], "FL")
        self.assertEqual(by_id(review)["lee-county"]["candidates"][0]["entity_id"], "ahj:FL:2")
        self.network.assert_not_called()
        # A second run refuses to overwrite the previous review.
        code, _, err = self.cli("catalog", "reconcile-coverage", "--registry", str(path), "--output", str(output))
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_reconcile_coverage_rejects_an_invalid_registry_without_writing(self):
        data = registry(("example-coral", "Example Coral"))
        data["entries"][0]["message_count"] = 3
        path = self.write_registry(data)
        output = self.private / "coverage-reconciliation"
        code, _, err = self.cli("catalog", "reconcile-coverage", "--registry", str(path), "--output", str(output))
        self.assertEqual(code, 1)
        self.assertNotIn("3", err.replace("Could not complete", ""))
        self.assertFalse((output / "review.json").exists())

    def test_reconcile_coverage_uses_public_registry_path_by_default(self):
        self.write_registry(registry(("example-coral", "Example Coral")))
        code, out, err = self.cli("catalog", "reconcile-coverage")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.private / "coverage-reconciliation/review.json").is_file())
        self.assertIn("single_candidate", out)

    def test_search_table_format_is_readable_and_json_remains_default(self):
        code, out, err = self.cli("catalog", "search", "--kind", "building_department", "--query", "Lee County", "--format", "table")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("entity_id"))
        self.assertIn("ahj:FL:2", out)
        self.assertIn("ahj:GA:3", out)
        self.assertNotIn("utility:9", out)
        self.assertNotIn("{", out)
        self.assertIn("2 results", out)
        self.assertIn("catalog show --id", out)
        code, out, err = self.cli("catalog", "search", "--query", "Lee County")
        self.assertEqual(code, 0, err)
        self.assertEqual({row["entity_id"] for row in json.loads(out)}, {"ahj:FL:2", "ahj:GA:3", "utility:9"})
        code, out, err = self.cli("catalog", "search", "--query", "No Such Place", "--format", "table")
        self.assertEqual(code, 0, err)
        self.assertIn("No catalog entities matched", out)
        code, out, err = self.cli("catalog", "search", "--query", "Lee", "--limit", "1", "--format", "table")
        self.assertEqual(code, 0, err)
        self.assertIn("capped", out)


if __name__ == "__main__":
    unittest.main()
