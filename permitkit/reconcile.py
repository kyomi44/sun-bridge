"""Conservative, read-only matching of permit proposals to CRM records."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_permit_id(value: Any) -> str:
    """Keep punctuation, embedded whitespace, and leading zeros significant."""
    return _text(value).upper()


def normalize_address(value: Any) -> str:
    """Normalize presentation only, preserving the complete address and unit.

    This is not geocoding. No city, ZIP, unit, street number, or direction is
    dropped, and street-only addresses do not match longer complete addresses.
    Conservative equivalences cover common suffixes and explicit unit labels.
    """
    value = unicodedata.normalize("NFKC", _text(value)).upper()
    value = value.replace(",", " ")
    # Abbreviation dots are presentation; dots between digits may identify units.
    value = re.sub(r"(?<=[A-Z])\.(?=\s|$)", "", value)
    value = re.sub(r"#\s*", " UNIT ", value)
    aliases = {
        "STREET": "ST", "ROAD": "RD", "AVENUE": "AVE",
        "BOULEVARD": "BLVD", "DRIVE": "DR", "LANE": "LN",
        "COURT": "CT", "CIRCLE": "CIR", "TERRACE": "TER",
        "PLACE": "PL", "PARKWAY": "PKWY",
        "APARTMENT": "UNIT", "APT": "UNIT", "SUITE": "UNIT", "STE": "UNIT",
    }
    value = " ".join(aliases.get(token, token) for token in value.split())
    return value


def match_event(event: dict, permits: list[dict]) -> dict:
    """Propose one deal match; never write a status or collapse permit rows.

    Match AHJ plus permit ID first. If an event contains a permit ID, a missing
    or conflicting ID never falls back to address. Address matching is allowed
    only when the event has no permit ID, and requires one matching permit row.
    Customer names are not used. Duplicate rows remain ambiguous, including
    multiple permits attached to the same deal.
    """
    result = {"status": "unmatched", "deal_id": None, "method": None, "issues": []}

    def unmatched(issue: str) -> dict:
        result["issues"].append(issue)
        return result

    ahj_id = _text(event.get("ahj_id"))
    if not ahj_id:
        return unmatched("missing_ahj_id")
    rows = [p for p in permits if isinstance(p, dict) and _text(p.get("ahj_id")) == ahj_id]
    if not rows:
        return unmatched("no_records_for_ahj")
    if event.get("permit_id") is not None and not isinstance(event["permit_id"], str):
        return unmatched("invalid_permit_id_type")
    permit_id = normalize_permit_id(event.get("permit_id"))
    address = normalize_address(event.get("address"))
    if permit_id:
        method = "ahj_permit_id"
        matches = [p for p in rows if normalize_permit_id(p.get("permit_id")) == permit_id]
        if not matches:
            return unmatched("permit_id_not_found_no_address_fallback")
    else:
        method = "ahj_full_address"
        if not address:
            return unmatched("missing_reconciliation_identifiers")
        # A name, city alone, or ZIP alone is not a service address.
        if not re.match(r"\d+[A-Z]?(?:-\d+[A-Z]?)?\s+", address) or not re.search(r"[A-Z]", address):
            return unmatched("incomplete_service_address")
        matches = [p for p in rows if normalize_address(p.get("service_address")) == address]
        if not matches:
            return unmatched("address_not_found")
    result["method"] = method
    if len(matches) > 1:
        result["status"] = "ambiguous"
        result["issues"].append("multiple_matching_permit_records")
        return result
    record = matches[0]
    # An identifier match cannot silently override contradictory address evidence.
    record_address = normalize_address(record.get("service_address"))
    if permit_id and address and record_address and address != record_address:
        result["status"] = "ambiguous"
        result["issues"].append("permit_id_address_conflict")
        return result
    deal_id = record.get("deal_id")
    if isinstance(deal_id, bool) or not isinstance(deal_id, (str, int)) or not str(deal_id).strip():
        return unmatched("matched_record_missing_deal_id")
    result.update({"status": "matched", "deal_id": deal_id})
    return result
