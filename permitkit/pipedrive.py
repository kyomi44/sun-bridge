"""Read-only Pipedrive organization inventory, retained only in a private directory.

Only the organization-fields and organizations GET endpoints are implemented.
Office addresses, people, deals, notes and related counts are never exported.
CRM values are unverified observations, not verified jurisdiction boundaries.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


API_BASE = "https://api.pipedrive.com"
ALLOWED_PATHS = {"/api/v2/organizationFields", "/api/v2/organizations"}


class PipedriveError(RuntimeError):
    """Safe to display: never includes response bodies, URLs or credentials."""


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_token(token_file: Path | None = None) -> str:
    token = os.environ.get("PIPEDRIVE_API_TOKEN", "").strip()
    if token_file is not None:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise PipedriveError("Could not read the Pipedrive token file.") from None
    if not token or not re.fullmatch(r"[A-Za-z0-9._-]+", token) or len(token) > 4096:
        raise PipedriveError("Provide a valid token file or PIPEDRIVE_API_TOKEN.")
    return token


class PipedriveClient:
    def __init__(self, token: str):
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirects())

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        if path not in ALLOWED_PATHS:
            raise PipedriveError("This importer only permits organization inventory GET requests.")
        url = API_BASE + path + "?" + urllib.parse.urlencode(params or {})
        request = urllib.request.Request(
            url, method="GET",
            headers={"x-api-token": self._token, "Accept": "application/json",
                     "User-Agent": "solar-bridge-readonly/0.1"},
        )
        for attempt in range(4):
            try:
                with self._opener.open(request, timeout=45) as response:
                    raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise PipedriveError("Pipedrive response exceeded the inventory size limit.")
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise PipedriveError("Pipedrive returned an invalid JSON response.") from None
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    raise PipedriveError("Pipedrive did not return a successful inventory response.")
                return payload
            except urllib.error.HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                exc.close()
                if (status == 429 or 500 <= status <= 599) and attempt < 3:
                    delay = min(float(retry_after), 20) if re.fullmatch(r"\d+(?:\.\d+)?", retry_after) else 2 ** attempt
                    time.sleep(delay)
                    continue
                raise PipedriveError(f"Pipedrive inventory GET failed (HTTP {status}).") from None
            except (urllib.error.URLError, OSError, TimeoutError):
                raise PipedriveError("Could not connect to Pipedrive for the inventory GET.") from None
        raise PipedriveError("Pipedrive inventory retries exhausted.")

    def pages(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        query = {"limit": 500, **(params or {})}
        seen_cursors: set[str] = set()
        while True:
            payload = self.get(path, query)
            rows = payload.get("data")
            if rows is None:
                rows = []
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise PipedriveError("Pipedrive returned an unexpected inventory data shape.")
            yield from rows
            extra = payload.get("additional_data") or {}
            if not isinstance(extra, dict):
                raise PipedriveError("Pipedrive returned invalid pagination metadata.")
            pagination = extra.get("pagination") or {}
            if not isinstance(pagination, dict):
                raise PipedriveError("Pipedrive returned invalid pagination metadata.")
            cursor = extra.get("next_cursor") or pagination.get("next_cursor")
            more = extra.get("more_items_in_collection") or pagination.get("more_items_in_collection")
            if not cursor:
                if more:
                    raise PipedriveError("Pipedrive indicated another page without a cursor.")
                break
            if not isinstance(cursor, str) or cursor in seen_cursors:
                raise PipedriveError("Pipedrive returned an invalid or repeated pagination cursor.")
            seen_cursors.add(cursor)
            query["cursor"] = cursor


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def field_code(field: dict) -> str:
    return str(field.get("field_code") or field.get("key") or "")


def field_name(field: dict) -> str:
    return str(field.get("field_name") or field.get("name") or "")


def _options(field: dict) -> dict[str, str]:
    return {str(option["id"]): str(option["label"])
            for option in field.get("options", []) or []
            if isinstance(option, dict) and "id" in option and "label" in option}


def decode_value(value: Any, field: dict) -> Any:
    """Decode v1/v2 enum, option objects, multi-options and scalar values."""
    if value is None:
        return None
    if isinstance(value, list):
        return [decode_value(item, field) for item in value]
    if isinstance(value, dict):
        if "label" in value:
            return str(value["label"])
        if "value" in value:
            return decode_value(value["value"], field)
        if "id" in value:
            return _options(field).get(str(value["id"]), value["id"])
        return None
    options = _options(field)
    if field.get("field_type") == "set" and isinstance(value, str) and "," in value:
        return [decode_value(item.strip(), field) for item in value.split(",")]
    return options.get(str(value), value)


def _contains_label(value: Any, label: str) -> bool:
    if isinstance(value, list):
        return any(_contains_label(item, label) for item in value)
    return _norm(value) == _norm(label)


def discover_type_field(fields: list[dict], override: str | None = None,
                        label: str = "Building Department") -> dict:
    if override:
        exact_code = [f for f in fields if field_code(f) == override]
        candidates = exact_code or [f for f in fields if _norm(field_name(f)) == _norm(override)]
    else:
        candidates = [f for f in fields if _norm(field_name(f)) == "type"]
        if not candidates:
            candidates = [f for f in fields if any(_norm(v) == _norm(label) for v in _options(f).values())]
    if len(candidates) != 1 or not field_code(candidates[0]):
        raise PipedriveError("Organization Type field is missing or ambiguous; supply its exact field code.")
    field = candidates[0]
    if _options(field) and not any(_norm(v) == _norm(label) for v in _options(field).values()):
        raise PipedriveError("The selected organization Type field has no matching department option.")
    return field


ROLE_NAMES = {
    "jurisdiction_type": {"jurisdiction", "jurisdiction type", "jurisdiction level", "ahj type", "ahj level", "government level", "city or county", "county or city", "city county", "county city"},
    "state": {"state", "jurisdiction state", "ahj state"},
    "county": {"county", "jurisdiction county", "ahj county", "county name"},
    "city": {"city", "jurisdiction city", "ahj city", "city name", "municipality"},
    "country": {"country", "jurisdiction country", "ahj country"},
    "parent_organization": {"parent organization", "parent organisation", "parent jurisdiction", "parent ahj"},
}


def discover_metadata_fields(fields: list[dict], type_field: dict) -> dict[str, list[dict]]:
    selected: dict[str, list[dict]] = {role: [] for role in ROLE_NAMES}
    for field in fields:
        if field_code(field) == field_code(type_field):
            continue
        name = " ".join(re.sub(r"[^a-z0-9]+", " ", field_name(field).casefold()).split())
        # No address component is a jurisdiction field, even if its display label is "City".
        code = field_code(field)
        if code == "address" or code.startswith("address_") or field.get("field_type") == "address":
            continue
        for role, names in ROLE_NAMES.items():
            if name in names and code:
                selected[role].append(field)
    return selected


def _value(row: dict, field: dict) -> Any:
    code = field_code(field)
    custom = row.get("custom_fields") or {}
    return decode_value(custom.get(code) if code in custom else row.get(code), field)


def _jurisdiction_kind(value: Any) -> str:
    labels = value if isinstance(value, list) else [value]
    kinds = {_norm(v) for v in labels if v is not None}
    known = {"city", "county", "town", "township", "village", "borough", "state", "regional", "special district"}
    if len(kinds) == 1 and next(iter(kinds)) in known:
        return next(iter(kinds))
    return "unknown"


def project_organization(row: dict, type_field: dict, metadata_fields: dict[str, list[dict]],
                         type_label: str = "Building Department") -> dict | None:
    org_type = _value(row, type_field)
    if not _contains_label(org_type, type_label):
        return None
    org_id = row.get("id")
    if isinstance(org_id, bool) or not isinstance(org_id, int) or org_id < 1:
        raise PipedriveError("A building department record has an invalid organization ID.")
    evidence: dict[str, list[dict]] = {}
    metadata: dict[str, Any] = {}
    relationships: list[dict] = []
    for role, fields in metadata_fields.items():
        evidence[role] = [{"field_code": field_code(f), "field_name": field_name(f), "field_type": f.get("field_type"), "value": _value(row, f)} for f in fields]
        for item in evidence[role]:
            if item["field_type"] != "org" or item["value"] in (None, "", []):
                continue
            target_id = item["value"]
            if isinstance(target_id, str) and target_id.isdigit():
                target_id = int(target_id)
            if isinstance(target_id, bool) or not isinstance(target_id, int) or target_id < 1:
                continue
            relationships.append({"role": role, "field_name": item["field_name"],
                                  "target_organization_id": target_id, "scope": "crm_reference_only"})
        populated = [item["value"] for item in evidence[role] if item["field_type"] != "org" and item["value"] not in (None, "", [])]
        # Two conflicting fields remain visible for review without silently choosing one.
        metadata[role] = populated[0] if populated and all(v == populated[0] for v in populated) else None
    county_ids = {r["target_organization_id"] for r in relationships if r["role"] == "county"}
    metadata["county_organization_id"] = next(iter(county_ids)) if len(county_ids) == 1 else None
    return {
        "local_candidate_id": f"pending/pipedrive/{org_id}",
        "crm": {"system": "pipedrive", "organization_id": org_id},
        "organization_name": str(row.get("name") or ""),
        "organization_type": org_type,
        "jurisdiction_type": _jurisdiction_kind(metadata.get("jurisdiction_type")),
        "metadata": metadata,
        "metadata_evidence": evidence,
        "organization_relationships": relationships,
        "verification_status": "unverified_crm_record",
        "public_ahj_id": None,
    }


def resolve_inventory_relationships(records: list[dict]) -> None:
    """Resolve only targets in the retained department inventory, never fetch others."""
    by_id = {r["crm"]["organization_id"]: r for r in records}
    for record in records:
        for relationship in record["organization_relationships"]:
            target = by_id.get(relationship["target_organization_id"])
            relationship["target_in_inventory"] = target is not None
            relationship["target_name"] = target["organization_name"] if target else None
            relationship["target_jurisdiction_type"] = target["jurisdiction_type"] if target else "unknown"


def build_summary(records: list[dict], type_field: dict, metadata_fields: dict[str, list[dict]]) -> dict:
    names = Counter(_norm(r["organization_name"]) for r in records)
    county_refs = [(r, rel) for r in records for rel in r["organization_relationships"] if rel["role"] == "county"]
    return {
        "building_department_count": len(records),
        "jurisdiction_type_counts": dict(sorted(Counter(r["jurisdiction_type"] for r in records).items())),
        "missing_metadata_counts": {role: sum(r["metadata"].get(role) in (None, "", []) for r in records) for role in [*ROLE_NAMES, "county_organization_id"]},
        "county_relationship_counts": {
            "total_references": len(county_refs),
            "city_records_with_reference": sum(r["jurisdiction_type"] == "city" and r["metadata"]["county_organization_id"] is not None for r in records),
            "target_in_inventory": sum(rel.get("target_in_inventory", False) for _, rel in county_refs),
            "target_missing_from_inventory": sum(not rel.get("target_in_inventory", False) for _, rel in county_refs),
            "target_jurisdiction_types": dict(sorted(Counter(rel.get("target_jurisdiction_type", "unknown") for _, rel in county_refs).items())),
            "interpretation": "CRM County references only; no legal or regulatory parent relationship inferred.",
        },
        "duplicate_name_groups": sum(n > 1 for name, n in names.items() if name),
        "records_in_duplicate_name_groups": sum(n for name, n in names.items() if name and n > 1),
        "type_field": {"name": field_name(type_field), "code": field_code(type_field)},
        "selected_metadata_fields": {role: [{"name": field_name(f), "code": field_code(f), "field_type": f.get("field_type")} for f in fields] for role, fields in metadata_fields.items()},
        "scope_note": "Only matching building department projections retained. Mailing addresses do not determine jurisdiction. No public profiles generated.",
    }


def _write_private_json(path: Path, value: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def import_building_departments(token_file: Path | None, output_dir: Path,
                                type_field: str | None = None,
                                type_label: str = "Building Department") -> dict:
    """Create private inventory/candidates; perform no Pipedrive mutations.

    The CLI additionally enforces its own project-private root. This function
    requires a resolved path containing a directory literally named ``private``.
    """
    output_dir = Path(output_dir).resolve()
    if "private" not in output_dir.parts:
        raise PipedriveError("Pipedrive inventory output must remain inside a private directory.")
    client = PipedriveClient(read_token(token_file))
    fields = list(client.pages("/api/v2/organizationFields"))
    selected_type = discover_type_field(fields, type_field, type_label)
    metadata_fields = discover_metadata_fields(fields, selected_type)
    selected = [selected_type] + [f for group in metadata_fields.values() for f in group]
    codes = list(dict.fromkeys(field_code(f) for f in selected))
    if len(codes) > 15:
        raise PipedriveError("More than 15 relevant organization fields were found; narrow the field selection before importing.")
    params = {"custom_fields": ",".join(codes), "include_option_labels": "true", "sort_by": "id", "sort_direction": "asc"}
    records: list[dict] = []
    seen_ids: set[int] = set()
    for row in client.pages("/api/v2/organizations", params):
        record = project_organization(row, selected_type, metadata_fields, type_label)
        if record is None:
            continue
        org_id = record["crm"]["organization_id"]
        if org_id in seen_ids:
            raise PipedriveError("Pipedrive returned a duplicate building department ID; retry after records stabilize.")
        seen_ids.add(org_id)
        records.append(record)
    records.sort(key=lambda item: item["crm"]["organization_id"])
    resolve_inventory_relationships(records)
    summary = build_summary(records, selected_type, metadata_fields)
    summary["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_private_json(output_dir / "building_departments.json", records)
    _write_private_json(output_dir / "import_summary.json", summary)
    _write_private_json(output_dir / "profile_candidates.json", [{
        "local_candidate_id": r["local_candidate_id"],
        "display_name_from_crm": r["organization_name"],
        "public_ahj_id": None,
        "jurisdiction_type_from_crm": r["jurisdiction_type"],
        "geography_from_crm": {k: r["metadata"].get(k) for k in ("country", "state", "county", "city")},
        "crm_relationships": r["organization_relationships"],
        "verification_status": "needs_official_source_review",
        "official_sources": [],
        "status_channels": [],
    } for r in records])
    _write_private_json(output_dir / "crm_mapping.json", {r["local_candidate_id"]: r["crm"] for r in records})
    return summary
