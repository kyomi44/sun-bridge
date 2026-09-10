"""Read-only, explicitly scoped Pipedrive deal-to-permit adapter.

This client cannot list deals. It reads schema metadata and individual IDs
provided by the caller, retaining only mapped permit fields. It does not write
files; the CLI applies the existing private-output boundary.
"""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .pipedrive import PipedriveError, _NoRedirects, read_token
from .reconcile import normalize_address


API_BASE = "https://api.pipedrive.com"
FIELDS_PATH = "/api/v2/dealFields"
CUSTOM_CODE = re.compile(r"[a-f0-9]{40}")
TEXT_TYPES = {"varchar", "varchar_auto", "text"}
MAPPING_KEYS = {"schema_version", "ahj_field", "permit_fields", "address_field", "customer_name_field", "ahj_map"}
MAX_METADATA_FIELDS = 10_000
MAX_METADATA_PAGES = 100
MAX_METADATA_OPTIONS = 10_000


class DealAdapterError(PipedriveError):
    """A sanitized failure with an optional non-sensitive HTTP status."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


class DealClient:
    """Fixed-host GET transport; deal details require an explicit ID allowlist."""

    def __init__(self, token: str, deal_ids: list[int] | None = None):
        ids = _deal_ids(deal_ids) if deal_ids is not None else []
        self._allowed_ids = frozenset(ids)
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirects())

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        params = dict(params or {})
        if path == FIELDS_PATH:
            allowed_params = {"limit", "cursor"}
        else:
            match = re.fullmatch(r"/api/v2/deals/([1-9][0-9]*)", path)
            if not match or int(match[1]) not in self._allowed_ids:
                raise DealAdapterError("Only explicitly selected deal IDs and deal field metadata may be read.")
            allowed_params = {"custom_fields", "include_option_labels"}
        if set(params) - allowed_params:
            raise DealAdapterError("Unsupported parameter for the scoped deal adapter.")
        if "custom_fields" in params:
            codes = str(params["custom_fields"]).split(",")
            if not 1 <= len(codes) <= 15 or any(not CUSTOM_CODE.fullmatch(code) for code in codes):
                raise DealAdapterError("Select at most 15 exact custom field codes.")
        request = urllib.request.Request(
            API_BASE + path + "?" + urllib.parse.urlencode(params), method="GET",
            headers={"x-api-token": self._token, "Accept": "application/json",
                     "User-Agent": "sun-bridge-readonly/0.1"},
        )
        for attempt in range(4):
            try:
                with self._opener.open(request, timeout=45) as response:
                    raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise DealAdapterError("Pipedrive response exceeded the scoped adapter size limit.")
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise DealAdapterError("Pipedrive returned an invalid JSON response.") from None
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    raise DealAdapterError("Pipedrive did not return a successful scoped response.")
                return payload
            except urllib.error.HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                exc.close()
                if (status == 429 or 500 <= status <= 599) and attempt < 3:
                    delay = min(float(retry_after), 20) if re.fullmatch(r"\d+(?:\.\d+)?", retry_after) else 2 ** attempt
                    time.sleep(delay)
                    continue
                raise DealAdapterError(f"Pipedrive scoped GET failed (HTTP {status}).", status) from None
            except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException):
                raise DealAdapterError("Could not connect to Pipedrive for the scoped GET.") from None
        raise DealAdapterError("Pipedrive scoped GET retries exhausted.")

    def fields(self) -> list[dict]:
        result = []
        cursor = None
        seen_cursors = set()
        option_count = 0
        for _ in range(MAX_METADATA_PAGES):
            params = {"limit": 500}
            if cursor:
                params["cursor"] = cursor
            payload = self.get(FIELDS_PATH, params)
            rows = payload.get("data")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise DealAdapterError("Pipedrive returned an invalid deal field schema.")
            if len(result) + len(rows) > MAX_METADATA_FIELDS:
                raise DealAdapterError("Pipedrive deal field metadata exceeded the field-count limit.")
            for row in rows:
                code = row.get("field_code", row.get("key"))
                name = row.get("field_name", row.get("name"))
                kind = row.get("field_type")
                if not all(isinstance(value, str) and value for value in (code, name, kind)):
                    raise DealAdapterError("Pipedrive returned incomplete deal field metadata.")
                field = {"code": code, "name": name, "type": kind}
                options = _field_options(row, code, kind)
                if options is not None:
                    option_count += len(options)
                    if option_count > MAX_METADATA_OPTIONS:
                        raise DealAdapterError("Pipedrive deal field metadata exceeded the option-count limit.")
                    field["options"] = options
                result.append(field)
            extra = payload.get("additional_data") or {}
            if not isinstance(extra, dict) or not isinstance(extra.get("pagination") or {}, dict):
                raise DealAdapterError("Pipedrive returned invalid deal field pagination.")
            pagination = extra.get("pagination") or {}
            cursor = extra.get("next_cursor") or pagination.get("next_cursor")
            more = extra.get("more_items_in_collection") or pagination.get("more_items_in_collection")
            if not cursor:
                if more:
                    raise DealAdapterError("Pipedrive indicated another field page without a cursor.")
                break
            if not isinstance(cursor, str) or len(cursor) > 4096 or cursor in seen_cursors:
                raise DealAdapterError("Pipedrive returned a repeated or invalid field cursor.")
            seen_cursors.add(cursor)
        else:
            raise DealAdapterError("Pipedrive deal field metadata exceeded the page-count limit.")
        _field_index(result)
        return result


def _field_options(row: dict, code: str, kind: str) -> list[dict] | None:
    """Project the v2 schema's enum/set option metadata, never entity values.

    Missing/null options mean metadata was not supplied; an explicit empty list
    is retained. Custom option IDs are integers; built-in IDs may be strings.
    Option labels can contain horizontal tabs (for example, pasted labels).
    Preserve those exactly; JSON serialization escapes them. Other unprintable
    characters are rejected. Bounds are local safety limits, not claims about
    Pipedrive account limits.
    """
    if kind not in {"enum", "set"} or row.get("options") is None:
        return None
    options = row["options"]
    if not isinstance(options, list) or len(options) > MAX_METADATA_OPTIONS:
        raise DealAdapterError("Pipedrive returned invalid or oversized deal field option metadata.")
    result = []
    seen_ids = set()
    for option in options:
        if not isinstance(option, dict):
            raise DealAdapterError("Pipedrive returned malformed deal field option metadata.")
        ident, label = option.get("id"), option.get("label")
        valid_id = type(ident) is int and 0 < ident <= (2 ** 63 - 1)
        if not CUSTOM_CODE.fullmatch(code) and isinstance(ident, str):
            valid_id = 0 < len(ident) <= 128 and ident == ident.strip() and ident.isprintable()
        valid_label = (isinstance(label, str) and 0 < len(label) <= 1000
                       and bool(label.strip())
                       and all(char.isprintable() or char == "\t" for char in label))
        if not valid_id or not valid_label:
            raise DealAdapterError("Pipedrive returned malformed deal field option metadata.")
        if str(ident) in seen_ids:
            raise DealAdapterError("Pipedrive returned duplicate deal field option IDs.")
        seen_ids.add(str(ident))
        result.append({"id": ident, "label": label})
    return result


def _deal_ids(values: list[int]) -> list[int]:
    if not isinstance(values, list) or not values or any(type(value) is not int or value < 1 for value in values):
        raise DealAdapterError("Provide a nonempty list of positive integer deal IDs.")
    result = list(dict.fromkeys(values))
    if len(result) > 100:
        raise DealAdapterError("Import at most 100 unique, explicitly selected deal IDs per run.")
    return result


def _field_index(fields: list[dict]) -> dict[str, dict]:
    result = {}
    for field in fields:
        if field["code"] in result:
            raise DealAdapterError("Deal field metadata contains duplicate codes.")
        result[field["code"]] = field
    return result


def _mapping_shape(mapping: dict) -> None:
    if not isinstance(mapping, dict) or set(mapping) != MAPPING_KEYS:
        raise DealAdapterError("Mapping must contain exactly the documented version 1 keys.")
    if type(mapping["schema_version"]) is not int or mapping["schema_version"] != 1:
        raise DealAdapterError("Unsupported deal mapping schema version.")
    for name in ("ahj_field", "address_field"):
        if not isinstance(mapping[name], str) or not mapping[name] or mapping[name] != mapping[name].strip():
            raise DealAdapterError("AHJ and address mappings require exact field codes.")
    permits = mapping["permit_fields"]
    if not isinstance(permits, list) or not permits or any(not isinstance(code, str) or not code for code in permits):
        raise DealAdapterError("Select at least one exact permit field code.")
    if len(set(permits)) != len(permits):
        raise DealAdapterError("Permit field mappings cannot repeat a field code.")
    customer = mapping["customer_name_field"]
    if customer is not None and (not isinstance(customer, str) or not customer or customer != customer.strip()):
        raise DealAdapterError("Customer name field must be an exact code or null.")
    ahjs = mapping["ahj_map"]
    if not isinstance(ahjs, dict) or any(not isinstance(k, str) or not k or k != k.strip() or not isinstance(v, str) or not v or v != v.strip() for k, v in ahjs.items()):
        raise DealAdapterError("Supply an exact AHJ-value-to-profile-ID map.")


def validate_mapping(mapping: dict) -> dict:
    """Validate the offline v1 structure and return an independent copy.

    An empty AHJ map and field-code placeholders are structurally valid during
    setup. Metadata validation and the calling CLI's readiness checks happen
    before any deal detail is fetched.
    """
    _mapping_shape(mapping)
    return {**mapping, "permit_fields": list(mapping["permit_fields"]), "ahj_map": dict(mapping["ahj_map"])}


def _validate_mapping(mapping: dict, fields: list[dict]) -> list[str]:
    _mapping_shape(mapping)
    by_code = _field_index(fields)
    selections = [("ahj", mapping["ahj_field"]), ("address", mapping["address_field"])]
    selections += [("permit", code) for code in mapping["permit_fields"]]
    if mapping["customer_name_field"] is not None:
        selections.append(("customer", mapping["customer_name_field"]))
    custom = []
    for role, code in selections:
        if code not in by_code:
            raise DealAdapterError("A mapped field code was not found in deal metadata; labels and inferred fields are not accepted.")
        if (role == "ahj" and code == "org_id") or (role == "customer" and code == "title"):
            continue
        if not CUSTOM_CODE.fullmatch(code):
            raise DealAdapterError("Only custom field codes, AHJ org_id and optional customer title are supported.")
        allowed = TEXT_TYPES | ({"org", "enum"} if role == "ahj" else {"address"} if role == "address" else set())
        if by_code[code]["type"] not in allowed:
            raise DealAdapterError("A mapped custom field has an unsupported type for its role.")
        custom.append(code)
    custom = list(dict.fromkeys(custom))
    if len(custom) > 15:
        raise DealAdapterError("The selected mapping exceeds Pipedrive's 15-custom-field limit.")
    return custom


def _raw(row: dict, code: str) -> Any:
    if code in {"id", "title", "org_id"}:
        return row.get(code)
    custom = row.get("custom_fields")
    if not isinstance(custom, dict):
        return None
    return custom.get(code)


def _text(value: Any) -> str | None:
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    return value.strip() if isinstance(value, str) and value.strip() else None


def _ahj_key(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("id", value.get("value"))
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and value and value == value.strip():
        return value
    return None


def _address(value: Any) -> tuple[str | None, str | None]:
    address = _text(value)
    if value in (None, ""):
        return None, "missing_service_address"
    if address is None:
        return None, "invalid_service_address"
    # Pipedrive address objects may carry a unit separately from their full text.
    if isinstance(value, dict) and value.get("subpremise") not in (None, ""):
        unit = _text(value["subpremise"])
        if unit is None:
            return None, "invalid_address_unit"
        full_norm, unit_norm = normalize_address(address), normalize_address(unit)
        if not re.search(r"\bUNIT " + re.escape(unit_norm) + r"(?:\s|$)", full_norm):
            if re.search(r"\bUNIT\b", full_norm):
                return None, "conflicting_address_unit"
            address += ", Unit " + unit
    return address, None


def discover_deal_fields(token_file: Path | None = None) -> list[dict]:
    """Return field metadata plus enum/set option IDs/labels, never deal values."""
    return DealClient(read_token(token_file)).fields()


def import_deal_permits(token_file: Path | None, mapping: dict, deal_ids: list[int]) -> dict:
    """Return selected permit rows, issues and counts without writing any data."""
    ids = _deal_ids(deal_ids)
    _mapping_shape(mapping)
    client = DealClient(read_token(token_file), ids)
    custom = _validate_mapping(mapping, client.fields())
    params = {"custom_fields": ",".join(custom), "include_option_labels": "true"}
    permits, issues = [], []
    fetched = 0

    def issue(deal_id: int, code: str, source_field: str | None = None):
        item = {"deal_id": deal_id, "code": code}
        if source_field is not None:
            item["source_field"] = source_field
        issues.append(item)

    for deal_id in ids:
        try:
            payload = client.get(f"/api/v2/deals/{deal_id}", params)
        except PipedriveError:
            issue(deal_id, "deal_read_failed")
            continue
        row = payload.get("data")
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] != deal_id:
            issue(deal_id, "unexpected_deal_response")
            continue
        fetched += 1
        key = _ahj_key(_raw(row, mapping["ahj_field"]))
        if key is None or key not in mapping["ahj_map"]:
            issue(deal_id, "missing_or_unmapped_ahj", mapping["ahj_field"])
            continue
        address, address_issue = _address(_raw(row, mapping["address_field"]))
        if address_issue:
            issue(deal_id, address_issue, mapping["address_field"])
            if address_issue != "missing_service_address":
                continue
        customer = None
        if mapping["customer_name_field"]:
            raw_customer = _raw(row, mapping["customer_name_field"])
            customer = _text(raw_customer)
            if raw_customer not in (None, "") and customer is None:
                issue(deal_id, "invalid_customer_name", mapping["customer_name_field"])
        for code in mapping["permit_fields"]:
            value = _raw(row, code)
            permit_id = _text(value)
            if permit_id is None:
                issue(deal_id, "missing_permit_identifier" if value in (None, "") else "non_string_permit_identifier", code)
                continue
            permits.append({"deal_id": deal_id, "ahj_id": mapping["ahj_map"][key],
                            "permit_id": permit_id, "service_address": address,
                            "customer_name": customer, "source_field": code})
    return {"permits": permits, "issues": issues, "summary": {
        "requested_unique_deals": len(ids), "duplicate_input_ids_ignored": len(deal_ids) - len(ids),
        "deals_read": fetched, "deals_with_permits": len({r["deal_id"] for r in permits}),
        "permit_rows": len(permits), "issue_count": len(issues), "crm_writes": 0,
    }}
