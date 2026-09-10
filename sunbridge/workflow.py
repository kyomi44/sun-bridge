"""Prepare an operator review queue. This module has no CRM write operation."""
from __future__ import annotations

import hashlib
import json
import os
import string
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .events import parse_message
from .reconcile import match_event


def _message_fingerprint(message: dict) -> str:
    fields = {key: message.get(key) for key in ("sender", "subject", "body", "ahj_id")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def review_messages(messages: list[dict], permits: list[dict], profiles: dict[str, dict], *, event_parser=None) -> dict:
    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
        raise ValueError("Messages must be a JSON array of objects.")
    if not isinstance(permits, list) or any(not isinstance(p, dict) for p in permits):
        raise ValueError("Permits must be a JSON array of objects.")
    for permit in permits:
        if not permit.get("deal_id") or not isinstance(permit.get("ahj_id"), str):
            raise ValueError("Each permit record requires deal_id and ahj_id.")
        if permit.get("permit_id") is not None and not isinstance(permit["permit_id"], str):
            raise ValueError("Permit identifiers must be strings to preserve leading zeros.")
    ids: dict[str, list[int]] = {}
    rows = []
    for position, message in enumerate(messages):
        ahj_id = message.get("ahj_id")
        profile = profiles.get(ahj_id, {}) if isinstance(ahj_id, str) else {}
        event = (event_parser or parse_message)(message, profile)
        event["review_required"] = True
        event["observed_event_time"] = None
        event["issues"].append("receipt_time_is_not_confirmed_event_time")
        import_issues = message.get("import_issues", [])
        if isinstance(import_issues, list):
            event["issues"].extend(issue for issue in import_issues if isinstance(issue, str))
        if not profile:
            event["issues"].append("unknown_ahj_profile")
        event["profile_verification"] = profile.get("verification", {}).get("status", "unknown")
        raw_date = message.get("received_at")
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError()
            sort_key = dt.astimezone(timezone.utc).isoformat()
        except (ValueError, AttributeError, TypeError):
            sort_key = ""
            event["issues"].append("missing_or_invalid_receipt_time")
        if event["event_type"] == "unknown":
            match = {"status": "unmatched", "deal_id": None, "method": None, "issues": ["unrecognized_event"]}
        else:
            match = match_event(event, permits)
        row = {
            "input_position": position + 1, "receipt_time_sort_key": sort_key,
            "event": event, "match": match, "decision": "needs_operator_review",
            "original_message": {key: message.get(key) for key in ("message_id", "sender", "subject", "body", "received_at", "timestamp_source", "date_header_at", "ignored_attachment_count")},
            "duplicate_of": None,
        }
        rows.append(row)
        key = event["message_id"]
        if key:
            ids.setdefault(key, []).append(position)
    # A colliding identifier invalidates every occurrence, not just the later one.
    for key, indices in ids.items():
        if len(indices) < 2:
            continue
        fingerprints = {_message_fingerprint(messages[i]) for i in indices}
        if len(fingerprints) > 1:
            for i in indices:
                rows[i]["event"]["issues"].append("conflicting_duplicate_message_id")
                rows[i]["decision"] = "hold_conflicting_message_id"
                rows[i]["match"] = {"status": "ambiguous", "deal_id": None, "method": None, "issues": ["message_id_collision"]}
        else:
            for i in indices[1:]:
                rows[i]["event"]["issues"].append("duplicate_message_id")
                rows[i]["duplicate_of"] = indices[0] + 1
                rows[i]["decision"] = "skip_duplicate"
    rows.sort(key=lambda row: (row["receipt_time_sort_key"], row["input_position"]))
    active = [r for r in rows if r["decision"] != "skip_duplicate"]
    return {
        "schema_version": 1, "mode": "review_only", "crm_writes": 0,
        "warning": "Proposed events only. Receipt times are not guaranteed event times. This report does not infer the current permit status or utility permission to operate.",
        "summary": {
            "input_messages": len(messages), "review_items": len(active),
            "duplicates_skipped": len(rows) - len(active),
            "recognized_events": sum(r["event"]["event_type"] != "unknown" for r in active),
            "event_types": dict(Counter(r["event"]["event_type"] for r in active)),
            "match_results": dict(Counter(r["match"]["status"] for r in active)),
        },
        "items": rows,
    }


def _md(value) -> str:
    """Render source text without Markdown, HTML, or automatic URL links.

    Character references become literal text after Markdown syntax is parsed.
    Encoding punctuation also handles bare URLs, emails, backslash escapes, and
    source text that already contains an HTML entity. JSON keeps the original.
    """
    text = str(value if value is not None else "—").replace("\n", " ").replace("\r", " ")
    return "".join(f"&#{ord(char)};" if char in string.punctuation else char for char in text)


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Permit notification review", "",
        "Every result is a proposal for a permitting operator to review. No CRM records were changed.", "",
        _md(report["warning"]), "",
        f"Messages: {_md(summary['input_messages'])} · Review items: {_md(summary['review_items'])} · Duplicates skipped: {_md(summary['duplicates_skipped'])}", "",
    ]
    imported = report.get("crm_import")
    if isinstance(imported, dict):
        imported_summary = imported.get("summary")
        imported_summary = imported_summary if isinstance(imported_summary, dict) else {}
        lines += ["## CRM import checks — private", "",
                  "Read these checks before accepting event matches. Failed reads or missing, invalid, or unmapped fields can leave selected projects out of the candidate records. Check the affected deal, source field, mapping, and access permissions; correct the issue and rerun the selected import. Do not guess a match to compensate for missing CRM records.", ""]
        counters = (("requested_unique_deals", "Selected deals"), ("deals_read", "Deals read"),
                    ("deals_with_permits", "Deals with permit rows"), ("permit_rows", "Permit rows"),
                    ("issue_count", "Import issues"), ("duplicate_input_ids_ignored", "Repeated input IDs ignored"))
        lines += [" · ".join(label + ": " + _md(imported_summary.get(key)) for key, label in counters), ""]
        issues = imported.get("issues")
        if isinstance(issues, list) and issues:
            lines += ["| Affected deal | Source field | Issue code |", "|---|---|---|"]
            for issue in issues:
                if isinstance(issue, dict):
                    lines.append("| " + " | ".join(_md(issue.get(key)) for key in ("deal_id", "source_field", "code")) + " |")
                else:
                    lines.append("| Not available | Not available | Unstructured issue; inspect the private JSON report |")
            lines.append("")
        else:
            lines += ["No CRM import issues were reported. This does not certify the mapping or establish complete project coverage.", ""]
        lines += ["Keep these deal and field identifiers private; do not paste this report into a public issue.", ""]
    lines += ["| Message | Proposed event | Scope | Permit or address | Proposed deal | Match | Handling |",
              "|---|---|---|---|---|---|---|"]
    for row in report["items"]:
        event, match = row["event"], row["match"]
        values = [event["message_id"], event["event_type"], event["scope"], event["permit_id"] or event["address"], match["deal_id"], match["status"], row["decision"]]
        lines.append("| " + " | ".join(_md(value) for value in values) + " |")
    lines += ["", "## Evidence and operator checks", "", "Confirm the source, the permit identity, and the meaning before updating your CRM. Unknown formats and ambiguous matches require investigation. The sender is not authenticated by this tool.", ""]
    for row in report["items"]:
        event, match = row["event"], row["match"]
        lines += [f"### Input {_md(row['input_position'])}: {_md(event['message_id'])}", "", f"Subject: {_md(row['original_message']['subject'])}", "", f"Evidence ({_md(event['evidence']['field'])}): {_md(event['evidence']['text'])}", "", f"Sender: {_md(row['original_message']['sender'])} · Received: {_md(event['received_at'])}", "", f"Rule: {_md(event['rule_id'])} · Match method: {_md(match['method'])}", "", "Review notes: " + "; ".join(_md(issue) for issue in event["issues"] + match["issues"]), "", "- [ ] Confirm correct project and permit", "- [ ] Confirm the event from the original notice / portal", "- [ ] Record operator decision in your usual workflow", ""]
    return "\n".join(lines)


