"""Sun Bridge command interface for scoped imports and permit review."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import webbrowser
from pathlib import Path

from .privateio import private_path, preflight_private_targets, read_json_file, write_private, write_private_json
from .validation import ROOT, load_profiles, validate_profile
from .workflow import review_messages, write_report


def private_output(value: str) -> Path:
    return private_path(value)


def read_json(path: Path):
    return read_json_file(path)


def _display_result(result: dict, open_browser: bool = False) -> None:
    print(json.dumps(result, indent=2))
    print("Proposals only. Check original evidence before making a decision. CRM writes: 0.")
    if open_browser and result.get("report_path"):
        webbrowser.open(Path(result["report_path"]).as_uri())


def _deal_ids(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("Use comma-separated positive deal IDs, for example 101,102.") from None
    if not values or len(values) > 100 or any(v < 1 for v in values) or len(set(values)) != len(values):
        raise argparse.ArgumentTypeError("Choose 1 to 100 distinct positive deal IDs.")
    return values


def _search_table(rows: list[dict], limit: int) -> str:
    """Render search hits as aligned text for people; JSON remains the default."""
    if not rows:
        return "No catalog entities matched. Broaden the query or remove a filter."
    headers = ("entity_id", "kind", "states", "identity", "name")
    table = [(row["entity_id"], row["kind"], ",".join(row["states"]), row["identity_status"], row["name"]) for row in rows]
    widths = [max(len(header), *(len(cells[i]) for cells in table)) for i, header in enumerate(headers)]
    lines = [" ".join(header.ljust(width) for header, width in zip(headers, widths)).rstrip(),
             " ".join("-" * width for width in widths)]
    lines += [" ".join(cell.ljust(width) for cell, width in zip(cells, widths)).rstrip() for cells in table]
    lines.append("")
    lines.append(f"{len(rows)} results. Inspect one with: python3 -m sunbridge catalog show --id ENTITY_ID")
    if len(rows) >= limit:
        lines.append(f"Results are capped at --limit {limit}; narrow the query or raise the limit (up to 1000).")
    lines.append("Historical source data, not current status. Identity 'unresolved' means the source row had no ID.")
    return "\n".join(lines)


def _catalog_command(args) -> int:
    from .catalog import attach_review, export_catalog, init_catalog, reconcile_organizations, search_catalog, show_entity
    from .solartrace import load_bundle, normalize_snapshot, read_workbook

    db = private_output(args.db)
    action = args.catalog_command
    if action in {"init", "import-workbook"}:
        source_input = args.input if action == "import-workbook" else None
        preflight_private_targets(db.parent, [db.name], sources=[source_input], overwrite=True)
        bundle = read_workbook(source_input) if source_input else load_bundle()
        snapshot = normalize_snapshot(bundle)
        result = init_catalog(db, snapshot)
        result["source_statistics"] = snapshot["stats"]
        result["note"] = "Local catalog ready. Historical data, not current status. CRM writes: 0."
    elif action == "search":
        result = search_catalog(db, query=args.query, state=args.state, kind=args.kind, limit=args.limit)
        if args.format == "table":
            print(_search_table(result, args.limit))
            return 0
    elif action == "show":
        result = show_entity(db, args.id)
    elif action == "export":
        names = ["organizations.json", "benchmarks.json", "requirements.json", "source.json", "NOTICE.txt"]
        output = preflight_private_targets(private_output(args.output), names, sources=[db])
        data = export_catalog(db, state=args.state)
        notice = data["source"].get("license_notice")
        if not isinstance(notice, str) or not notice.strip():
            raise ValueError("Source attribution is missing; restore the reviewed source notice before export.")
        for key in ("organizations", "benchmarks", "requirements", "source"):
            write_private_json(output / (key + ".json"), data[key])
        write_private(output / "NOTICE.txt", notice)
        result = {"output": str(output), "counts": {key: len(data[key]) for key in ("organizations", "benchmarks", "requirements")},
                  "crm_writes": 0, "note": "Keep NOTICE.txt and source.json with redistributed data. No private event evidence exported."}
    elif action == "reconcile":
        output = preflight_private_targets(private_output(args.output), ["review.json"], sources=[db, args.organizations])
        report = reconcile_organizations(db, read_json(args.organizations))
        write_private_json(output / "review.json", report)
        result = {"summary": report["summary"], "report_path": str(output / "review.json"), "crm_writes": 0,
                  "note": "Candidate links only. Review jurisdiction and identifiers before any CRM import."}
    elif action == "reconcile-coverage":
        from .coverage import load_registry
        from .crosswalk import reconcile_coverage
        output = preflight_private_targets(private_output(args.output), ["review.json"], sources=[db, args.registry])
        report = reconcile_coverage(db, load_registry(args.registry), state=args.state)
        write_private_json(output / "review.json", report)
        result = {"summary": report["summary"], "report_path": str(output / "review.json"), "crm_writes": 0, "registry_writes": 0,
                  "note": "Candidate links only. The public registry and the catalog were not changed; confirm jurisdiction identity before recording a link."}
    else:
        preflight_private_targets(db.parent, [db.name], sources=[args.report, args.links], overwrite=True)
        result = attach_review(db, read_json(args.report), read_json(args.links))
        result["note"] = "Proposed evidence saved privately. No benchmark, current status, or CRM record was changed."
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sun Bridge: AHJ and utility data, historical timelines, and permit evidence review. No CRM writes.")
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="Initialize, search, and reconcile a local AHJ and utility catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    for name, help_text in (
        ("init", "Load the bundled public source without network or accounts"),
        ("import-workbook", "Privately import a compatible reviewed workbook snapshot"),
        ("search", "Find source AHJs and utilities"),
        ("show", "Inspect one entity, source benchmarks, requirements, and proposed evidence"),
        ("export", "Export source-derived data and required attribution; never private event evidence"),
        ("reconcile", "Propose organization links for human review; no CRM writes"),
        ("reconcile-coverage", "Propose catalog entities for public email coverage entries; review only, no writes"),
        ("attach-review", "Retain review proposals through an explicit profile-to-catalog crosswalk"),
    ):
        command = catalog_sub.add_parser(name, help=help_text)
        command.add_argument("--db", default=str(ROOT / "private/catalog/sunbridge.sqlite"))
        if name in {"search", "export"}:
            command.add_argument("--state")
        if name == "search":
            command.add_argument("--kind", choices=["building_department", "utility_company"])
            command.add_argument("--query", default="")
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--format", choices=["json", "table"], default="json", help="table prints aligned columns for people; json is the default")
        elif name == "reconcile-coverage":
            command.add_argument("--registry", type=Path, default=ROOT / "coverage/ahj-email-signals.json")
            command.add_argument("--state", help="Default state for entries whose registry name carries no ', XX' suffix")
            command.add_argument("--output", default=str(ROOT / "private/coverage-reconciliation"))
        elif name == "show":
            command.add_argument("--id", required=True)
        elif name == "import-workbook":
            command.add_argument("--input", type=Path, required=True)
        elif name == "export":
            command.add_argument("--output", default=str(ROOT / "private/catalog-export"))
        elif name == "reconcile":
            command.add_argument("--organizations", type=Path, required=True)
            command.add_argument("--output", default=str(ROOT / "private/catalog-reconciliation"))
        elif name == "attach-review":
            command.add_argument("--report", type=Path, required=True)
            command.add_argument("--links", type=Path, required=True)
    for name in ("start", "demo"):
        command = sub.add_parser(name, help="Run the fictional training exercise; no accounts or API keys")
        command.add_argument("--output", default=str(ROOT / "private/demo"))
        command.add_argument("--open", action="store_true", help="Open the local HTML report in your browser")
    setup = sub.add_parser("setup", help="Generate a private workspace and step-by-step instructions; no network")
    setup.add_argument("--crm", choices=["demo", "json_file", "pipedrive"], default="demo")
    setup.add_argument("--output", default=str(ROOT / "private/workspace"))
    setup.add_argument("--interactive", action="store_true", help="Ask which supported setup you want")
    for name in ("doctor", "run"):
        command = sub.add_parser(name, help="Check configuration offline" if name == "doctor" else "Review your configured inputs; CRM is read-only")
        command.add_argument("--config", type=Path, default=ROOT / "private/workspace/sunbridge.json")
        if name == "run":
            command.add_argument("--allow-llm-data-transfer", action="store_true")
            command.add_argument("--open", action="store_true")
    registry = sub.add_parser("integrations", help="Show implemented, experimental, and planned CRM capabilities")
    registry.add_argument("--json", action="store_true")
    analyze = sub.add_parser("analyze", help="Review local JSON messages and normalized permit records")
    analyze.add_argument("--messages", type=Path, required=True)
    analyze.add_argument("--permits", type=Path, required=True)
    analyze.add_argument("--profiles", type=Path, default=ROOT / "profiles")
    analyze.add_argument("--output", default=str(ROOT / "private/my-review"))
    analyze.add_argument("--llm-config", type=Path)
    analyze.add_argument("--allow-llm-data-transfer", action="store_true")
    analyze.add_argument("--open", action="store_true")
    check = sub.add_parser("llm-check", help="Send only a fictional connection test to your configured provider")
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--allow-llm-data-transfer", action="store_true")
    mail = sub.add_parser("import-mail", help="Convert a local EML, EML folder, or MBOX assigned to one AHJ")
    mail.add_argument("--input", type=Path, required=True)
    mail.add_argument("--ahj", required=True, help="Operator-verified profile ID, not a guessed postal city")
    mail.add_argument("--profiles", type=Path, default=ROOT / "profiles")
    mail.add_argument("--limit", type=int, default=100)
    mail.add_argument("--output", default=str(ROOT / "private/mail"))
    validate = sub.add_parser("validate", help="Validate profiles, integration registry, and demo outcomes")
    validate.add_argument("--profiles", type=Path, default=ROOT / "profiles")
    imp = sub.add_parser("pipedrive-import", help="Read organization fields and Building Departments into private/")
    imp.add_argument("--token-file", type=Path)
    imp.add_argument("--output", default=str(ROOT / "private/pipedrive"))
    imp.add_argument("--type-field")
    imp.add_argument("--type-label", default="Building Department")
    fields = sub.add_parser("pipedrive-fields", help="Read deal field metadata for an explicit mapping")
    fields.add_argument("--token-file", type=Path)
    fields.add_argument("--output", default=str(ROOT / "private/deal-fields"))
    deals = sub.add_parser("pipedrive-deals", help="Read only selected deals and normalize their mapped permit fields")
    deals.add_argument("--mapping", type=Path, required=True)
    deals.add_argument("--deal-ids", type=_deal_ids, required=True)
    deals.add_argument("--token-file", type=Path)
    deals.add_argument("--profiles", type=Path, default=ROOT / "profiles")
    deals.add_argument("--output", default=str(ROOT / "private/permits"))
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            return _catalog_command(args)
        if args.command == "integrations":
            from .registry import integration_registry, render_integrations
            print(json.dumps(integration_registry(), indent=2) if args.json else render_integrations())
            return 0
        if args.command == "setup":
            from .workspace import create_workspace
            mode = args.crm
            if args.interactive:
                print("Choose a setup. No data is sent and no credentials are stored.")
                print("1. Fictional demo (recommended first)\n2. Local JSON permit export\n3. Read selected Pipedrive deals")
                choice = input("Choice [1]: ").strip() or "1"
                if choice not in {"1", "2", "3"}:
                    raise ValueError("Choose 1, 2, or 3.")
                mode = {"1": "demo", "2": "json_file", "3": "pipedrive"}[choice]
            path = create_workspace(private_output(args.output), mode)
            print(f"Private setup created: {path}")
            print(f"Read {path.parent / 'START-HERE.md'}")
            print("No accounts connected. LLM disabled. Next: python3 -m sunbridge doctor --config " + shlex.quote(str(path)))
            return 0
        if args.command == "doctor":
            from .workspace import doctor
            result = doctor(args.config)
            for check in result["checks"]:
                print(f"{check['status'].upper()}: {check['name']} — {check['message']}")
            if result["llm_target"]:
                print(f"Configured LLM destination (not contacted): {result['llm_target']}")
            print(result["note"])
            return 0 if result["ready"] else 1
        if args.command == "run":
            from .workspace import run_workspace
            _display_result(run_workspace(args.config, allow_data_transfer=args.allow_llm_data_transfer), args.open)
            return 0
        if args.command == "llm-check":
            from .llm import LLMClient
            result = LLMClient(read_json(args.config), allow_data_transfer=args.allow_llm_data_transfer).check_connection()
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "import-mail":
            from .mail import load_mail
            if args.ahj not in load_profiles(args.profiles):
                raise ValueError("Choose an AHJ ID present in your validated profiles.")
            output = private_output(args.output)
            preflight_private_targets(output, ["messages.json"], sources=[args.input, args.profiles])
            messages = load_mail(args.input, args.ahj, args.limit)
            write_private_json(output / "messages.json", messages)
            print(f"Imported {len(messages)} messages into {output / 'messages.json'}")
            print("One operator-assigned AHJ. Sender and dates still need verification. No network requests.")
            return 0
        if args.command == "pipedrive-import":
            from .pipedrive import import_building_departments
            output = preflight_private_targets(private_output(args.output),
                ["building_departments.json", "import_summary.json", "profile_candidates.json", "crm_mapping.json"],
                sources=[args.token_file])
            result = import_building_departments(args.token_file, output, args.type_field, args.type_label)
            print(json.dumps(result, indent=2))
            return 0
        if args.command in {"pipedrive-fields", "pipedrive-deals"}:
            from .crm import discover_deal_fields, import_deal_permits
            output = private_output(args.output)
            target = output / ("fields.json" if args.command == "pipedrive-fields" else "permits.json")
            names = [target.name] if args.command == "pipedrive-fields" else [target.name, "import-summary.json"]
            sources = [args.token_file]
            if args.command == "pipedrive-deals":
                sources.extend([args.mapping, args.profiles])
            preflight_private_targets(output, names, sources=sources)
            if args.command == "pipedrive-fields":
                data = discover_deal_fields(args.token_file)
                write_private_json(target, data)
                print(f"Saved {len(data)} field definitions to {target}. No deals read.")
            else:
                from .workspace import ready_pipedrive_mapping
                profiles = load_profiles(args.profiles)
                mapping = ready_pipedrive_mapping(read_json(args.mapping), profiles)
                result = import_deal_permits(args.token_file, mapping, args.deal_ids)
                write_private_json(target, result["permits"])
                write_private_json(output / "import-summary.json", {"summary": result["summary"], "issues": result["issues"]})
                print(f"Saved {len(result['permits'])} mapped permit rows to {target}. Review {len(result['issues'])} import issues.")
            return 0
        if args.command == "validate":
            from .registry import integration_registry
            integration_registry()
            profiles = load_profiles(args.profiles)
            errors = validate_profile(read_json(ROOT / "templates/ahj-profile.json"))
            if errors:
                raise ValueError("Invalid contribution template: " + "; ".join(errors))
            expected = read_json(ROOT / "examples/expected-results.json")
            report = review_messages(read_json(ROOT / "examples/messages.json"), read_json(ROOT / "examples/permits.json"), load_profiles(ROOT / "profiles"))
            actual = {str(row["input_position"]): {"event_type": row["event"]["event_type"], "match": row["match"]["status"], "decision": row["decision"]} for row in report["items"]}
            if actual != expected:
                raise ValueError("Demo results differ from reviewed expectations; inspect the change.")
            print(f"Validated {len(profiles)} AHJ profiles, integration registry, contribution template, and {len(actual)} training outcomes.")
            return 0
        event_parser = None
        if args.command in {"demo", "start"}:
            messages, permits, profile_path = ROOT / "examples/messages.json", ROOT / "examples/permits.json", ROOT / "profiles"
        else:
            messages, permits, profile_path = args.messages, args.permits, args.profiles
            if args.llm_config:
                from .workspace import llm_parser
                event_parser = llm_parser(args.llm_config, args.allow_llm_data_transfer)
        output = private_output(args.output)
        sources = [messages, permits, profile_path]
        if args.command == "analyze" and args.llm_config:
            sources.append(args.llm_config)
        preflight_private_targets(output, ["review.json", "review.md", "review.html"], sources=sources, overwrite=True)
        inputs = read_json(messages)
        if event_parser is not None and (not isinstance(inputs, list) or len(inputs) > 100):
            raise ValueError("LLM review is limited to 100 messages per run.")
        report = review_messages(inputs, read_json(permits), load_profiles(profile_path), event_parser=event_parser)
        write_report(report, output)
        _display_result({"summary": report["summary"], "report_path": str(output / "review.html"), "crm_writes": 0}, args.open)
        return 0
    except (OSError, UnicodeError, ValueError, RuntimeError, EOFError) as exc:
        print(f"Could not complete the command: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
