"""Convert an explicitly supported message format into a reviewable proposal.

Rules are maintained code: load profiles only from a source you trust. A sender
allowlist is useful for routing, but does not authenticate an email. This module
neither validates SPF/DKIM nor permits unattended CRM updates.
"""

from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Any


EVENT_TYPES = frozenset({
    "submission_received", "application_accepted", "action_required",
    "review_started", "review_completed", "plans_approved",
    "permit_ready_to_issue", "permit_issued", "permit_denied",
    "permit_expired", "permit_closed", "inspection_scheduled",
    "inspection_passed", "inspection_failed", "payment_due",
    "payment_received", "unknown",
})
SCOPES = frozenset({"permit", "review", "inspection", "payment", "unknown"})


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _sender_address(value: Any) -> str:
    """Extract one mailbox; do not treat a domain or display name as a sender."""
    value = _text(value)
    if not value or "\n" in value or "\r" in value:
        return ""
    _, address = parseaddr(value)
    # Require a single mailbox, with no comma-separated list or trailing text.
    if not re.fullmatch(r"[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+", address):
        return ""
    if "<" in value:
        if not re.fullmatch(r"[^<>]*<[^<>]+>\s*", value):
            return ""
    elif value != address:
        return ""
    return address.casefold()


def parse_message(message: dict, profile: dict) -> dict:
    """Return a proposal from exactly one supported subject rule.

    Each rule supplies ``id``, ``event_type``, ``scope``, and a regular-expression
    ``pattern``. Patterns use fullmatch, case-insensitively; named groups
    ``permit_id`` and ``address`` supply identifiers. Bodies and quoted history
    are deliberately not searched. Zero rules, multiple matching rules, invalid
    configuration, or mismatched routing metadata produce an unknown event.
    """
    subject = message.get("subject", "")
    subject = subject if isinstance(subject, str) else ""
    sender = _sender_address(message.get("sender"))
    event = {
        "message_id": _text(message.get("message_id")),
        "ahj_id": _text(message.get("ahj_id")),
        "received_at": _text(message.get("received_at")),
        "event_type": "unknown",
        "scope": "unknown",
        "permit_id": None,
        "address": None,
        "evidence": {"field": "subject", "text": subject},
        "rule_id": None,
        "review_required": True,
        "sender_authentication": "not_verified",
        "issues": [],
    }

    def abstain(issue: str) -> dict:
        event["issues"].append(issue)
        return event

    if not event["message_id"]:
        return abstain("missing_message_id")
    if not event["ahj_id"] or event["ahj_id"] != _text(profile.get("id")):
        return abstain("ahj_mismatch_or_missing")
    parser = profile.get("parser")
    if not isinstance(parser, dict):
        return abstain("parser_not_configured")
    if not isinstance(parser.get("status"), str) or parser["status"] not in {"experimental", "validated"}:
        return abstain("parser_not_enabled")
    senders = parser.get("sender_allowlist")
    if not isinstance(senders, list) or not senders:
        return abstain("sender_allowlist_missing")
    allowed = {_sender_address(item) for item in senders}
    if "" in allowed:
        return abstain("invalid_sender_allowlist")
    if not sender or sender not in allowed:
        return abstain("sender_not_allowlisted")
    rules = parser.get("subject_rules")
    if not isinstance(rules, list) or not rules:
        return abstain("subject_rules_missing")
    matches = []
    rule_ids = set()
    for rule in rules:
        if not isinstance(rule, dict):
            return abstain("invalid_rule_configuration")
        rule_id = _text(rule.get("id"))
        if (
            not rule_id or rule_id in rule_ids
            or not isinstance(rule.get("event_type"), str)
            or rule["event_type"] not in EVENT_TYPES - {"unknown"}
            or not isinstance(rule.get("scope"), str)
            or rule["scope"] not in SCOPES - {"unknown"}
            or not isinstance(rule.get("pattern"), str)
            or not rule["pattern"]
        ):
            return abstain("invalid_rule_configuration")
        rule_ids.add(rule_id)
        try:
            match = re.fullmatch(rule["pattern"], subject, flags=re.IGNORECASE)
        except re.error:
            return abstain("invalid_rule_pattern")
        if match:
            matches.append((rule, match.groupdict()))
    if not matches:
        return abstain("no_supported_subject_rule")
    if len(matches) != 1:
        return abstain("multiple_matching_subject_rules")
    rule, fields = matches[0]
    event.update({
        "event_type": rule["event_type"],
        "scope": rule["scope"],
        "permit_id": _text(fields.get("permit_id")) or None,
        "address": _text(fields.get("address")) or None,
        "rule_id": rule["id"],
    })
    if not event["permit_id"] and not event["address"]:
        event["issues"].append("missing_reconciliation_identifiers")
    if parser.get("status") == "experimental":
        event["issues"].append("experimental_parser")
    return event
