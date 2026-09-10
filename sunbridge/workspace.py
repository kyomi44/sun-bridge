"""Guided private setup, offline readiness checks, and a bounded review run."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from urllib.parse import urlsplit

from .privateio import private_path, preflight_private_targets, read_json_file, write_private, write_private_json
from .validation import ROOT, load_profiles
from .workflow import review_messages, write_report


def source_path(value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Input paths must be nonempty strings.")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def validate_workspace(config: dict) -> dict:
    keys = {"schema_version", "messages_path", "profiles_path", "crm", "llm_config_path", "output_dir", "max_messages"}
    if not isinstance(config, dict) or set(config) != keys or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise ValueError("Use the generated workspace configuration; unknown or missing settings are not accepted.")
    for key in ("messages_path", "profiles_path", "output_dir"):
        source_path(config[key])
    private_path(config["output_dir"])
    if type(config["max_messages"]) is not int or not 1 <= config["max_messages"] <= 100:
        raise ValueError("Set max_messages between 1 and 100 for a bounded review run.")
    if config["llm_config_path"] is not None:
        source_path(config["llm_config_path"])
    crm = config["crm"]
    if not isinstance(crm, dict):
        raise ValueError("CRM settings must be an object.")
    if crm.get("adapter") == "json_file":
        if set(crm) != {"adapter", "permits_path"}:
            raise ValueError("JSON CRM settings require only adapter and permits_path.")
        source_path(crm["permits_path"])
    elif crm.get("adapter") == "pipedrive":
        if set(crm) != {"adapter", "mapping_path", "deal_ids", "token_file"}:
            raise ValueError("Pipedrive settings require adapter, mapping_path, deal_ids, and token_file.")
        source_path(crm["mapping_path"])
        ids = crm["deal_ids"]
        if not isinstance(ids, list) or len(ids) > 100 or any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Supply up to 100 distinct positive integer Pipedrive deal IDs.")
        if crm["token_file"] is not None:
            source_path(crm["token_file"])
    else:
        raise ValueError("Only json_file and pipedrive CRM adapters are implemented. See integrations.")
    return config


def create_workspace(directory: Path, crm_mode: str = "demo") -> Path:
    directory = private_path(directory)
    if crm_mode not in {"demo", "json_file", "pipedrive"}:
        raise ValueError("Choose demo, json_file, or pipedrive setup.")
    # Refuse to partially replace a previous setup.
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Setup directory is not empty. Keep your existing setup or choose a new directory.")
    rel = directory.relative_to(ROOT).as_posix()
    config = {
        "schema_version": 1,
        "messages_path": "examples/messages.json" if crm_mode == "demo" else "private/mail/messages.json",
        "profiles_path": "profiles",
        "crm": {"adapter": "json_file", "permits_path": "examples/permits.json" if crm_mode == "demo" else "private/permits/permits.json"},
        "llm_config_path": None,
        "output_dir": f"{rel}/review",
        "max_messages": 100,
    }
    if crm_mode == "pipedrive":
        config["crm"] = {"adapter": "pipedrive", "mapping_path": f"{rel}/pipedrive-mapping.json", "deal_ids": [], "token_file": None}
        write_private_json(directory / "pipedrive-mapping.json", read_json_file(ROOT / "templates/pipedrive-deal-mapping.json"))
    write_private_json(directory / "llm-config.json", read_json_file(ROOT / "templates/llm-config.json"))
    path = write_private_json(directory / "sunbridge.json", config)
    command_config = shlex.quote(f"{rel}/sunbridge.json")
    instructions = "\n".join([
        "# Your private Sun Bridge workspace", "",
        "No accounts were connected and no messages were sent during setup.", "",
        "1. Run the offline check:", f"   python3 -m sunbridge doctor --config {command_config}", "",
        "2. For real work, import a small local email export and prepare the CRM mapping.",
        "   See docs/getting-started.md and docs/pipedrive-deals.md in the repository.", "",
        "3. Run a review after the checks pass:", f"   python3 -m sunbridge run --config {command_config}", "",
        "4. Open review/review.html in your browser. Nothing is written to your CRM.", "",
        "LLM extraction is OFF. The llm-config.json file is a template, not an active connection.",
        "Choose a compatible endpoint and model, supply its key through the configured environment variable,",
        "and read docs/llm-providers.md before enabling it. Never put a literal token in configuration.",
        "An explicit --allow-llm-data-transfer flag is required for every LLM-enabled run.", "",
        "Keep this entire directory private. Do not attach it to a public issue or include it in a fork.", "",
    ])
    write_private(directory / "START-HERE.md", instructions)
    return path


def _messages(config: dict) -> list[dict]:
    messages = read_json_file(source_path(config["messages_path"]))
    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
        raise ValueError("Messages must be a JSON array of objects; use import-mail for EML or MBOX.")
    if not messages or len(messages) > config["max_messages"]:
        raise ValueError("Provide 1 to max_messages inputs; split larger exports into smaller batches.")
    for message in messages:
        if any(key in message and not isinstance(message[key], str) for key in ("message_id", "ahj_id", "sender", "subject", "body", "received_at")):
            raise ValueError("Message identifiers, headers, body, and timestamps must be strings.")
    return messages


def _permits(path: Path) -> list[dict]:
    records = read_json_file(path)
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("Permit input must be a JSON array of at most 10000 records.")
    for record in records:
        if not isinstance(record, dict) or type(record.get("deal_id")) not in (int, str) or not str(record["deal_id"]).strip():
            raise ValueError("Every permit record needs a nonempty deal_id.")
        if not isinstance(record.get("ahj_id"), str) or not record["ahj_id"].strip():
            raise ValueError("Every permit record needs an explicit AHJ profile ID.")
        for key in ("permit_id", "service_address", "customer_name"):
            if record.get(key) is not None and not isinstance(record[key], str):
                raise ValueError("Permit numbers, service addresses, and names must be strings.")
    return records


def ready_pipedrive_mapping(value: dict, profiles: dict) -> dict:
    """Reject unfinished setup locally, before field discovery or deal reads.

    The public mapping validator also serves template editing and therefore
    accepts placeholders. A live-run preflight requires real code syntax and
    at least one explicit mapping to a loaded profile. Metadata types and the
    actual existence of field codes remain checks for the read-only adapter.
    """
    from .crm import validate_mapping
    mapping = validate_mapping(value)
    if not mapping["ahj_map"]:
        raise ValueError("Add at least one explicit CRM AHJ value mapped to a loaded profile before a live read.")
    if any(profile not in profiles for profile in mapping["ahj_map"].values()):
        raise ValueError("Every AHJ mapping must reference a configured profile.")
    selections = [("ahj", mapping["ahj_field"]), ("address", mapping["address_field"])]
    selections += [("permit", code) for code in mapping["permit_fields"]]
    if mapping["customer_name_field"] is not None:
        selections.append(("customer", mapping["customer_name_field"]))
    custom_codes = set()
    for role, code in selections:
        if (role == "ahj" and code == "org_id") or (role == "customer" and code == "title"):
            continue
        if not re.fullmatch(r"[a-f0-9]{40}", code):
            raise ValueError("Replace field-code placeholders with exact codes from pipedrive-fields; only AHJ org_id and optional customer title are supported standard fields.")
        custom_codes.add(code)
    if len(custom_codes) > 15:
        raise ValueError("Select no more than 15 unique custom fields across the Pipedrive mapping.")
    if mapping["ahj_field"] == "org_id" and any(not re.fullmatch(r"[1-9][0-9]*", key) for key in mapping["ahj_map"]):
        raise ValueError("For org_id, replace fictional mapping keys with the actual positive organization IDs as strings.")
    return mapping


def preflight_workspace(config_path: Path, config: dict) -> Path:
    crm = config["crm"]
    sources = [config_path, source_path(config["messages_path"]), source_path(config["profiles_path"])]
    names = ["review.json", "review.md", "review.html"]
    if config["llm_config_path"]:
        sources.append(source_path(config["llm_config_path"]))
    if crm["adapter"] == "json_file":
        sources.append(source_path(crm["permits_path"]))
    else:
        names.append("permits.json")
        sources.append(source_path(crm["mapping_path"]))
        if crm["token_file"]:
            sources.append(source_path(crm["token_file"]))
    return preflight_private_targets(private_path(config["output_dir"]), names, sources=sources, overwrite=True)


def doctor(config_path: Path) -> dict:
    config = validate_workspace(read_json_file(config_path, max_bytes=128000))
    checks = []
    guidance = {
        "private outputs": "Choose an output_dir below this clone's private directory, separate from inputs/configuration and without symlink aliases or directory-shaped report files.",
        "profiles": "Validate profiles_path with the validate command and fix missing or invalid profiles.",
        "messages": "Import 1 to max_messages local emails, set messages_path to the JSON array, and assign each message a loaded AHJ profile ID.",
        "permit records": "Set permits_path to a nonempty normalized JSON array; each record needs a deal ID and a loaded AHJ profile ID, with permit identifiers stored as strings.",
        "Pipedrive mapping and deal selection": "Replace field-code placeholders using pipedrive-fields, add an explicit AHJ map to loaded profiles, and select 1 to 100 distinct positive deal IDs. For org_id, map real organization IDs as string keys.",
        "Pipedrive credential": "Set PIPEDRIVE_API_TOKEN or point token_file to a nonempty regular token file outside the repository; do not place a literal credential in configuration.",
        "LLM configuration": "Check the LLM configuration against templates/llm-config.json and docs/llm-providers.md; use an allowed endpoint and an environment-variable credential reference.",
    }
    def check(name, operation):
        try:
            message = operation()
            checks.append({"name": name, "status": "ready", "message": message})
        except (OSError, ValueError, RuntimeError):
            # Do not echo arbitrary exception text, which could include private paths or values.
            checks.append({"name": name, "status": "needs_attention", "message": guidance.get(name, "Check this setting using the setup guide.") + " No network requests were made."})
    def check_output():
        preflight_workspace(config_path, config)
        return "Private report targets do not overlap inputs or configuration."
    check("private outputs", check_output)
    profiles = {}
    def check_profiles():
        profiles.update(load_profiles(source_path(config["profiles_path"])))
        return f"{len(profiles)} profiles pass structural checks, not production certification."
    check("profiles", check_profiles)
    def check_messages():
        messages = _messages(config)
        if any(m.get("ahj_id") not in profiles for m in messages):
            raise ValueError("Map each message to a configured profile.")
        return f"{len(messages)} messages are within the batch limit."
    check("messages", check_messages)
    crm = config["crm"]
    if crm["adapter"] == "json_file":
        def check_records():
            records = _permits(source_path(crm["permits_path"]))
            if not records or any(r["ahj_id"] not in profiles for r in records):
                raise ValueError("Permit records need loaded profiles.")
            return f"{len(records)} private or synthetic permit records; no CRM connection."
        check("permit records", check_records)
    else:
        def check_mapping():
            ready_pipedrive_mapping(read_json_file(source_path(crm["mapping_path"]), max_bytes=128000), profiles)
            if not crm["deal_ids"]:
                raise ValueError("Select deal IDs.")
            return f"{len(crm['deal_ids'])} explicitly selected deals. Actual field codes and connectivity are checked on the live read."
        check("Pipedrive mapping and deal selection", check_mapping)
        def check_credential():
            if crm["token_file"]:
                path = source_path(crm["token_file"])
                present = path.is_file() and not path.is_symlink() and path.stat().st_size > 0
            else:
                present = bool(os.environ.get("PIPEDRIVE_API_TOKEN", "").strip())
            if not present:
                raise ValueError("Supply a private token file or environment variable.")
            return "Credential reference exists. Validity and permissions have NOT been tested."
        check("Pipedrive credential", check_credential)
    llm_target = None
    if config["llm_config_path"]:
        def check_llm():
            nonlocal llm_target
            from .llm import validate_config
            llm = validate_config(read_json_file(source_path(config["llm_config_path"]), max_bytes=128000))
            parts = urlsplit(llm["base_url"])
            llm_target = f"{parts.scheme}://{parts.netloc}{parts.path}"
            return "Configured experimental extraction. Every run still requires explicit data-transfer consent."
        check("LLM configuration", check_llm)
    else:
        checks.append({"name": "LLM", "status": "ready", "message": "Disabled. No message content is sent to an LLM."})
    return {"ready": all(c["status"] == "ready" for c in checks), "network_requests": 0,
            "crm_writes": 0, "checks": checks, "llm_target": llm_target,
            "note": "Readiness is configuration validation, not verified accuracy or live connectivity."}


def llm_parser(config_path: Path, allow_data_transfer: bool):
    from .llm import LLMClient, LLMError, _base_event, validate_config
    if allow_data_transfer is not True:
        raise ValueError("LLM use is disabled without --allow-llm-data-transfer. Read the provider and privacy guide first.")
    config = validate_config(read_json_file(config_path, max_bytes=128000))
    client = LLMClient(config, allow_data_transfer=True)
    def extract(message, profile):
        try:
            return client.extract(message, profile)
        except LLMError as error:
            event = _base_event(message, profile, config)
            event["issues"].extend([error.code, "llm_request_failed_no_fallback"])
            return event
    return extract


def run_workspace(config_path: Path, *, allow_data_transfer: bool = False) -> dict:
    config = validate_workspace(read_json_file(config_path, max_bytes=128000))
    readiness = doctor(config_path)
    if not readiness["ready"]:
        raise ValueError("Setup needs attention. Run doctor and follow docs/getting-started.md before a live read.")
    output = preflight_workspace(config_path, config)
    parser = None
    if config["llm_config_path"]:
        parser = llm_parser(source_path(config["llm_config_path"]), allow_data_transfer)
    messages = _messages(config)
    profiles = load_profiles(source_path(config["profiles_path"]))
    crm = config["crm"]
    imported = None
    if crm["adapter"] == "json_file":
        permits = _permits(source_path(crm["permits_path"]))
    else:
        from .crm import import_deal_permits
        token_file = source_path(crm["token_file"]) if crm["token_file"] else None
        mapping = ready_pipedrive_mapping(read_json_file(source_path(crm["mapping_path"]), max_bytes=128000), profiles)
        imported = import_deal_permits(token_file, mapping, crm["deal_ids"])
        permits = imported["permits"]
    report = review_messages(messages, permits, profiles, event_parser=parser)
    if imported is not None:
        report["crm_import"] = {"summary": imported["summary"], "issues": imported["issues"]}
    if imported is not None:
        write_private_json(output / "permits.json", permits, overwrite=True)
    write_report(report, output)
    return {"summary": report["summary"], "report_path": str(output / "review.html"), "crm_writes": 0,
            "llm_enabled": parser is not None, "crm_import_issues": len(imported["issues"]) if imported else 0}
