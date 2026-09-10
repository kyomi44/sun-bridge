"""Prepare an operator review queue. This module has no CRM write operation."""
from __future__ import annotations

import hashlib
import json
import string
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .events import parse_message
from .reconcile import match_event


def _message_fingerprint(message: dict) -> str:
    fields = {key: message.get(key) for key in ("sender", "subject", "body", "ahj_id")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def review_messages(messages: list[dict], permits: list[dict], profiles: dict[str, dict]) -> dict:
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
        event = parse_message(message, profile)
        event["observed_event_time"] = None
        event["issues"].append("receipt_time_is_not_confirmed_event_time")
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
            "original_message": {key: message.get(key) for key in ("message_id", "sender", "subject", "body", "received_at")},
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
        "| Message | Proposed event | Scope | Permit or address | Proposed deal | Match | Handling |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["items"]:
        event, match = row["event"], row["match"]
        values = [event["message_id"], event["event_type"], event["scope"], event["permit_id"] or event["address"], match["deal_id"], match["status"], row["decision"]]
        lines.append("| " + " | ".join(_md(value) for value in values) + " |")
    lines += ["", "## Evidence and operator checks", "", "Confirm the source, the permit identity, and the meaning before updating your CRM. Unknown formats and ambiguous matches require investigation. The sender is not authenticated by this tool.", ""]
    for row in report["items"]:
        event, match = row["event"], row["match"]
        lines += [f"### Input {_md(row['input_position'])}: {_md(event['message_id'])}", "", f"Subject: {_md(event['evidence']['text'])}", "", f"Sender: {_md(row['original_message']['sender'])} · Received: {_md(event['received_at'])}", "", f"Rule: {_md(event['rule_id'])} · Match method: {_md(match['method'])}", "", "Review notes: " + "; ".join(_md(issue) for issue in event["issues"] + match["issues"]), "", "- [ ] Confirm correct project and permit", "- [ ] Confirm the event from the original notice / portal", "- [ ] Record operator decision in your usual workflow", ""]
    return "\n".join(lines)


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, content in [("review.json", json.dumps(report, indent=2) + "\n"), ("review.md", render_markdown(report))]:
        path = output / name
        if path.is_symlink():
            raise ValueError("Review output cannot overwrite a symbolic link.")
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
