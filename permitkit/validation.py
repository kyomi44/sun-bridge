"""Dependency-free validation for the subset used by the checked-in JSON schema.

The published schema also works with external Draft 2020-12 validators. This
module intentionally implements only the keywords used in that schema.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from .events import _sender_address


ROOT = Path(__file__).resolve().parent.parent


def validate_schema(value, schema: dict, path: str = "$", errors: list | None = None) -> list[str]:
    errors = [] if errors is None else errors
    kinds = schema.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    checks = {
        "null": value is None, "object": isinstance(value, dict),
        "array": isinstance(value, list), "string": isinstance(value, str),
        "integer": type(value) is int, "number": type(value) in (int, float),
        "boolean": type(value) is bool,
    }
    if kinds and not any(checks.get(kind, False) for kind in kinds):
        errors.append(f"{path}: expected {' or '.join(kinds)}")
        return errors
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside the documented choices")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: value cannot be blank")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: invalid format")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name}: required")
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                validate_schema(item, properties[name], f"{path}.{name}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{name}: unknown field")
    if isinstance(value, list):
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errors.append(f"{path}: duplicate items")
        for i, item in enumerate(value):
            if "items" in schema:
                validate_schema(item, schema["items"], f"{path}[{i}]", errors)
    return errors


def validate_profile(profile: dict) -> list[str]:
    schema = json.loads((ROOT / "schemas/ahj-profile.schema.json").read_text())
    errors = validate_schema(profile, schema)
    if errors:
        return errors
    verification = profile["verification"]
    if verification["status"] == "documented" and (not profile["sources"] or not verification["last_checked"]):
        errors.append("Documented profiles require official sources and last_checked.")
    for value in [verification["last_checked"], *(s["checked_on"] for s in profile["sources"])]:
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append("Dates must use YYYY-MM-DD.")
    for link in [profile["capabilities"]["portal_url"], *(s["url"] for s in profile["sources"])]:
        if link:
            try:
                parts = urlsplit(link)
                valid = parts.scheme == "https" and parts.hostname and not parts.username and not parts.password
            except ValueError:
                valid = False
            if not valid:
                errors.append("Sources and portal links must be HTTPS URLs without credentials.")
    parser = profile["parser"]
    if parser["status"] == "not_implemented" and parser["subject_rules"]:
        errors.append("Disabled parsers must not contain enabled rules.")
    if parser["status"] == "experimental" and (not parser["subject_rules"] or not parser["sender_allowlist"]):
        errors.append("Experimental parsers require rules and sender addresses.")
    if any(not _sender_address(sender) for sender in parser["sender_allowlist"]):
        errors.append("Sender allowlist entries must each contain one valid mailbox address.")
    ids = set()
    for rule in parser["subject_rules"]:
        rule_id = rule["id"].strip()
        if not rule_id:
            errors.append("Rule IDs cannot be blank.")
        if rule_id in ids:
            errors.append("Rule IDs must be unique after trimming whitespace within a profile.")
        ids.add(rule_id)
        try:
            pattern = re.compile(rule["pattern"])
            if not ({"permit_id", "address"} & pattern.groupindex.keys()):
                errors.append(f"Rule {rule['id']} must extract permit_id or address.")
        except re.error:
            errors.append(f"Rule {rule['id']} has an invalid regular expression.")
    return errors


def load_profiles(path: Path) -> dict[str, dict]:
    files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    if not files:
        raise ValueError("No AHJ profiles found.")
    result = {}
    for file in files:
        profile = json.loads(file.read_text(encoding="utf-8"))
        errors = validate_profile(profile)
        if errors:
            raise ValueError(f"Invalid profile {file.name}: {'; '.join(errors)}")
        if profile["id"] in result:
            raise ValueError(f"Duplicate AHJ profile ID: {profile['id']}")
        result[profile["id"]] = profile
    return result
