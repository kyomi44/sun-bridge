"""Offline SolarTRACE normalization and values-only archive boundary tests."""

import copy
import gzip
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape, quoteattr

from sunbridge import solartrace as st


COHORT = "2017 0-10kW PV Only"
PERMIT = "Median AHJ Permit Time " + COHORT
PRE_IX = "Median Pre-Install IX Time " + COHORT
INSPECTION = "Median Inspection Time " + COHORT
INSTALLS = "Installs " + COHORT


def timeline(**changes):
    result = {header: None for header in st.TIMELINE_HEADERS}
    result.update(state="FL", ahj="Example City", geo_id="00123",
                  utility="Example Utility", eia_id="00991")
    result.update(changes)
    return result


def table(headers, records):
    return [{"row": 1, "values": list(headers)}] + [
        {"row": index, "values": [row.get(header) for header in headers]}
        for index, row in enumerate(records, 2)
    ]


def bundle(timelines=(), ahjs=(), utilities=()):
    return {"schema_version": 1, "source": {
        "dataset_id": "solartrace", "version": "v9-9-2025",
        "source_sha256": st.SOURCE_SHA256, "verified_official_bytes": True,
        "license_notice": "Synthetic source notice",
    }, "tables": {
        "Information": [{"row": 2, "values": ["Dataset Completed: 9/9/2025"]}],
        "AHJ-Utility Timelines": table(st.TIMELINE_HEADERS, timelines),
        "AHJ permits reqs": table(st.AHJ_HEADERS, ahjs),
        "Utility IX reqs": table(st.UTILITY_HEADERS, utilities),
    }}


def worksheet(rows):
    body = []
    for entry in rows:
        cells = []
        for index, value in enumerate(entry["values"], 1):
            if value is None:
                continue
            ref = st.column_name(index) + str(entry["row"])
            if isinstance(value, str):
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        body.append(f'<row r="{entry["row"]}">{"".join(cells)}</row>')
    return ('<worksheet xmlns="' + st.NS["s"] + '"><sheetData>'
            + "".join(body) + '</sheetData></worksheet>').encode()