def _report_directory(output: Path) -> Path:
    """Check an arbitrary component output directory without following aliases.

    CLI callers additionally enforce their private-directory boundary. macOS
    spells its platform temp root through the system /var alias; canonicalize
    that exact root, not any user-created aliases within it, for component tests.
    """
    output = Path(output).absolute()
    if ".." in output.parts:
        raise ValueError("Review output cannot contain parent-directory traversal.")
    platform_temp = Path(tempfile.gettempdir()).absolute()
    if output.is_relative_to(platform_temp):
        output = platform_temp.resolve() / output.relative_to(platform_temp)
    for parent in [output, *output.parents]:
        if parent.is_symlink():
            raise ValueError("Review output paths cannot contain symbolic links.")
        if parent.exists() and not parent.is_dir():
            raise ValueError("Review output must use a directory path.")
    return output


def _check_report_target(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("Review output cannot overwrite a symbolic link.")
    if path.exists() and not path.is_file():
        raise ValueError("Every report output must be a regular file.")


def write_report(report: dict, output: Path) -> None:
    """Preflight all report leaves, then replace each with a private staged file.

    Replacing a hard-linked leaf changes only that directory entry. No existing
    inode is truncated and no report content is written under permissive old
    modes. Replacements are atomic per file, not a three-file transaction.
    """
    from .html_report import render_html
    output = _report_directory(output)
    names = ("review.json", "review.md", "review.html")
    for name in names:
        _check_report_target(output / name)
    # Complete rendering and encoding before creating or changing any files.
    contents = (
        (json.dumps(report, indent=2) + "\n").encode("utf-8"),
        render_markdown(report).encode("utf-8"),
        render_html(report).encode("utf-8"),
    )
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = []
    try:
        for name, content in zip(names, contents):
            _report_directory(output)
            fd, temporary = tempfile.mkstemp(prefix=".sunbridge-report-", dir=output)
            temporary_path = Path(temporary)
            staged.append((temporary_path, output / name))
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        # Recheck all leaves together after staging, before any replacement.
        _report_directory(output)
        for _, target in staged:
            _check_report_target(target)
        for temporary_path, target in staged:
            _report_directory(output)
            _check_report_target(target)
            os.replace(temporary_path, target)
    finally:
        for temporary_path, _ in staged:
            if temporary_path.exists():
                temporary_path.unlink()
