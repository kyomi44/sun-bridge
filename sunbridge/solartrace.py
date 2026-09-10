"""Versioned SolarTRACE source rows and conservative catalog normalization.

The bundled data are an attributed derivative, not covered by the code license.
No workbook macros, formulas, hyperlinks, or external relationships are run.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from .validation import ROOT

SOURCE_URL = "https://data.nlr.gov/system/files/160/1763653965-SolarTRACE%20Dataset%20v9-9-2025.xlsx"
SOURCE_SHA256 = "3a4d51ba622d1132e2451387c9b359dbd6674e1d8e94e7f59733019ccb4a6d26"
BUNDLE_DIR = ROOT / "catalog/solartrace"
SHEETS = ("Information", "AHJ-Utility Timelines", "AHJ permits reqs", "Utility IX reqs")
MAX_XLSX_BYTES = 20_000_000
MAX_XML_BYTES = 100_000_000
MAX_BUNDLE_BYTES = 40_000_000
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
COHORTS = [(year, size, technology) for technology in ("PV Only", "PV+Storage")
           for size in ("0-10kW", "10-20kW") for year in range(2017, 2025)]
METRICS = {
    "Median AHJ Permit Time": ("ahj_permit", "building_department"),
    "Median Pre-Install IX Time": ("pre_install_ix", "utility_company"),
    "Median Inspection Time": ("inspection", "building_department"),
    "Median Final IX to PTO": ("final_ix_to_pto", "utility_company"),
}
TIMELINE_HEADERS = ["state", "ahj", "geo_id", "utility", "eia_id"] + [
    f"{metric} {year} {size} {technology}" for year, size, technology in COHORTS
    for metric in ("Installs", *METRICS)
]
AHJ_HEADERS = ["state", "ahj", "geo_id", "SolSmart Awardee", "SolSmart 3-Day Permit Target",
    "Online Permitting in 2019", "Online Permitting - 2022", "Online Permitting - 2024",
    "Online Permitting - 2025", "Online Instant Permitting - 2022", "Online Instant Permitting - 2024",
    "PV Online Instant Permitting - 2025", "Same Day In-Person Permitting Available",
    "Structural Review Required", "Electrical Review Required", "Third-Party Permit Review",
    "Median Permit Cost", "Number of Inspections Required", "Rough-In Inspection Required"]
UTILITY_HEADERS = ["State", "Utility", "EIA ID", "Approval to Build required from utility before install",
    "Direct Point of Contact for Interconnection Information Available", "Application Acceptance Method",
    "Online Payment Acceptance", "IX Application Response Time Requirement", "Response Time (Business days)",
    "Offset Policy in Place from Utility", "Offset Percentage", "Capacity Map", "Utility Webpage / Map Link"]


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _safe_xml(raw: bytes) -> None:
    # The supported source uses UTF-8. Reject UTF-16/32 instead of allowing a
    # different encoding to hide entity declarations from the safety check.
    if b"\x00" in raw or raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("Workbook XML must use the supported UTF-8 encoding.")
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("Workbook XML declarations are not supported.")


def _xml(raw: bytes):
    _safe_xml(raw)
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise ValueError("Workbook XML is malformed.") from None


def _column(value: str) -> int:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", value)
    if not match:
        raise ValueError("Workbook contains an invalid cell reference.")
    result = 0
    for char in match[1]:
        result = result * 26 + ord(char) - 64
    return result - 1


def column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def read_workbook(path: Path, *, require_pinned: bool = False) -> dict:
    """Read the supported workbook layout with only Python's standard library."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_XLSX_BYTES:
        raise ValueError("Choose a regular SolarTRACE workbook no larger than 20 MB.")
    with path.open("rb") as handle:
        raw = handle.read(MAX_XLSX_BYTES + 1)
    if len(raw) > MAX_XLSX_BYTES:
        raise ValueError("Workbook exceeds the size limit.")
    sha = hashlib.sha256(raw).hexdigest()
    if require_pinned and sha != SOURCE_SHA256:
        raise ValueError("Public seed generation requires the verified official source checksum.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
        if len(infos) > 300 or sum(i.file_size for i in infos) > MAX_XML_BYTES or len({i.filename for i in infos}) != len(infos):
            raise ValueError("Workbook archive exceeds the supported bounds or repeats a member.")
        if any(i.flag_bits & 1 or i.filename.startswith("/") or ".." in PurePosixPath(i.filename).parts for i in infos):
            raise ValueError("Encrypted or unsafe workbook archive members are not supported.")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = _xml(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.iterfind(".//s:t", NS)) for item in root]
            if len(strings) > 100_000 or any(len(item) > 20_000 for item in strings):
                raise ValueError("Workbook strings exceed the supported bounds.")
        relationships = {}
        for item in _xml(archive.read("xl/_rels/workbook.xml.rels")):
            if item.attrib.get("TargetMode") == "External":
                continue
            target = item.attrib.get("Target", "")
            target = target.lstrip("/") if target.startswith("/xl/") else str(PurePosixPath("xl") / target)
            if ".." in PurePosixPath(target).parts:
                raise ValueError("Workbook relationships cannot traverse parent directories.")
            relationships[item.attrib["Id"]] = target
        workbook = _xml(archive.read("xl/workbook.xml"))
        sheets = {item.attrib["name"]: relationships.get(item.attrib[REL]) for item in workbook.findall("s:sheets/s:sheet", NS)}
        if any(name not in sheets or not sheets[name] for name in SHEETS):
            raise ValueError("Workbook is missing a required SolarTRACE worksheet.")
        tables = {}
        for name in SHEETS:
            sheet_bytes = archive.read(sheets[name])
            _safe_xml(sheet_bytes)
            rows, seen = [], set()
            for _, element in ET.iterparse(io.BytesIO(sheet_bytes), events=("end",)):
                if element.tag != f"{{{NS['s']}}}row":
                    continue
                row_text = element.attrib.get("r", "")
                if not re.fullmatch(r"[1-9][0-9]{0,4}", row_text):
                    raise ValueError("Workbook row identifiers must be bounded positive integers.")
                row_number = int(row_text)
                if not 1 <= row_number <= 20_000 or row_number in seen:
                    raise ValueError("Workbook row identifiers are invalid or exceed the import limit.")
                seen.add(row_number)
                values, columns = [], set()
                for cell in element.findall("s:c", NS):
                    index = _column(cell.attrib.get("r", ""))
                    if int(re.search(r"[0-9]+$", cell.attrib["r"])[0]) != row_number:
                        raise ValueError("Workbook cell reference does not match its source row.")
                    if index > 300 or index in columns:
                        raise ValueError("Workbook contains repeated or out-of-range columns.")
                    columns.add(index)
                    if cell.find("s:f", NS) is not None:
                        raise ValueError("Calculated source cells are not supported; use a reviewed values-only source.")
                    kind = cell.attrib.get("t", "n")
                    node = cell.find("s:v", NS)
                    value = node.text if node is not None else None
                    if kind == "s" and value is not None:
                        if not re.fullmatch(r"[0-9]+", value) or int(value) >= len(strings):
                            raise ValueError("Workbook shared-string reference is invalid.")
                        value = strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iterfind(".//s:t", NS))
                    elif kind == "n" and value is not None:
                        if len(value) > 100:
                            raise ValueError("Workbook numeric token exceeds the supported precision.")
                        try:
                            number = Decimal(value)
                        except InvalidOperation:
                            raise ValueError("Workbook contains an invalid numeric token.") from None
                        if not number.is_finite() or (number and abs(number.adjusted()) > 100):
                            raise ValueError("Workbook contains a non-finite number.")
                        value = int(number) if number == number.to_integral_value() else float(number)
                    elif kind not in {"str", "n", "s", "inlineStr"}:
                        raise ValueError("Workbook contains an unsupported cell type.")
                    if isinstance(value, str) and len(value) > 20_000:
                        raise ValueError("Workbook cell text exceeds the size limit.")
                    values.extend([None] * (index + 1 - len(values)))
                    values[index] = value
                while values and values[-1] is None:
                    values.pop()
                if values:
                    rows.append({"row": row_number, "values": values})
                element.clear()
            tables[name] = rows
        archive.close()
    except (zipfile.BadZipFile, KeyError, IndexError, ET.ParseError, OverflowError):
        raise ValueError("Workbook does not have the supported SolarTRACE archive structure.") from None
    information = {row["row"]: row["values"] for row in tables["Information"]}
    completed = information.get(2, [""])[0]
    if not isinstance(completed, str) or completed != "Dataset Completed: 9/9/2025":
        raise ValueError("This importer supports the reviewed v9-9-2025 layout; review a new version before importing it.")
    return {"schema_version": 1, "source": {
        "dataset_id": "solartrace", "version": "v9-9-2025", "completed_on": "2025-09-09",
        "source_sha256": sha, "source_url": SOURCE_URL if sha == SOURCE_SHA256 else None,
        "verified_official_bytes": sha == SOURCE_SHA256,
        "license_notice": (BUNDLE_DIR / "NOTICE.txt").read_text(encoding="utf-8"),
        "included_sheets": list(SHEETS), "excluded_sheets": ["Data Quartiles", "State-Level Timelines"],
    }, "tables": tables}