def xlsx_bytes(*, replacements=None, extra_members=None):
    """Create only fictional minimal OOXML, with no workbook library or network."""
    tables = bundle()["tables"]
    members = {
        "xl/workbook.xml": ('<workbook xmlns="' + st.NS["s"]
            + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>'
                      for index, name in enumerate(st.SHEETS, 1))
            + '</sheets></workbook>').encode(),
        "xl/_rels/workbook.xml.rels": ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{index}" Target="worksheets/sheet{index}.xml"/>'
                      for index in range(1, 5)) + '</Relationships>').encode(),
        **{f"xl/worksheets/sheet{index}.xml": worksheet(tables[name])
           for index, name in enumerate(st.SHEETS, 1)},
    }
    members.update(replacements or {})
    members.update(extra_members or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


class NormalizationTests(unittest.TestCase):
    def test_fixture_has_exact_reviewed_165_headers_and_four_sheets(self):
        self.assertEqual(len(st.TIMELINE_HEADERS), 165)
        self.assertEqual(len(set(st.TIMELINE_HEADERS)), 165)
        self.assertEqual(set(bundle()["tables"]), set(st.SHEETS))

    def test_identifiers_preserve_opaque_leading_zeros(self):
        result = st.normalize_snapshot(bundle([timeline(**{PERMIT: 4})]))
        entities = {entity["entity_id"]: entity for entity in result["entities"]}
        self.assertIn("ahj:FL:00123", entities)
        self.assertIn("utility:00991", entities)
        self.assertEqual(entities["ahj:FL:00123"]["source_identifiers"], {"geo_id": "00123"})
        self.assertEqual(entities["utility:00991"]["source_identifiers"], {"eia_id": "00991"})

    def test_source_ids_not_names_define_identity(self):
        rows = [timeline(geo_id="00123"), timeline(geo_id="123")]
        result = st.normalize_snapshot(bundle(rows))
        self.assertEqual(len([e for e in result["entities"] if e["kind"] == "building_department"]), 2)

    def test_missing_ids_remain_source_local_even_when_names_match(self):
        rows = [timeline(geo_id=None, **{PERMIT: 4}), timeline(geo_id="NA", **{PERMIT: 4})]
        requirement = {"state": "FL", "ahj": "Example City", "geo_id": ""}
        result = st.normalize_snapshot(bundle(rows, [requirement]))
        authorities = [e for e in result["entities"] if e["kind"] == "building_department"]
        self.assertEqual(len(authorities), 3)
        self.assertEqual(len({e["entity_id"] for e in authorities}), 3)
        self.assertTrue(all(e["identity_status"] == "unresolved" for e in authorities))
        self.assertTrue(all(e["source_identifiers"] == {} for e in authorities))
        self.assertEqual(len(result["benchmarks"]), 2)
        self.assertTrue(all("source_identity_unresolved" in b["flags"] for b in result["benchmarks"]))

    def test_same_ahj_token_in_different_states_is_not_merged(self):
        result = st.normalize_snapshot(bundle([timeline(), timeline(state="CA")]))
        authorities = [e for e in result["entities"] if e["kind"] == "building_department"]
        self.assertEqual({e["entity_id"] for e in authorities}, {"ahj:FL:00123", "ahj:CA:00123"})

    def test_identical_medians_deduplicate_without_averaging_or_sample_invention(self):
        rows = [timeline(eia_id="991", **{PERMIT: 7, INSTALLS: 12}),
                timeline(eia_id="992", **{PERMIT: 7.0, INSTALLS: 30})]
        result = st.normalize_snapshot(bundle(rows))
        self.assertEqual(len(result["benchmarks"]), 1)
        benchmark = result["benchmarks"][0]
        self.assertEqual(benchmark["value"], 7)
        self.assertEqual(benchmark["values"], [7])
        self.assertEqual(benchmark["status"], "reported")
        self.assertEqual(len(benchmark["source_refs"]), 2)
        self.assertIsNone(benchmark["sample_n"])
        self.assertIn("metric_sample_size_not_supplied", benchmark["flags"])
        self.assertEqual([item["count"] for item in result["installations"]], [12, 30])

    def test_same_eia_has_state_specific_benchmarks_and_requirements(self):
        rows = [timeline(**{PRE_IX: 4}), timeline(state="CA", **{PRE_IX: 9})]
        requirements = [{"State": state, "Utility": "Example Utility", "EIA ID": "00991",
                         "Application Acceptance Method": method}
                        for state, method in [("FL", "Example one"), ("CA", "Example two")]]
        result = st.normalize_snapshot(bundle(rows, utilities=requirements))
        utilities = [e for e in result["entities"] if e["kind"] == "utility_company"]
        self.assertEqual(len(utilities), 1)
        self.assertEqual(utilities[0]["states"], ["CA", "FL"])
        self.assertEqual({(b["state"], b["value"], b["status"]) for b in result["benchmarks"]},
                         {("CA", 9, "reported"), ("FL", 4, "reported")})
        self.assertEqual({r["state"] for r in result["requirements"]}, {"CA", "FL"})

    def test_different_numeric_values_flag_conflict_instead_of_averaging(self):
        result = st.normalize_snapshot(bundle([timeline(**{PERMIT: 4}), timeline(**{PERMIT: 8})]))
        benchmark = result["benchmarks"][0]
        self.assertIsNone(benchmark["value"])
        self.assertEqual(benchmark["values"], [4, 8])
        self.assertEqual(benchmark["status"], "conflict")
        self.assertEqual(result["stats"]["conflicting_benchmarks"], 1)

    def test_na_blank_and_null_are_not_zero_and_source_rows_are_unchanged(self):
        original = bundle([timeline(**{PERMIT: missing}) for missing in ["NA", "", None, 0]])
        before = copy.deepcopy(original)
        result = st.normalize_snapshot(original)
        self.assertEqual(original, before)
        benchmark = result["benchmarks"][0]
        self.assertEqual(benchmark["value"], 0)
        self.assertEqual(benchmark["unknown_references_count"], 3)
        self.assertEqual(len(benchmark["source_refs"]), 1)
        self.assertIn("some_repeated_source_rows_report_missing", benchmark["flags"])
        raw = [r for r in result["source_rows"] if r["sheet"] == "AHJ-Utility Timelines"]
        self.assertEqual([r["values"] for r in raw], [r["values"] for r in before["tables"]["AHJ-Utility Timelines"]])

    def test_all_missing_metrics_do_not_produce_benchmarks(self):
        result = st.normalize_snapshot(bundle([timeline(**{PERMIT: "NA", PRE_IX: "", INSPECTION: None})]))
        self.assertEqual(result["benchmarks"], [])

    def test_zero_preinstall_value_retains_specific_caveat(self):
        result = st.normalize_snapshot(bundle([timeline(**{PRE_IX: 0})]))
        self.assertIn("zero_may_represent_no_preinstall_requirement", result["benchmarks"][0]["flags"])

    def test_inspection_preserves_definition_conflict(self):
        result = st.normalize_snapshot(bundle([timeline(**{INSPECTION: 3})]))
        self.assertIn("source_inspection_definition_ambiguous_Information_C15_C47", result["benchmarks"][0]["flags"])

    def test_positive_installations_are_separate_from_metric_samples(self):
        result = st.normalize_snapshot(bundle([timeline(**{INSTALLS: 10, PERMIT: 2}),
                                              timeline(**{INSTALLS: 0}), timeline(**{INSTALLS: "NA"})]))
        self.assertEqual(len(result["installations"]), 1)
        self.assertEqual(result["installations"][0]["count"], 10)
        self.assertEqual(result["stats"]["source_installs"], 10)
        self.assertIsNone(result["benchmarks"][0]["sample_n"])

    def test_missing_label_with_stored_id_does_not_destroy_identity(self):
        result = st.normalize_snapshot(bundle([timeline(ahj=None, utility="NA", **{PERMIT: 2, PRE_IX: 3})]))
        self.assertEqual({e["entity_id"] for e in result["entities"]}, {"ahj:FL:00123", "utility:00991"})
        self.assertTrue(all(e["identity_status"] == "source_id" for e in result["entities"]))
        self.assertEqual(len(result["benchmarks"]), 2)

    def test_reordered_headers_keep_values_and_evidence_columns_aligned(self):
        original = bundle([timeline(**{PERMIT: 2, INSTALLS: 10})])
        rows = original["tables"]["AHJ-Utility Timelines"]
        for row in rows:
            row["values"].reverse()
        result = st.normalize_snapshot(original)
        self.assertEqual(result["benchmarks"][0]["value"], 2)
        expected = st.column_name(rows[0]["values"].index(PERMIT) + 1)
        self.assertEqual(result["benchmarks"][0]["source_refs"][0]["column"], expected)
        expected = st.column_name(rows[0]["values"].index(INSTALLS) + 1)
        self.assertEqual(result["installations"][0]["column"], expected)

    def test_missing_and_duplicate_headers_fail_closed(self):
        for sheet in st.SHEETS[1:]:
            for mode in ["missing", "duplicate"]:
                original = bundle()
                headers = original["tables"][sheet][0]["values"]
                if mode == "missing":
                    headers.pop()
                else:
                    headers[-1] = headers[0]
                with self.subTest(sheet=sheet, mode=mode), self.assertRaises(ValueError):
                    st.normalize_snapshot(original)

    def test_malformed_and_negative_timeline_values_fail(self):
        for value in ["7", -1, True, float("nan"), float("inf"), {}, []]:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                st.normalize_snapshot(bundle([timeline(**{PERMIT: value})]))

    def test_malformed_install_counts_fail(self):
        for value in [-1, True, "10", 2.5, float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                st.normalize_snapshot(bundle([timeline(**{INSTALLS: value})]))

    def test_bad_identifiers_and_missing_state_fail(self):
        for value in [-1, 1.5, True, "source-name", " 123 ", {}]:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                st.normalize_snapshot(bundle([timeline(geo_id=value)]))
        with self.assertRaises(ValueError):
            st.normalize_snapshot(bundle([timeline(state=None)]))

    def test_unattributable_valid_timeline_is_counted_without_guessed_entity(self):
        original = bundle([timeline(utility=None, eia_id=None, **{PRE_IX: 3})])
        before = copy.deepcopy(original)
        result = st.normalize_snapshot(original)
        self.assertEqual(result["benchmarks"], [])
        self.assertEqual(result["stats"]["unassigned_numeric_timeline_source_cells"], 1)
        self.assertFalse(any(e["kind"] == "utility_company" for e in result["entities"]))
        self.assertEqual(original, before)
        raw = [row for row in result["source_rows"] if row["sheet"] == "AHJ-Utility Timelines" and row["row"] == 2]
        self.assertEqual(raw[0]["values"], before["tables"]["AHJ-Utility Timelines"][1]["values"])

    def test_unattributable_malformed_timeline_still_fails(self):
        for value in [-1, "malformed", True, float("nan")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                st.normalize_snapshot(bundle([timeline(ahj=None, geo_id=None, **{PERMIT: value})]))

    def test_repeated_row_ids_cannot_merge_unresolved_records(self):
        original = bundle([timeline(geo_id=None), timeline(geo_id=None)])
        original["tables"]["AHJ-Utility Timelines"][2]["row"] = 2
        with self.assertRaises(ValueError):
            st.normalize_snapshot(original)

    def test_malformed_table_structure_fails_with_valueerror(self):
        for broken in [[], {}, [None], [{"row": 1, "values": [{}]}],
                       [{"row": 1, "values": st.TIMELINE_HEADERS}, {"row": True, "values": []}],
                       [{"row": 1, "values": st.TIMELINE_HEADERS}, {"row": 2, "values": {}}]]:
            original = bundle()
            original["tables"]["AHJ-Utility Timelines"] = broken
            with self.subTest(table_type=type(broken).__name__), self.assertRaises(ValueError):
                st.normalize_snapshot(original)


class WorkbookBoundaryTests(unittest.TestCase):
    def read_fixture(self, raw, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "synthetic.xlsx"
            path.write_bytes(raw)
            (base / "NOTICE.txt").write_text("Synthetic source notice", encoding="utf-8")
            with patch.object(st, "BUNDLE_DIR", base):
                return st.read_workbook(path, **kwargs)

    def test_values_only_fixture_reads_without_claiming_official_identity(self):
        result = self.read_fixture(xlsx_bytes())
        self.assertEqual(set(result["tables"]), set(st.SHEETS))
        self.assertFalse(result["source"]["verified_official_bytes"])
        self.assertIsNone(result["source"]["source_url"])
        self.assertEqual(result["tables"]["AHJ-Utility Timelines"][0]["values"], st.TIMELINE_HEADERS)

    def test_large_numeric_integer_is_preserved_exactly(self):
        expected = 9007199254740993
        for token in [str(expected), "9.007199254740993E15"]:
            cells = (f'<worksheet xmlns="{st.NS["s"]}"><sheetData><row r="1">'
                     f'<c r="A1"><v>{token}</v></c></row></sheetData></worksheet>').encode()
            with self.subTest(token=token):
                result = self.read_fixture(xlsx_bytes(replacements={"xl/worksheets/sheet2.xml": cells}))
                value = result["tables"]["AHJ-Utility Timelines"][0]["values"][0]
                self.assertIs(type(value), int)
                self.assertEqual(value, expected)

    def test_pinned_generation_rejects_synthetic_source_bytes(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.read_fixture(xlsx_bytes(), require_pinned=True)

    def test_formula_cells_fail_without_evaluation(self):
        formula = (f'<worksheet xmlns="{st.NS["s"]}"><sheetData><row r="2">'
                   '<c r="A2" t="str"><f>HYPERLINK("https://example.invalid/", "Example")</f>'
                   '<v>Dataset Completed: 9/9/2025</v></c></row></sheetData></worksheet>').encode()
        with self.assertRaisesRegex(ValueError, "Calculated"):
            self.read_fixture(xlsx_bytes(replacements={"xl/worksheets/sheet1.xml": formula}))

    def test_unsafe_archive_path_fails_without_extraction(self):
        with self.assertRaises(ValueError):
            self.read_fixture(xlsx_bytes(extra_members={"../outside.xml": b"unused"}))

    def test_external_required_sheet_relationship_is_not_followed(self):
        rel = b'<Relationships><Relationship Id="rId1" TargetMode="External" Target="https://example.invalid/sheet.xml"/></Relationships>'
        with self.assertRaises(ValueError):
            self.read_fixture(xlsx_bytes(replacements={"xl/_rels/workbook.xml.rels": rel}))

    def test_negative_shared_string_index_is_rejected(self):
        info = (f'<worksheet xmlns="{st.NS["s"]}"><sheetData><row r="2">'
                '<c r="A2" t="s"><v>-1</v></c></row></sheetData></worksheet>').encode()
        strings = (f'<sst xmlns="{st.NS["s"]}"><si><t>Dataset Completed: 9/9/2025</t></si></sst>').encode()
        with self.assertRaises(ValueError):
            self.read_fixture(xlsx_bytes(replacements={"xl/worksheets/sheet1.xml": info},
                                         extra_members={"xl/sharedStrings.xml": strings}))

    def test_cell_reference_must_match_its_parent_row(self):
        info = worksheet([{"row": 2, "values": ["Dataset Completed: 9/9/2025"]}]).replace(b'r="A2"', b'r="A3"')
        with self.assertRaises(ValueError):
            self.read_fixture(xlsx_bytes(replacements={"xl/worksheets/sheet1.xml": info}))

    def test_doctype_is_rejected_for_utf8_and_utf16(self):
        xml = ('<!DOCTYPE worksheet [<!ENTITY completed "Dataset Completed: 9/9/2025">]>'
               f'<worksheet xmlns="{st.NS["s"]}"><sheetData><row r="2">'
               '<c r="A2" t="inlineStr"><is><t>&completed;</t></is></c></row></sheetData></worksheet>')
        for encoding in ["utf-8", "utf-16"]:
            with self.subTest(encoding=encoding), self.assertRaises(ValueError):
                self.read_fixture(xlsx_bytes(replacements={"xl/worksheets/sheet1.xml": xml.encode(encoding)}))


class BundleIntegrityTests(unittest.TestCase):
    def load_fixture(self, payload, *, transform_manifest=None, corrupt_bytes=False):
        raw = gzip.compress(json.dumps(payload).encode(), mtime=0)
        manifest = {"bundle_bytes": len(raw), "bundle_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_sha256": st.SOURCE_SHA256}
        if transform_manifest:
            transform_manifest(manifest)
        if corrupt_bytes:
            raw = raw[:-1] + bytes([raw[-1] ^ 1])
        with patch.object(Path, "read_text", return_value=json.dumps(manifest)), patch.object(Path, "read_bytes", return_value=raw):
            return st.load_bundle()

    def test_valid_pinned_bundle_roundtrips(self):
        original = bundle([timeline(**{PERMIT: 2})])
        self.assertEqual(self.load_fixture(original), original)

    def test_changed_compressed_bytes_fail_integrity(self):
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.load_fixture(bundle(), corrupt_bytes=True)

    def test_source_pin_checked_in_both_manifest_and_bundle(self):
        wrong = "f" * 64
        with self.assertRaises(ValueError):
            self.load_fixture(bundle(), transform_manifest=lambda manifest: manifest.update(source_sha256=wrong))
        original = bundle()
        original["source"]["source_sha256"] = wrong
        with self.assertRaises(ValueError):
            self.load_fixture(original)

    def test_decompression_limit_is_enforced(self):
        with patch.object(st, "MAX_BUNDLE_BYTES", 20), self.assertRaisesRegex(ValueError, "size limit"):
            self.load_fixture(bundle())


if __name__ == "__main__":
    unittest.main()
