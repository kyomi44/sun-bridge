"""Sun Bridge command interface; prior module names remain compatible."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import webbrowser
from pathlib import Path

from .privateio import private_path, preflight_private_targets, read_json_file, write_private_json
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sun Bridge: learn, connect selected inputs, and review permit events. No CRM writes.")
    sub = parser.add_subparsers(dest="command", required=True)
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