def load_bundle() -> dict:
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or type(manifest.get("bundle_bytes")) is not int or not isinstance(manifest.get("bundle_sha256"), str):
        raise ValueError("Bundled SolarTRACE manifest has an unsupported structure.")
    raw = (BUNDLE_DIR / "rows.json.gz").read_bytes()
    if len(raw) != manifest["bundle_bytes"] or hashlib.sha256(raw).hexdigest() != manifest["bundle_sha256"]:
        raise ValueError("Bundled SolarTRACE data failed its integrity check.")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
            content = handle.read(MAX_BUNDLE_BYTES + 1)
        if len(content) > MAX_BUNDLE_BYTES:
            raise ValueError("Bundled SolarTRACE data exceeds the size limit.")
        bundle = json.loads(content)
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Bundled SolarTRACE data could not be decoded.") from None
    if not isinstance(bundle, dict) or not isinstance(bundle.get("source"), dict) or bundle["source"].get("source_sha256") != SOURCE_SHA256 or manifest.get("source_sha256") != SOURCE_SHA256:
        raise ValueError("Bundled SolarTRACE provenance does not match the reviewed source.")
    return bundle


def _missing(value) -> bool:
    return value in (None, "NA", "")


def _identifier(value) -> str | None:
    if _missing(value):
        return None
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value):
        return value
    raise ValueError("SolarTRACE identifiers must be source numeric tokens, not guessed names.")


