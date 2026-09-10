"""Render the public, volume-free email signal registry without reading mail.

Coverage is an evidence claim, not a parser capability declaration. In
particular, a subject-level candidate is not an exact permitting event.
"""
from __future__ import annotations

from datetime import date
from html import escape
import json
from pathlib import Path
import re


TOP_KEYS = {
    "schema_version", "evidence_reviewed_on", "evidence_basis",
    "identity_status", "public_runtime", "entries",
}
ENTRY_KEYS = {"id", "name", "candidate_signals", "pilot_events", "identity_note"}
CANDIDATE_SIGNALS = (
    "submission", "review_or_correction", "approval", "issuance", "inspection", "payment",
)
PILOT_EVENTS = (
    "submission_received", "action_required", "plans_approved", "permit_issued",
    "inspection_passed", "inspection_failed", "permit_expired",
)
IDENTITY_NOTES = {
    "none", "historical_domain_aliases", "sender_spelling_variant",
    "provisional_office_grouping", "unusual_domain_alias", "cross_platform_identity",
}
CANDIDATE_LABELS = (
    "Submission", "Review / correction", "Approval", "Issuance", "Inspection", "Payment",
)
PILOT_LABELS = (
    "Submission received", "Action required", "Plans approved", "Permit issued",
    "Inspection passed", "Inspection failed", "Permit expired",
)
NOTE_LABELS = {
    "none": "Provisional identity",
    "historical_domain_aliases": "Historical domain aliases grouped; identity needs confirmation",
    "sender_spelling_variant": "Sender spelling variant grouped; identity needs confirmation",
    "provisional_office_grouping": "Provisional office grouping; jurisdiction needs confirmation",
    "unusual_domain_alias": "Unusual domain alias grouped; identity needs confirmation",
    "cross_platform_identity": "Cross-platform identity grouped; identity needs confirmation",
}
INVALID = "Invalid public email coverage registry."


