"""Propose links between public coverage registry entries and catalog AHJs.

Proposals only. This module never edits the public registry, the catalog, a
profile, or a CRM. One candidate is a review shortcut, not a verified identity:
a registry name is a provisional display group and a catalog entity is a source
row, so confirm the jurisdiction before recording any link between them.
"""
from __future__ import annotations

import re

from .catalog import _database, _entities, _norm, _source
from .coverage import INVALID, validate_registry

COUNTY_FORMS = frozenset({"county", "parish"})
LEGAL_FORMS = frozenset({
    "city", "town", "village", "township", "borough", "municipality", "cdp", "municipio",
}) | COUNTY_FORMS
_PREFIX = re.compile(r"(?i)^(city|town|village|county|borough|township) of (.+)$")
_STATE_SUFFIX = re.compile(r"^(.+?),\s*([A-Z]{2})$")
_PARENTHETICAL = re.compile(r"\s*\([^()]*\)\s*$")
WARNING = (
    "Candidate links only. Registry names are provisional display groups and catalog "
    "entities are source rows; confirm the jurisdiction identity before recording a link. "
    "Nothing was written to the registry, the catalog, a profile, or a CRM."
)


def registry_search_terms(name: str) -> tuple[str, str | None, str | None]:
    """Split a registry display name into (search name, state hint, legal form).

    Only two explicit conventions are read: a trailing ", XX" state code and a
    leading "Village of" / "City of" / "Town of" / "County of" style prefix.
    Nothing else is inferred from the name.
    """
    text = " ".join(name.split())
    state = None
    match = _STATE_SUFFIX.fullmatch(text)
    if match:
        text, state = match.group(1).strip(), match.group(2)
    legal_form = None
    match = _PREFIX.fullmatch(text)
    if match:
        legal_form, text = match.group(1).casefold(), match.group(2).strip()
    return text, state, legal_form


def _catalog_forms(name: str) -> tuple[str, str | None, str | None]:
    """Return (exact form, place form, legal form) for one catalog entity name.

    The source writes Census-style names such as "Cape Coral city" or
    "Lee township (Midland County)". The place form drops one trailing legal
    form after any trailing parenthetical; the exact form only normalizes case
    and whitespace, matching the catalog's own reconciliation rule.
    """
    core = _PARENTHETICAL.sub("", " ".join(name.split()))
    tokens = core.split()
    if len(tokens) > 1 and tokens[-1].casefold() in LEGAL_FORMS:
        return _norm(name), _norm(" ".join(tokens[:-1])), tokens[-1].casefold()
    return _norm(name), None, None


def _state_filter(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2}", value.strip()):
        raise ValueError("Use a two-letter source state code for the coverage state filter.")
    return value.strip().upper()


def _candidate(entity: dict, method: str, legal_form: str | None) -> dict:
    return {"entity_id": entity["entity_id"], "name": entity["name"], "states": list(entity["states"]),
            "identity_status": entity["identity_status"], "legal_form": legal_form, "match_method": method}


def _in_state(candidate: dict, state: str) -> bool:
    return _norm(state) in {_norm(value) for value in candidate["states"]}


def propose_registry_links(registry: dict, entities: list[dict], *, state: str | None = None) -> dict:
    """Propose catalog building departments for each registry entry; no writes.

    A registry state suffix always wins over the optional ``state`` default.
    Utilities are never candidates. Candidates outside the state hint are kept
    separately so a reviewer can see why an entry stayed unmatched. Each
    candidate names its match method: ``exact_name`` (case and whitespace only),
    ``place_name`` (one trailing municipal form dropped from the catalog name),
    or ``county_name`` (a trailing County/Parish dropped, so a bare place name
    can also surface the county that shares it; the reviewer decides).
    """
    if validate_registry(registry):
        raise ValueError(INVALID)
    default_state = _state_filter(state)
    exact_index: dict[str, list] = {}
    place_index: dict[str, list] = {}
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("kind") != "building_department":
            continue
        exact, place, legal_form = _catalog_forms(entity["name"])
        exact_index.setdefault(exact, []).append((entity, legal_form))
        if place is not None:
            method = "county_name" if legal_form in COUNTY_FORMS else "place_name"
            place_index.setdefault(place, []).append((entity, legal_form, method))
    items = []
    for entry in sorted(registry["entries"], key=lambda item: (item["name"].casefold(), item["id"])):
        search_name, entry_state, registry_form = registry_search_terms(entry["name"])
        if entry_state:
            state_hint, hint_source = entry_state, "registry_name"
        elif default_state:
            state_hint, hint_source = default_state, "state_option"
        else:
            state_hint, hint_source = None, None
        needle = _norm(search_name)
        found: dict[str, dict] = {}
        for entity, legal_form in exact_index.get(needle, []):
            found[entity["entity_id"]] = _candidate(entity, "exact_name", legal_form)
        for entity, legal_form, method in place_index.get(needle, []):
            found.setdefault(entity["entity_id"], _candidate(entity, method, legal_form))
        candidates = sorted(found.values(), key=lambda candidate: candidate["entity_id"])
        issues = []
        if state_hint is None:
            issues.append("state_not_specified_all_states_searched")
            in_state, elsewhere = candidates, []
        else:
            in_state = [candidate for candidate in candidates if _in_state(candidate, state_hint)]
            elsewhere = [candidate for candidate in candidates if not _in_state(candidate, state_hint)]
        if not in_state:
            status = "unmatched"
            issues.append("candidates_only_in_other_states" if elsewhere else "no_catalog_candidate")
        elif len(in_state) == 1:
            status = "single_candidate"
        else:
            status = "ambiguous"
        if any(candidate["identity_status"] != "source_id" for candidate in in_state):
            issues.append("candidate_identity_unresolved_in_source")
        if registry_form and any(candidate["legal_form"] not in (None, registry_form) for candidate in in_state):
            issues.append("registry_legal_form_differs_from_catalog")
        if entry["identity_note"] != "none":
            issues.append("registry_identity_note_" + entry["identity_note"])
        items.append({
            "id": entry["id"], "name": entry["name"], "search_name": search_name,
            "registry_legal_form": registry_form,
            "state_hint": state_hint, "state_hint_source": hint_source,
            "status": status, "candidates": in_state, "other_state_candidates": elsewhere,
            "identity_note": entry["identity_note"], "pilot_events": list(entry["pilot_events"]),
            "review_required": True, "issues": issues,
        })
    summary = {status: sum(item["status"] == status for item in items)
               for status in ("single_candidate", "ambiguous", "unmatched")}
    return {"mode": "review_only", "crm_writes": 0, "registry_writes": 0, "catalog_writes": 0,
            "state_filter": default_state, "evidence_reviewed_on": registry["evidence_reviewed_on"],
            "items": items, "summary": summary, "warning": WARNING}


def reconcile_coverage(db_path, registry: dict, *, state: str | None = None) -> dict:
    """Read the active catalog source and propose registry links; read-only."""
    if validate_registry(registry):
        raise ValueError(INVALID)
    state = _state_filter(state)
    with _database(db_path) as (connection, active):
        entities = _entities(connection, active)
        source = _source(connection, active)
    report = propose_registry_links(registry, entities, state=state)
    report["source"] = source
    return report
