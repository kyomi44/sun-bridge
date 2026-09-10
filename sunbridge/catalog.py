"""Private, versioned source catalog and review proposals; never CRM writes."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .privateio import private_path

SCHEMA_VERSION = 1
APPLICATION_ID = 0x53554252
MAX_JSON_BYTES = 16_000_000
KINDS = {"building_department", "utility_company"}
METRICS = {"ahj_permit", "pre_install_ix", "inspection", "final_ix_to_pto"}
SCHEMA = {
    "meta": "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "sources": "CREATE TABLE sources (source_id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, source_json TEXT NOT NULL, stats_json TEXT NOT NULL)",
    "entities": "CREATE TABLE entities (source_id INTEGER NOT NULL REFERENCES sources(source_id), entity_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY (source_id, entity_id))",
    "requirements": "CREATE TABLE requirements (record_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(source_id), entity_id TEXT NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL)",
    "benchmarks": "CREATE TABLE benchmarks (source_id INTEGER NOT NULL REFERENCES sources(source_id), benchmark_id TEXT NOT NULL, entity_id TEXT NOT NULL, state TEXT NOT NULL, metric TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY (source_id, benchmark_id))",
    "installations": "CREATE TABLE installations (record_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(source_id), ahj_id TEXT, utility_id TEXT, state TEXT NOT NULL, payload_json TEXT NOT NULL)",
    "source_rows": "CREATE TABLE source_rows (source_id INTEGER NOT NULL REFERENCES sources(source_id), sheet TEXT NOT NULL, row_number INTEGER NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY (source_id, sheet, row_number))",
    "review_reports": "CREATE TABLE review_reports (report_sha256 TEXT PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(source_id), profile_links_json TEXT NOT NULL, report_json TEXT NOT NULL)",
    "proposed_events": "CREATE TABLE proposed_events (report_sha256 TEXT NOT NULL REFERENCES review_reports(report_sha256), input_position INTEGER NOT NULL, source_id INTEGER NOT NULL REFERENCES sources(source_id), entity_id TEXT NOT NULL, profile_id TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY (report_sha256, input_position))",
    "operator_annotations": "CREATE TABLE operator_annotations (annotation_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(source_id), entity_id TEXT NOT NULL, payload_json TEXT NOT NULL)",
}


def _json(value, limit=MAX_JSON_BYTES):
    try:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("Catalog input must contain bounded, finite JSON data.") from None
    if len(encoded) > limit:
        raise ValueError("A catalog record or review report exceeds the JSON size limit.")
    return encoded


def _text(value, limit=500):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _norm(value):
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def _array(snapshot, key, limit):
    value = snapshot.get(key)
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(row, dict) for row in value):
        raise ValueError("Catalog snapshot has an invalid or oversized record collection.")
    return value


def _cohort(row):
    if type(row.get("year")) is not int or not 1900 <= row["year"] <= 2200:
        raise ValueError("Catalog cohorts require an explicit year.")
    if row.get("size_band") not in {"0-10kW", "10-20kW"} or row.get("technology") not in {"PV Only", "PV+Storage"}:
        raise ValueError("Catalog cohort labels must match the source contract.")
    if not _text(row.get("state"), 100):
        raise ValueError("Catalog observations require their source state.")


def _validate_snapshot_data(snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("source"), dict):
        raise ValueError("Provide a normalized SolarTRACE snapshot.")
    source = snapshot["source"]
    if source.get("dataset_id") != "solartrace" or not _text(source.get("version")):
        raise ValueError("Catalog source must identify the SolarTRACE dataset and version.")
    if not isinstance(source.get("source_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", source["source_sha256"]):
        raise ValueError("Catalog source requires its exact SHA-256 digest.")
    _json(source)
    _json(snapshot.get("stats", {}))
    entities = {}
    for row in _array(snapshot, "entities", 100_000):
        ident = row.get("entity_id")
        if not _text(ident) or ident in entities or row.get("kind") not in KINDS or not _text(row.get("name"), 2000):
            raise ValueError("Catalog entities require unique IDs, supported kinds, and source names.")
        states, identifiers = row.get("states"), row.get("source_identifiers")
        if not isinstance(states, list) or any(not _text(state, 100) for state in states) or not isinstance(identifiers, dict):
            raise ValueError("Catalog entities require source states and opaque identifier objects.")
        if any(not _text(value) for value in identifiers.values()) or row.get("identity_status") not in {"source_id", "unresolved"}:
            raise ValueError("Catalog identifiers must be nonempty strings with an explicit identity status.")
        if not isinstance(row.get("aliases"), list) or not isinstance(row.get("source_refs"), list):
            raise ValueError("Catalog entities require alias and source-reference lists.")
        _json(row)
        entities[ident] = row
    for row in _array(snapshot, "requirements", 100_000):
        if row.get("entity_id") not in entities or not _text(row.get("state"), 100) or not isinstance(row.get("fields"), dict):
            raise ValueError("Requirement observations require a known entity, state, and original fields.")
        if not _text(row.get("source_sheet")) or type(row.get("source_row")) is not int or row["source_row"] < 1:
            raise ValueError("Requirement observations require original sheet and row references.")
        _json(row)
    seen = set()
    for row in _array(snapshot, "benchmarks", 1_000_000):
        _cohort(row)
        ident, metric = row.get("benchmark_id"), row.get("metric")
        if not _text(ident) or ident in seen or row.get("entity_id") not in entities or metric not in METRICS:
            raise ValueError("Benchmarks require unique IDs, known entities, and supported metrics.")
        seen.add(ident)
        kind = "building_department" if metric in {"ahj_permit", "inspection"} else "utility_company"
        if entities[row["entity_id"]]["kind"] != kind or row.get("unit") != "business_days" or row.get("statistic") != "median" or row.get("sample_n") is not None:
            raise ValueError("Benchmark scope, median units, and unknown metric sample sizes must be preserved.")
        values, value = row.get("values"), row.get("value")
        numeric = lambda item: type(item) in (int, float) and math.isfinite(item)
        if not isinstance(values, list) or any(not numeric(item) for item in values):
            raise ValueError("Benchmark values must retain finite reported observations.")
        distinct = set(values)
        if row.get("status") == "reported":
            if (value is None and distinct) or (value is not None and (not numeric(value) or distinct != {value})):
                raise ValueError("Reported benchmarks must have one consistent value.")
        elif row.get("status") == "conflict":
            if value is not None or len(distinct) < 2:
                raise ValueError("Conflicting benchmarks must retain alternatives without a selected value.")
        else:
            raise ValueError("Benchmark status must be reported or conflict.")
        if not isinstance(row.get("source_refs"), list) or not isinstance(row.get("flags"), list) or type(row.get("unknown_references_count")) is not int or row["unknown_references_count"] < 0:
            raise ValueError("Benchmark provenance and unknown-reference counts must be retained.")
        _json(row)
    for row in _array(snapshot, "installations", 1_000_000):
        _cohort(row)
        for key, kind in (("ahj_id", "building_department"), ("utility_id", "utility_company")):
            ident = row.get(key)
            if ident is not None and (ident not in entities or entities[ident]["kind"] != kind):
                raise ValueError("Installation counts require correctly typed source entity references.")
        if type(row.get("count")) not in (int, float) or not math.isfinite(row["count"]) or row["count"] <= 0:
            raise ValueError("Only positive reported installation counts belong in the normalized count table.")
        _json(row)
    seen = set()
    for row in _array(snapshot, "source_rows", 100_000):
        key = (row.get("sheet"), row.get("row"))
        if not _text(key[0]) or type(key[1]) is not int or key[1] < 1 or key in seen or not isinstance(row.get("values"), list):
            raise ValueError("Source rows require unique original sheet/row coordinates and cell values.")
        seen.add(key)
        _json(row)


def _validate_snapshot(snapshot):
    try:
        _validate_snapshot_data(snapshot)
    except (TypeError, KeyError, RecursionError, OverflowError):
        raise ValueError("Catalog snapshot fields do not match the normalized source contract.") from None


def _db_path(value, *, must_exist=True):
    path = private_path(value)
    if path.exists():
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_mode & 0o077:
            raise ValueError("Use a private, owner-only regular catalog file without hard links.")
    elif must_exist:
        raise ValueError("The private catalog does not exist. Initialize it first.")
    return path


def _connect(path, mode):
    connection = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=" + mode, uri=True, timeout=10)
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        if mode == "ro":
            connection.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def _check(connection):
    if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        raise ValueError("File is not a supported Sun Bridge catalog; it was not modified.")
    tables = dict(connection.execute("SELECT name, sql FROM sqlite_schema WHERE type='table'"))
    if tables != SCHEMA or connection.execute("SELECT 1 FROM sqlite_schema WHERE type IN ('view','trigger') LIMIT 1").fetchone():
        raise ValueError("Catalog schema does not match this release; it was not modified.")
    metadata = dict(connection.execute("SELECT key,value FROM meta"))
    if metadata.get("schema_version") != str(SCHEMA_VERSION) or metadata.get("dataset_id") != "solartrace":
        raise ValueError("Catalog source or schema version is not supported.")
    active = metadata.get("active_source")
    row = connection.execute("SELECT source_id, source_json, sha256 FROM sources WHERE source_id=?", (active,)).fetchone()
    source = json.loads(row[1]) if row is not None else None
    if not isinstance(source, dict) or source.get("dataset_id") != "solartrace" or not _text(source.get("version")) or source.get("source_sha256") != row[2] or not re.fullmatch(r"[a-f0-9]{64}", row[2]):
        raise ValueError("Catalog has no valid active SolarTRACE source.")
    return row[0]


@contextmanager
def _database(value, *, write=False):
    path = _db_path(value)
    connection = None
    try:
        # Validate before opening a writable connection, so invalid files remain untouched.
        connection = _connect(path, "ro")
        active = _check(connection)
        if write:
            connection.close()
            connection = _connect(_db_path(path), "rw")
            active = _check(connection)
            connection.execute("BEGIN IMMEDIATE")
        yield connection, active
        if write:
            connection.commit()
    except (sqlite3.Error, json.JSONDecodeError, UnicodeError):
        raise ValueError("Could not read or update the private catalog. Check its format, permissions, and availability.") from None
    finally:
        if connection is not None:
            connection.close()


def _insert_snapshot(connection, snapshot):
    source = snapshot["source"]
    existing = connection.execute("SELECT source_id,source_json FROM sources WHERE sha256=?", (source["source_sha256"],)).fetchone()
    if existing:
        previous = json.loads(existing[1])
        if previous.get("version") != source["version"] or previous.get("dataset_id") != source["dataset_id"]:
            raise ValueError("The same source digest cannot be relabeled as a different dataset version.")
        source_id, status = existing[0], "already_present"
    else:
        cursor = connection.execute("INSERT INTO sources(sha256,source_json,stats_json) VALUES (?,?,?)", (source["source_sha256"], _json(source), _json(snapshot.get("stats", {}))))
        source_id, status = cursor.lastrowid, "imported"
        connection.executemany("INSERT INTO entities VALUES (?,?,?,?,?)", ((source_id, row["entity_id"], row["kind"], row["name"], _json(row)) for row in snapshot["entities"]))
        connection.executemany("INSERT INTO requirements(source_id,entity_id,state,payload_json) VALUES (?,?,?,?)", ((source_id, row["entity_id"], row["state"], _json(row)) for row in snapshot["requirements"]))
        connection.executemany("INSERT INTO benchmarks VALUES (?,?,?,?,?,?)", ((source_id, row["benchmark_id"], row["entity_id"], row["state"], row["metric"], _json(row)) for row in snapshot["benchmarks"]))
        connection.executemany("INSERT INTO installations(source_id,ahj_id,utility_id,state,payload_json) VALUES (?,?,?,?,?)", ((source_id, row.get("ahj_id"), row.get("utility_id"), row["state"], _json(row)) for row in snapshot["installations"]))
        connection.executemany("INSERT INTO source_rows VALUES (?,?,?,?)", ((source_id, row["sheet"], row["row"], _json(row)) for row in snapshot["source_rows"]))
    connection.execute("INSERT OR REPLACE INTO meta VALUES ('active_source',?)", (str(source_id),))
    counts = {name: connection.execute("SELECT COUNT(*) FROM " + name + " WHERE source_id=?", (source_id,)).fetchone()[0] for name in ("entities", "requirements", "benchmarks", "installations", "source_rows")}
    return {"status": status, "active_source_sha256": source["source_sha256"], "counts": counts, "source_versions": connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0], "crm_writes": 0}


def init_catalog(db_path, snapshot):
    """Atomically create a private catalog or retain and activate a source version."""
    _validate_snapshot(snapshot)
    path = _db_path(db_path, must_exist=False)
    if path.exists():
        with _database(path, write=True) as (connection, _):
            return _insert_snapshot(connection, snapshot)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".sunbridge-catalog-", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    connection = None
    try:
        connection = _connect(temporary, "rw")
        for statement in SCHEMA.values():
            connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.executemany("INSERT INTO meta VALUES (?,?)", (("schema_version", str(SCHEMA_VERSION)), ("dataset_id", "solartrace")))
        result = _insert_snapshot(connection, snapshot)
        connection.commit()
        connection.close()
        connection = None
        # Publish without replacing a file created by someone else during import.
        os.link(temporary, path)
        return result
    except (sqlite3.Error, OSError):
        raise ValueError("Could not create the private catalog. Existing files were not replaced.") from None
    finally:
        if connection is not None:
            connection.close()
        temporary.unlink(missing_ok=True)


def _source(connection, active):
    return json.loads(connection.execute("SELECT source_json FROM sources WHERE source_id=?", (active,)).fetchone()[0])


def _entities(connection, active):
    return [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM entities WHERE source_id=? ORDER BY name,entity_id", (active,))]


def _in_state(entity, state):
    return state is None or _norm(state) in {_norm(value) for value in entity.get("states", [])}


def _filters(state, kind=None):
    if state is not None and not _text(state, 100):
        raise ValueError("State filters must be nonempty source-state strings.")
    if kind is not None and (not isinstance(kind, str) or kind not in KINDS):
        raise ValueError("Choose building_department or utility_company.")


def search_catalog(db_path, query="", state=None, kind=None, limit=50):
    _filters(state, kind)
    if not isinstance(query, str) or len(query) > 2000 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Use a bounded text query and a result limit from 1 to 1000.")
    needle = _norm(query)
    with _database(db_path) as (connection, active):
        found = []
        for row in _entities(connection, active):
            if not _in_state(row, state) or (kind is not None and row["kind"] != kind):
                continue
            searchable = [row["entity_id"], row["name"], *row["source_identifiers"].values()]
            searchable += [alias.get("name", "") for alias in row["aliases"] if isinstance(alias, dict)]
            if needle and not any(needle in _norm(value) for value in searchable):
                continue
            found.append(row)
            if len(found) == limit:
                break
        return found


def show_entity(db_path, entity_id):
    if not _text(entity_id):
        raise ValueError("Choose an exact catalog entity ID.")
    with _database(db_path) as (connection, active):
        row = connection.execute("SELECT payload_json FROM entities WHERE source_id=? AND entity_id=?", (active, entity_id)).fetchone()
        if row is None:
            raise ValueError("Entity is not present in the active source version.")
        result = {"entity": json.loads(row[0]), "source": _source(connection, active)}
        for table in ("requirements", "benchmarks"):
            result[table] = [json.loads(item[0]) for item in connection.execute("SELECT payload_json FROM " + table + " WHERE source_id=? AND entity_id=?", (active, entity_id))]
        result["proposed_events"] = [{"report_sha256": row[0], "input_position": row[1], "source_sha256": row[2], "proposal": json.loads(row[3])} for row in connection.execute("SELECT p.report_sha256,p.input_position,s.sha256,p.payload_json FROM proposed_events p JOIN sources s ON s.source_id=p.source_id WHERE p.entity_id=? ORDER BY p.report_sha256,p.input_position", (entity_id,))]
        return result


def export_catalog(db_path, state=None):
    _filters(state)
    with _database(db_path) as (connection, active):
        entities = [entity for entity in _entities(connection, active) if _in_state(entity, state)]
        selected = {entity["entity_id"] for entity in entities}
        result = {"organizations": entities, "source": _source(connection, active)}
        for table in ("requirements", "benchmarks"):
            result[table] = [json.loads(row[2]) for row in connection.execute("SELECT entity_id,state,payload_json FROM " + table + " WHERE source_id=?", (active,)) if row[0] in selected and (state is None or _norm(row[1]) == _norm(state))]
        return result


def reconcile_organizations(db_path, records):
    if not isinstance(records, list) or len(records) > 100_000 or any(not isinstance(record, dict) for record in records):
        raise ValueError("Supply a bounded list of normalized organization records.")
    _json(records)
    with _database(db_path) as (connection, active):
        entities = _entities(connection, active)
        source = _source(connection, active)
    native_index, name_index = {}, {}
    for entity in entities:
        kind, ident = entity["kind"], entity["entity_id"]
        states = {_norm(state) for state in entity["states"]}
        key = "geo_id" if kind == "building_department" else "eia_id"
        native = entity["source_identifiers"].get(key)
        for state in states:
            name_index.setdefault((kind, state, _norm(entity["name"])), set()).add(ident)
            if entity["identity_status"] == "source_id" and native:
                native_index.setdefault((kind, state, key, native), set()).add(ident)
        for alias in entity["aliases"]:
            if isinstance(alias, dict) and _norm(alias.get("state")) in states and _norm(alias.get("name")):
                name_index.setdefault((kind, _norm(alias["state"]), _norm(alias["name"])), set()).add(ident)
    items = []
    for record in records:
        item = {"organization_id": record.get("organization_id"), "name": record.get("name"), "kind": record.get("kind"), "state": record.get("state"), "status": "held", "candidates": [], "review_required": True, "issues": []}
        kind, state = record.get("kind"), record.get("state")
        ident = record.get("organization_id")
        if (type(ident) is not int and not _text(ident)) or (type(ident) is int and ident <= 0):
            item["issues"].append("organization_id_required")
        elif not isinstance(kind, str) or kind not in KINDS or not _text(state, 100):
            item["issues"].append("explicit_supported_kind_and_state_required")
        else:
            key = "geo_id" if kind == "building_department" else "eia_id"
            other_key = "eia_id" if kind == "building_department" else "geo_id"
            native = record.get(key)
            if record.get(other_key) not in (None, ""):
                item["issues"].append("native_identifier_kind_mismatch")
            elif native is not None and native != "":
                if not _text(native):
                    item["issues"].append("native_identifier_must_be_an_opaque_string")
                else:
                    candidates = sorted(native_index.get((kind, _norm(state), key, native.strip()), set()))
                    item["candidates"] = candidates
                    item["status"] = "exact_identifier_candidate" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched"
                    if not candidates:
                        item["issues"].append("identifier_not_resolved_in_state_no_name_fallback")
            elif _text(record.get("name"), 2000):
                candidates = sorted(name_index.get((kind, _norm(state), _norm(record["name"])), set()))
                item["candidates"] = candidates
                item["status"] = "name_candidate" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched"
            else:
                item["issues"].append("source_identifier_or_name_required")
        items.append(item)
    counts = {status: sum(item["status"] == status for item in items) for status in ("exact_identifier_candidate", "name_candidate", "ambiguous", "unmatched", "held")}
    return {"mode": "review_only", "crm_writes": 0, "source": source, "items": items, "summary": counts,
            "warning": "Candidates only. Review identity and jurisdiction; no organizations were created, merged, or updated."}


def attach_review(db_path, report, profile_links):
    """Store proposals through an explicit operator-reviewed crosswalk, atomically."""
    if not isinstance(report, dict) or report.get("mode") != "review_only" or type(report.get("crm_writes")) is not int or report["crm_writes"] != 0:
        raise ValueError("Attach only a review-only report with zero CRM writes.")
    items = report.get("items")
    if not isinstance(items, list) or len(items) > 10000 or not isinstance(profile_links, dict):
        raise ValueError("Provide a bounded review report and an explicit profile-to-entity crosswalk.")
    encoded = _json(report)
    links_json = _json(profile_links)
    digest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    with _database(db_path, write=True) as (connection, active):
        entities = {entity["entity_id"]: entity for entity in _entities(connection, active)}
        for profile, entity_id in profile_links.items():
            if not _text(profile) or not _text(entity_id) or entity_id not in entities or entities[entity_id]["kind"] != "building_department":
                raise ValueError("Each reviewed profile link must name an active building-department entity.")
        staged, positions, skipped = [], set(), 0
        for row in items:
            if not isinstance(row, dict) or type(row.get("input_position")) is not int or row["input_position"] < 1 or row["input_position"] in positions:
                raise ValueError("Review input positions must be unique positive integers.")
            positions.add(row["input_position"])
            event = row.get("event")
            if not isinstance(event, dict) or event.get("review_required") is not True:
                raise ValueError("Every attached event must remain a review-required proposal.")
            profile = event.get("ahj_id")
            if profile is None or profile == "":
                skipped += 1
                continue
            if not _text(profile) or profile not in profile_links:
                raise ValueError("A report AHJ is unmapped. Review every profile link before attaching any events.")
            staged.append((digest, row["input_position"], active, profile_links[profile], profile, _json(row)))
        existing = connection.execute("SELECT profile_links_json FROM review_reports WHERE report_sha256=?", (digest,)).fetchone()
        if existing:
            if existing[0] != links_json:
                raise ValueError("This report already has a different crosswalk. Its existing proposals were not reassigned.")
            return {"report_sha256": digest, "attached": 0, "already_present": len(staged), "skipped_empty_ahj": skipped, "crm_writes": 0}
        connection.execute("INSERT INTO review_reports VALUES (?,?,?,?)", (digest, active, links_json, encoded))
        connection.executemany("INSERT INTO proposed_events VALUES (?,?,?,?,?,?)", staged)
        return {"report_sha256": digest, "attached": len(staged), "already_present": 0, "skipped_empty_ahj": skipped, "crm_writes": 0}
