"""Shared Solar Bridge CLI; the legacy permitkit module remains supported."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .validation import ROOT, load_profiles, validate_profile
from .workflow import review_messages, write_report


def private_output(value: str) -> Path:
    base = ROOT / "private"
    if base.is_symlink():
        raise ValueError("The private directory cannot be a symbolic link.")
    output = Path(value).resolve()
    if not output.is_relative_to(base.resolve()) or output == base.resolve():
        raise ValueError("Choose an output subdirectory under this clone's private/ directory.")
    return output


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Solar Bridge: understand permit messages and prepare an operator review. No CRM writes.")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Run the fictional training exercise without accounts or API keys")
    demo.add_argument("--output", default=str(ROOT / "private/demo"))
    analyze = sub.add_parser("analyze", help="Prepare proposals from a local JSON message export and permit records")
    analyze.add_argument("--messages", type=Path, required=True)
    analyze.add_argument("--permits", type=Path, required=True)
    analyze.add_argument("--profiles", type=Path, default=ROOT / "profiles")
    analyze.add_argument("--output", default=str(ROOT / "private/my-review"))
    validate = sub.add_parser("validate", help="Validate AHJ profiles, template and demo expectations")
    validate.add_argument("--profiles", type=Path, default=ROOT / "profiles")
    imp = sub.add_parser("pipedrive-import", help="Read organization fields and building-department records into private/")
    imp.add_argument("--token-file", type=Path)
    imp.add_argument("--output", default=str(ROOT / "private/pipedrive"))
    imp.add_argument("--type-field", help="Exact field code or name if automatic discovery is ambiguous")
    imp.add_argument("--type-label", default="Building Department")
    args = parser.parse_args(argv)
    try:
        if args.command == "pipedrive-import":
            from .pipedrive import import_building_departments
            result = import_building_departments(args.token_file, private_output(args.output), args.type_field, args.type_label)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "validate":
            profiles = load_profiles(args.profiles)
            errors = validate_profile(read_json(ROOT / "templates/ahj-profile.json"))
            if errors:
                raise ValueError("Invalid contribution template: " + "; ".join(errors))
            expected = read_json(ROOT / "examples/expected-results.json")
            report = review_messages(read_json(ROOT / "examples/messages.json"), read_json(ROOT / "examples/permits.json"), load_profiles(ROOT / "profiles"))
            actual = {str(row["input_position"]): {"event_type": row["event"]["event_type"], "match": row["match"]["status"], "decision": row["decision"]} for row in report["items"]}
            if actual != expected:
                raise ValueError("Demo results differ from reviewed expected-results.json; run tests and inspect the changes.")
            print(f"Validated {len(profiles)} AHJ profiles, contribution template, and {len(actual)} training outcomes.")
            return 0
        if args.command == "demo":
            messages, permits = ROOT / "examples/messages.json", ROOT / "examples/permits.json"
            profile_path = ROOT / "profiles"
        else:
            messages, permits, profile_path = args.messages, args.permits, args.profiles
        profiles = load_profiles(profile_path)
        report = review_messages(read_json(messages), read_json(permits), profiles)
        output = private_output(args.output)
        write_report(report, output)
        print(json.dumps(report["summary"], indent=2))
        print(f"Open {output / 'review.md'}")
        print("All results require operator review. CRM writes: 0.")
        return 0
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        # PipedriveError messages are deliberately sanitized by the importer.
        print(f"Could not complete the command: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