def validate_registry(data: object) -> list[str]:
    """Return bounded, value-free errors for the deliberately narrow contract."""
    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        return ["Registry must contain exactly the public coverage fields."]
    errors = []
    expected = {
        "schema_version": "v1", "evidence_basis": "historical_private_review",
        "identity_status": "provisional", "public_runtime": "not_enabled",
    }
    for key, value in expected.items():
        if data[key] != value:
            errors.append(f"Invalid {key}.")
    reviewed = data["evidence_reviewed_on"]
    if not isinstance(reviewed, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed):
        errors.append("Evidence review date must be an ISO calendar date.")
    else:
        try:
            date.fromisoformat(reviewed)
        except ValueError:
            errors.append("Evidence review date must be an ISO calendar date.")
    entries = data["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 2000:
        return errors + ["Entries must be a bounded, nonempty list."]
    ids, names = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            errors.append("An entry has unexpected or missing fields.")
            continue
        entry_id = entry["id"]
        if not isinstance(entry_id, str) or len(entry_id) > 80 or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", entry_id):
            errors.append("Entry IDs must be bounded lowercase kebab-case strings.")
        elif entry_id in ids:
            errors.append("Entry IDs must be unique.")
        else:
            ids.add(entry_id)
        name = entry["name"]
        if not isinstance(name, str) or not 1 <= len(name) <= 100 or not name.strip() or not name.isprintable() or name != name.strip():
            errors.append("Entry names must be bounded, printable, nonblank strings.")
        elif name.casefold() in names:
            errors.append("Entry names must be unique.")
        else:
            names.add(name.casefold())
        for key, allowed in (("candidate_signals", CANDIDATE_SIGNALS), ("pilot_events", PILOT_EVENTS)):
            values = entry[key]
            if (not isinstance(values, list) or len(values) > len(allowed)
                    or any(not isinstance(value, str) or value not in allowed for value in values)
                    or len(set(values)) != len(values)):
                errors.append(f"Invalid or repeated {key}.")
        note = entry["identity_note"]
        if not isinstance(note, str) or note not in IDENTITY_NOTES:
            errors.append("Invalid identity note.")
    # Avoid returning thousands of repeated errors for a malformed input.
    return list(dict.fromkeys(errors))


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(INVALID)
        result[key] = value
    return result


def load_registry(path: str | Path) -> dict:
    """Read only the supplied public JSON, without echoing bad contents or paths."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError(INVALID)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        _validated(data)
        return data
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        raise ValueError(INVALID) from None


def _validated(data: object) -> dict:
    if validate_registry(data):
        raise ValueError(INVALID)
    return data


def _entries(data: dict, *, pilot: bool = False) -> list[dict]:
    entries = _validated(data)["entries"]
    return sorted((entry for entry in entries if not pilot or entry["pilot_events"]),
                  key=lambda entry: (entry["name"].casefold(), entry["id"]))


def _markdown(value: str) -> str:
    """Escape both Markdown structure and embedded HTML in public labels."""
    value = escape(value, quote=True)
    for character in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|"):
        value = value.replace(character, "\\" + character)
    return value


def render_markdown(data: dict) -> str:
    entries = _entries(data)
    pilot = _entries(data, pilot=True)
    lines = [
        "# AHJ email milestone signals", "",
        "A public map of email signals that may support reviewable CRM updates. "
        "It reports milestone presence, never inbox volumes, customer records, or matching results.", "",
        "**These are evidence levels, not production support claims.** AHJ identities remain provisional. "
        "Real-AHJ parsers are not enabled by this registry, and no automatic CRM writes are added.", "",
        "[How to interpret and contribute](email-coverage-methodology.md) · "
        "[Public registry](../coverage/ahj-email-signals.json)", "",
        "## Exact milestones observed in the private pilot", "",
        "**P** = an exact milestone was proposed in a historical, private, review-only pilot. "
        "It still needs operator validation. **—** = not demonstrated; it does not mean unavailable.", "",
        "![Exact milestone proposals observed in the private pilot; table follows.](assets/email-pilot-milestones.svg)", "",
        "| AHJ | " + " | ".join(PILOT_LABELS) + " |",
        "| --- | " + " | ".join("---" for _ in PILOT_EVENTS) + " |",
    ]
    for entry in pilot:
        marks = ["P" if event in entry["pilot_events"] else "—" for event in PILOT_EVENTS]
        lines.append("| " + _markdown(entry["name"]) + " | " + " | ".join(marks) + " |")
    if not pilot:
        lines.extend(["", "No exact pilot milestones are recorded."])
    lines.extend([
        "", "Submission received does not mean accepted. Approved plans do not mean permit issued. "
        "An inspection result does not mean final approval. Action required is not a terminal denial.", "",
        "## Candidate email signal families", "",
        "**C** = a subject-level signal family was observed and needs validation. "
        "A candidate mark is not a confirmed event, a complete lifecycle, or an implemented parser. "
        "**—** = not demonstrated in the reviewed evidence.", "",
        "![Alphabetical AHJ-by-signal-family candidate matrix; accessible table follows.](assets/email-candidate-signals.svg)", "",
        "<details>", "<summary>Accessible candidate signal table and identity-review notes</summary>", "",
        "| AHJ | " + " | ".join(CANDIDATE_LABELS) + " | Identity review |",
        "| --- | " + " | ".join("---" for _ in CANDIDATE_SIGNALS) + " | --- |",
    ])
    for entry in entries:
        marks = ["C" if signal in entry["candidate_signals"] else "—" for signal in CANDIDATE_SIGNALS]
        lines.append("| " + _markdown(entry["name"]) + " | " + " | ".join(marks)
                     + " | " + NOTE_LABELS[entry["identity_note"]] + " |")
    lines.extend([
        "", "</details>", "", "## Before a CRM update", "",
        "Validate the message body and source, distinguish the exact milestone, confirm the AHJ "
        "and permit/deal identity, handle duplicates and older messages, and require human review. "
        "Current status must not be inferred from historical email alone.", "",
        "Only AHJ names, qualitative milestone flags, and identity-review categories are published. "
        "The chart contains no email addresses, subjects, permit identifiers, customer data, "
        "message counts, match counts, or private evidence links.", "",
        f"Evidence reviewed: {data['evidence_reviewed_on']}. Historical private review; "
        "not live monitoring or a claim of ongoing availability.", "",
        "Generated from the public registry with `python3 scripts/render_email_coverage.py`. "
        "This rendering step does not open an inbox or private analysis.", "",
    ])
    return "\n".join(lines)


def _text(x: int | float, y: int | float, value: str, css: str, *, anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{escape(value)}</text>'


def _svg_open(width: int, height: int, title: str, description: str) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="coverage-title coverage-description">',
        f'<title id="coverage-title">{escape(title)}</title>',
        f'<desc id="coverage-description">{escape(description)}</desc>',
        '<style>',
        'text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }',
        '.background { fill: #f6f8fa; } .panel { fill: #ffffff; stroke: #d0d7de; }',
        '.title { fill: #172a3a; font-size: 25px; font-weight: 700; }',
        '.subtitle { fill: #536473; font-size: 15px; }',
        '.eyebrow { fill: #516170; font-size: 11px; font-weight: 700; letter-spacing: 1.4px; }',
        '.column { fill: #425667; font-size: 16px; font-weight: 650; }',
        '.name { fill: #1c3345; font-size: 16px; font-weight: 600; }',
        '.row-alt { fill: #f6f8fa; } .rule { stroke: #e6ebef; stroke-width: 1; }',
        '.pilot-bg { fill: #d9f0e8; } .pilot-mark { fill: #125642; font-size: 15px; font-weight: 750; }',
        '.candidate-bg { fill: #fff0c8; } .candidate-mark { fill: #765000; font-size: 15px; font-weight: 750; }',
        '.empty { fill: #788894; font-size: 17px; }',
        '.note { fill: #536473; font-size: 14px; }',
        '@media (prefers-color-scheme: dark) {',
        '.background { fill: #0d1117; } .panel { fill: #161b22; stroke: #30363d; }',
        '.title, .name { fill: #e6edf3; } .subtitle, .note, .column, .eyebrow { fill: #a8b8c7; }',
        '.row-alt { fill: #1c232d; } .rule { stroke: #30363d; }',
        '.pilot-bg { fill: #153f34; } .pilot-mark { fill: #86dbb7; }',
        '.candidate-bg { fill: #43391f; } .candidate-mark { fill: #efcc78; }',
        '.empty { fill: #82909d; }',
        '}',
        '</style>',
        f'<rect width="{width}" height="{height}" rx="16" class="background"/>',
    ]


def _mark(x: int | float, y: int | float, *, present: bool, pilot: bool) -> list[str]:
    if not present:
        return [_text(x, y + 5, "—", "empty", anchor="middle")]
    css, label = ("pilot", "P") if pilot else ("candidate", "C")
    return [f'<circle cx="{x}" cy="{y}" r="12" class="{css}-bg"/>',
            _text(x, y + 4.5, label, css + "-mark", anchor="middle")]


def _label_lines(label: str) -> tuple[str, ...]:
    if label == "Review / correction":
        return ("Review /", "correction")
    return tuple(label.split(" ", 1))


def _name_lines(name: str, width: int) -> list[str]:
    """Conservatively wrap public names, including unbroken future labels.

    Pixel estimates use a deliberately generous glyph width at the fixed name
    font size. An accessible per-row title retains the complete identity label.
    """
    def measure(text: str) -> float:
        return sum(5 if char in " ilI.,'!|" else 16 if char in "MW@#%&" or ord(char) > 255
                   else 11 if char.isupper() else 9 for char in text)

    lines = []
    current = ""
    for word in name.split():
        if current and measure(current + " " + word) > width:
            lines.append(current)
            current = ""
        while measure(word) > width:
            end = 1
            while end < len(word) and measure(word[:end + 1]) <= width:
                end += 1
            lines.append(word[:end])
            word = word[end:]
        current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [name]


def _render_svg(data: dict, *, pilot: bool) -> str:
    entries = _entries(data, pilot=pilot)
    columns = PILOT_EVENTS if pilot else CANDIDATE_SIGNALS
    labels = PILOT_LABELS if pilot else CANDIDATE_LABELS
    field = "pilot_events" if pilot else "candidate_signals"
    width = 960
    name_width = 196 if pilot else 292
    left, right = 28, 932
    cell_width = (right - left - name_width) / len(columns)
    header_bottom = 210
    wrapped_names = [_name_lines(entry["name"], name_width - 36) for entry in entries]
    row_heights = [max(46, 22 * len(lines) + 14) for lines in wrapped_names]
    body_bottom = header_bottom + sum(row_heights)
    if not entries:
        body_bottom += 48
    height = body_bottom + 164
    title = "Email milestones observed in the private pilot" if pilot else "Candidate AHJ email signals"
    description = (
        "Alphabetical AHJ milestone matrix. P means an exact milestone was proposed in a historical "
        "private review-only pilot, not validated production support. A dash means not demonstrated. "
        "No real-AHJ parser or automatic CRM update is enabled. An accessible table is in the coverage documentation."
        if pilot else
        "Alphabetical AHJ signal-family matrix. C means a subject-level candidate signal that needs "
        "validation, not a confirmed event or implemented parser. A dash means not demonstrated. "
        "Identities remain provisional. An accessible table is in the coverage documentation."
    )
    out = _svg_open(width, height, title, description)
    out.extend([
        _text(28, 32, "SUN BRIDGE  /  EMAIL EVIDENCE", "eyebrow"),
        _text(28, 70, title, "title"),
        _text(28, 98, "Exact event proposals · Operator validation required" if pilot else
              "Broad signal families · Subject evidence only", "subtitle"),
        _text(28, 120, "Real-AHJ parsers not enabled · Historical evidence, not live monitoring", "subtitle"),
        f'<rect x="{left}" y="148" width="{right - left}" height="{body_bottom - 148}" rx="10" class="panel"/>',
        _text(left + 18, 175, "AHJ", "column"),
        _text(left + 18, 195, "Provisional identity", "note"),
    ])
    for index, label in enumerate(labels):
        x = left + name_width + (index + 0.5) * cell_width
        lines = _label_lines(label)
        for line_index, line in enumerate(lines):
            out.append(_text(x, 173 + line_index * 20 if len(lines) > 1 else 184,
                             line, "column", anchor="middle"))
    out.append(f'<line x1="{left}" y1="{header_bottom}" x2="{right}" y2="{header_bottom}" class="rule"/>')
    y = header_bottom
    for index, (entry, lines, row_height) in enumerate(zip(entries, wrapped_names, row_heights)):
        if index % 2 == 0:
            out.append(f'<rect x="{left + 1}" y="{y + 1}" width="{right - left - 2}" height="{row_height - 1}" class="row-alt"/>')
        center_y = y + row_height / 2
        first_y = center_y - (len(lines) - 1) * 10 + 5
        # Per-row titles preserve the identity caveat without clutter or private provenance.
        out.append(f'<g><title>{escape(entry["name"] + ": " + NOTE_LABELS[entry["identity_note"]])}</title>')
        for line_index, line in enumerate(lines):
            out.append(_text(left + 18, first_y + line_index * 20, line, "name"))
        for column_index, column in enumerate(columns):
            x = left + name_width + (column_index + 0.5) * cell_width
            out.extend(_mark(x, center_y, present=column in entry[field], pilot=pilot))
        out.append('</g>')
        y += row_height
        if index < len(entries) - 1:
            out.append(f'<line x1="{left + 1}" y1="{y}" x2="{right - 1}" y2="{y}" class="rule"/>')
    if not entries:
        out.append(_text(left + 18, header_bottom + 30, "No exact pilot milestones are recorded.", "note"))
    legend_y = body_bottom + 32
    out.extend(_mark(42, legend_y - 4, present=True, pilot=pilot))
    out.extend([
        _text(64, legend_y, "Private pilot proposal · not yet operator-validated" if pilot else
              "Subject signal · needs validation", "note"),
        _text(28, legend_y + 24, "—  Not demonstrated · not proof of absence", "note"),
        _text(28, legend_y + 54, "Receipt ≠ acceptance. Plans approved ≠ permit issued. Inspection result ≠ final approval." if pilot else
              "A signal family does not establish the exact milestone, email authenticity, or a match to a CRM deal.", "note"),
        _text(28, legend_y + 76, "Real-AHJ parsers not enabled. No automatic CRM writes. Review the methodology before use.", "note"),
        _text(28, legend_y + 108, f"Evidence reviewed {data['evidence_reviewed_on']} · Volumes and private evidence omitted", "note"),
        '</svg>', '',
    ])
    return "\n".join(out)


def render_pilot_svg(data: dict) -> str:
    """Render exact pilot evidence separately from the candidate inventory."""
    return _render_svg(data, pilot=True)


def render_candidate_svg(data: dict) -> str:
    """Render subject-level candidates without upgrading their evidence level."""
    return _render_svg(data, pilot=False)
