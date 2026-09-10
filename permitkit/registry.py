"""Public integration capabilities, not a dynamic plugin execution mechanism."""
from __future__ import annotations

import json
import re
from .validation import ROOT


def integration_registry() -> dict:
    registry = json.loads((ROOT / "integrations/crms.json").read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or set(registry) != {"schema_version", "crms"}:
        raise ValueError("Invalid CRM integration registry.")
    entries = registry["crms"]
    if type(registry["schema_version"]) is not int or registry["schema_version"] != 1 or not isinstance(entries, list) or not entries:
        raise ValueError("Invalid CRM integration registry.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_]*", entry["id"]) or entry["id"] in seen:
            raise ValueError("CRM registry IDs must be unique strings.")
        seen.add(entry["id"])
        if entry.get("status") not in {"available", "experimental", "planned"}:
            raise ValueError("Invalid CRM support status.")
        if entry.get("crm_writes") is not False:
            raise ValueError("This release must not advertise CRM writes.")
        if any(not isinstance(entry.get(key), str) or not entry[key].strip() for key in ("name", "scope", "authentication", "verification")):
            raise ValueError("Integration claims need a name, scope, authentication, and verification description.")
        if any(type(entry.get(key)) is not bool for key in ("organization_discovery", "permit_reads")):
            raise ValueError("Integration capabilities must be explicit booleans.")
        for key in ("implementation", "tests"):
            if not isinstance(entry.get(key), list) or any(not isinstance(name, str) or not name for name in entry[key]):
                raise ValueError("Integration source and test references must be lists of paths.")
        if entry["status"] != "planned":
            if not entry["implementation"] or not entry["tests"]:
                raise ValueError("An implemented integration must identify source and tests.")
            for name in entry["implementation"] + entry["tests"]:
                path = (ROOT / name).resolve()
                if name.startswith("/") or ".." in name.split("/") or not path.is_relative_to(ROOT) or not path.is_file() or (ROOT / name).is_symlink():
                    raise ValueError("An implemented integration must have source and tests.")
        elif entry["organization_discovery"] or entry["permit_reads"]:
            raise ValueError("A planned adapter cannot advertise implemented read capabilities.")
    return registry


def render_integrations() -> str:
    lines = ["Sun Bridge CRM integrations", "", "All integrations are read-only. Support is capability-specific.", ""]
    for crm in integration_registry()["crms"]:
        lines.append(f"{crm['name']} — {crm['status']}")
        lines.append(f"  {crm['scope']}")
        lines.append(f"  Verification: {crm['verification']}")
    return "\n".join(lines)