def _table(bundle, name, expected):
    rows = bundle["tables"][name]
    if not isinstance(rows, list) or not rows or len(rows) > 20_000:
        raise ValueError("SolarTRACE table rows are missing or exceed the limit.")
    headers = rows[0]["values"]
    if rows[0]["row"] != 1 or len(headers) != len(set(headers)) or set(headers) != set(expected):
        raise ValueError(f"Unsupported {name} headers; review the source layout instead of guessing columns.")
    for entry in rows[1:]:
        if len(entry["values"]) > len(headers):
            raise ValueError("Source data extend beyond their headers.")
        yield entry["row"], dict(zip(headers, entry["values"] + [None] * (len(headers) - len(entry["values"]))))


def normalize_snapshot(bundle: dict) -> dict:
    """Build entities and deduplicated STATE-scoped medians; retain raw evidence."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1 or not isinstance(bundle.get("tables"), dict) or set(bundle["tables"]) != set(SHEETS):
        raise ValueError("Unsupported SolarTRACE snapshot structure.")
    if not isinstance(bundle.get("source"), dict):
        raise ValueError("SolarTRACE snapshot requires source provenance.")
    for name, rows in bundle["tables"].items():
        if not isinstance(rows, list) or not rows or len(rows) > 20_000:
            raise ValueError("SolarTRACE table rows are missing or exceed the limit.")
        seen = set()
        for entry in rows:
            if not isinstance(entry, dict) or type(entry.get("row")) is not int or not 1 <= entry["row"] <= 20_000 or entry["row"] in seen:
                raise ValueError("SolarTRACE rows require unique, positive source row identifiers.")
            seen.add(entry["row"])
            cells = entry.get("values")
            if not isinstance(cells, list) or len(cells) > 301:
                raise ValueError("SolarTRACE source cells must be bounded value lists.")
            for value in cells:
                if value is None:
                    continue
                if type(value) not in (str, int, float) or (isinstance(value, str) and len(value) > 20_000) or (type(value) in (int, float) and not math.isfinite(value)):
                    raise ValueError("SolarTRACE source cells must contain finite numbers, text, or blanks.")
        if name != "Information" and any(not isinstance(value, str) for value in rows[0]["values"]):
            raise ValueError("SolarTRACE source headers must be text.")
    entities, requirements, installations = {}, [], []
    observations = defaultdict(lambda: defaultdict(list))
    stats = Counter()

    def entity(kind, state, name, native, sheet, row):
        if _missing(name) and _missing(native):
            return None
        if not isinstance(state, str) or not re.fullmatch(r"[A-Z]{2}", state):
            raise ValueError("Every named SolarTRACE entity needs source state context.")
        native = _identifier(native)
        if _missing(name):
            name = f"Unnamed source authority ({native})"
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Source entity names must be text.")
        prefix = "ahj" if kind == "building_department" else "utility"
        native_key = "geo_id" if kind == "building_department" else "eia_id"
        ident = f"{prefix}:{state}:{native}" if kind == "building_department" else f"{prefix}:{native}"
        if native is None:
            # A source-local unresolved row, not a name-based cross-sheet merge.
            ident = f"{prefix}:unresolved:{_digest([sheet, row, state, name])[:20]}"
        current = entities.setdefault(ident, {"entity_id": ident, "kind": kind, "name": name, "states": [],
            "source_identifiers": {native_key: native} if native is not None else {},
            "identity_status": "source_id" if native is not None else "unresolved", "aliases": [], "source_refs": []})
        if state not in current["states"]:
            current["states"].append(state)
        alias = {"name": name, "state": state}
        if alias not in current["aliases"]:
            current["aliases"].append(alias)
        current["source_refs"].append({"sheet": sheet, "row": row})
        return ident

    for sheet, headers, kind in ((SHEETS[2], AHJ_HEADERS, "building_department"), (SHEETS[3], UTILITY_HEADERS, "utility_company")):
        for row_number, row in _table(bundle, sheet, headers):
            if all(_missing(value) for value in row.values()):
                continue
            state, name, native = (row[key] for key in headers[:3])
            ident = entity(kind, state, name, native, sheet, row_number)
            if ident is None:
                raise ValueError("Requirement observations need an identifiable source subject.")
            requirements.append({"entity_id": ident, "state": state, "source_sheet": sheet, "source_row": row_number,
                                 "fields": {key: row[key] for key in headers[3:]}})
    header_positions = {value: i + 1 for i, value in enumerate(bundle["tables"][SHEETS[1]][0]["values"])}
    for row_number, row in _table(bundle, SHEETS[1], TIMELINE_HEADERS):
        state = row["state"]
        ahj = entity("building_department", state, row["ahj"], row["geo_id"], SHEETS[1], row_number)
        utility = entity("utility_company", state, row["utility"], row["eia_id"], SHEETS[1], row_number)
        stats["timeline_source_rows"] += 1
        for year, size, technology in COHORTS:
            count_header = f"Installs {year} {size} {technology}"
            count = row[count_header]
            if not _missing(count):
                if type(count) is not int or count < 0:
                    raise ValueError("Installation counts must be nonnegative whole numbers or missing.")
                stats["source_installs"] += count
                if count > 0:
                    installations.append({"ahj_id": ahj, "utility_id": utility, "state": state, "year": year,
                        "size_band": size, "technology": technology, "count": count,
                        "source_row": row_number, "column": column_name(header_positions[count_header])})
            for label, (metric, kind) in METRICS.items():
                ident = ahj if kind == "building_department" else utility
                value = row[f"{label} {year} {size} {technology}"]
                if _missing(value):
                    continue
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Timeline medians must be nonnegative finite numbers or missing.")
                if ident is None:
                    # Some official rows have a median but no utility name/ID.
                    # Preserve their raw evidence without inventing a subject.
                    stats["unassigned_numeric_timeline_source_cells"] += 1
                    continue
                key = (ident, state, year, size, technology, metric)
                observations[key][value].append({"sheet": SHEETS[1], "row": row_number,
                    "column": column_name(header_positions[f"{label} {year} {size} {technology}"]), "value": value})
                stats["numeric_timeline_source_cells"] += 1
    benchmarks = []
    # A second pass counts explicit NA/blank evidence only for reported benchmarks.
    missing_counts = Counter()
    for row_number, row in _table(bundle, SHEETS[1], TIMELINE_HEADERS):
        state = row["state"]
        for kind, native_key, prefix, metrics in (("building_department", "geo_id", "ahj", ("Median AHJ Permit Time", "Median Inspection Time")),
                                                 ("utility_company", "eia_id", "utility", ("Median Pre-Install IX Time", "Median Final IX to PTO"))):
            native = _identifier(row[native_key])
            if native is None:
                continue
            ident = f"ahj:{state}:{native}" if prefix == "ahj" else f"utility:{native}"
            for year, size, technology in COHORTS:
                for label in metrics:
                    key = (ident, state, year, size, technology, METRICS[label][0])
                    if key in observations and _missing(row[f"{label} {year} {size} {technology}"]):
                        missing_counts[key] += 1
    for key, versions in sorted(observations.items()):
        ident, state, year, size, technology, metric = key
        values = sorted(versions)
        flags = ["historical_cohort_not_current_status", "metric_sample_size_not_supplied"]
        if metric == "pre_install_ix" and 0 in values:
            flags.append("zero_may_represent_no_preinstall_requirement")
        if metric == "inspection":
            flags.append("source_inspection_definition_ambiguous_Information_C15_C47")
        if missing_counts[key]:
            flags.append("some_repeated_source_rows_report_missing")
        if entities[ident]["identity_status"] == "unresolved":
            flags.append("source_identity_unresolved")
        benchmarks.append({"benchmark_id": "benchmark:" + _digest(key)[:24], "entity_id": ident,
            "state": state, "year": year, "size_band": size, "technology": technology, "metric": metric,
            "unit": "business_days", "statistic": "median", "value": values[0] if len(values) == 1 else None,
            "values": values, "status": "reported" if len(values) == 1 else "conflict", "sample_n": None,
            "source_refs": [ref for value in values for ref in versions[value]],
            "unknown_references_count": missing_counts[key], "flags": flags})
    for current in entities.values():
        current["states"].sort()
        current["aliases"].sort(key=lambda item: (item["state"], item["name"]))
    stats.update({"entities": len(entities), "benchmarks": len(benchmarks), "requirement_rows": len(requirements),
                  "nonzero_installation_cohorts": len(installations), "conflicting_benchmarks": sum(b["status"] == "conflict" for b in benchmarks)})
    for kind in ("building_department", "utility_company"):
        stats[kind + "_identified"] = sum(e["kind"] == kind and e["identity_status"] == "source_id" for e in entities.values())
        stats[kind + "_unresolved_rows"] = sum(e["kind"] == kind and e["identity_status"] == "unresolved" for e in entities.values())
    return {"source": bundle["source"], "entities": sorted(entities.values(), key=lambda e: e["entity_id"]),
        "requirements": requirements, "benchmarks": benchmarks, "installations": installations,
        "source_rows": [{"sheet": sheet, "row": entry["row"], "values": entry["values"]} for sheet, rows in bundle["tables"].items() for entry in rows],
        "stats": dict(stats)}
