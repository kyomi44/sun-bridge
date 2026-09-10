"""Static private report: no scripts, links, forms, remote assets, or actions."""
from __future__ import annotations

from html import escape

EVENT_LABELS = {
    "submission_received": "Application received", "application_accepted": "Intake accepted",
    "action_required": "Corrections or action required", "review_started": "Review started",
    "review_completed": "Review completed", "plans_approved": "Plans approved",
    "permit_ready_to_issue": "Permit ready to issue", "permit_issued": "Permit issued",
    "permit_denied": "Permit denied", "permit_expired": "Permit expired",
    "permit_closed": "Permit closed", "inspection_scheduled": "Inspection scheduled",
    "inspection_passed": "Inspection passed", "inspection_failed": "Inspection failed",
    "payment_due": "Payment due", "payment_received": "Payment received",
    "unknown": "Notice needs interpretation",
}
HANDLING = {"needs_operator_review": "Operator review needed", "skip_duplicate": "Duplicate — skip",
            "hold_conflicting_message_id": "Conflicting message ID — hold"}
CRM_ISSUE_GUIDANCE = {
    "deal_read_failed": "Check access to this selected deal and connection settings, then retry the read.",
    "unexpected_deal_response": "Ask a technical helper to check the selected deal ID and adapter response before retrying.",
    "missing_or_unmapped_ahj": "Verify this deal's AHJ field and add an explicit mapping to the correct loaded profile.",
    "missing_service_address": "Verify the complete service address and unit. A permit-number match still needs review.",
    "invalid_service_address": "Check that the mapped field contains a complete service address in a supported text or address format.",
    "invalid_address_unit": "Verify the unit in the address field; do not guess or omit it.",
    "conflicting_address_unit": "Resolve the conflicting unit values against the original project record before matching.",
    "invalid_customer_name": "Check the optional name-field mapping. A name alone cannot establish a permit match.",
    "missing_permit_identifier": "Check the mapped permit field and the original permit number. Missing data is not evidence that no permit exists.",
    "non_string_permit_identifier": "Use a text field for the permit identifier so leading zeros and punctuation are preserved.",
}


def _safe(value) -> str:
    return escape(str(value) if value is not None and value != "" else "Not available", quote=True)


def _label(value) -> str:
    return str(value).replace("_", " ") if value else "Not available"


def _crm_section(imported: dict) -> str:
    """Show only the adapter's review fields, never an arbitrary CRM payload."""
    summary = imported.get("summary", {})
    parts = ["<section><h2>CRM import checks</h2>",
             "<p>Failed reads or missing mappings can leave selected deals out of matching. An unmatched notice does not prove that no permit exists. Resolve the issues below and rerun the read before relying on coverage.</p><dl>"]
    if isinstance(summary, dict):
        for key, label in (("requested_unique_deals", "Selected deals"), ("deals_read", "Deals read"),
                           ("deals_with_permits", "Deals with permit records"), ("permit_rows", "Permit records"),
                           ("issue_count", "Import issues"), ("duplicate_input_ids_ignored", "Repeated selections ignored")):
            parts.append("<dt>" + label + "</dt><dd>" + _safe(summary.get(key)) + "</dd>")
    parts.append("</dl>")
    issues = imported.get("issues", [])
    if not issues:
        parts.append("<p>No import issues were reported. Verify the selected deals, field mappings, and permit records before accepting matches.</p>")
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict):
            continue
        code = issue.get("code")
        guidance = CRM_ISSUE_GUIDANCE.get(code) if isinstance(code, str) else None
        parts.append("<article><h3>Selected deal " + _safe(issue.get("deal_id")) + "</h3><dl><dt>Issue code</dt><dd>" + _safe(code) + "</dd><dt>Source field</dt><dd>" + _safe(issue.get("source_field")) + "</dd></dl>")
        parts.append("<p>" + _safe(guidance or "Ask a technical helper to inspect this issue and the selected mapping before relying on the imported records.") + "</p></article>")
    parts.append("</section>")
    return "".join(parts)


def render_html(report: dict) -> str:
    """Render evidence as escaped text, without modifying the input report."""
    summary = report.get("summary", {})
    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
             "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
             "<title>Sun Bridge · Permit review</title><style>",
             "body{font:16px/1.55 system-ui,sans-serif;color:#172c34;background:#f5f5ee;margin:0}main{max-width:960px;margin:auto;padding:32px 20px}h1{font-size:2.2rem;line-height:1.2}h2{font-size:1.35rem}h3{font-size:1rem;margin-bottom:8px}.eyebrow{letter-spacing:.08em;text-transform:uppercase;color:#446456}.notice{background:#fff0cb;padding:16px;border-left:4px solid #ad7400}.stats{display:flex;gap:12px;flex-wrap:wrap}.stat,article{background:white;border:1px solid #d9dfd6;border-radius:10px;padding:20px}.stat{flex:1;min-width:140px}.stat strong{display:block;font-size:1.7rem}article{margin:20px 0}dl{display:grid;grid-template-columns:minmax(120px,180px) 1fr;gap:8px 16px}dt{color:#51636a}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f1;padding:16px;font:inherit}li{overflow-wrap:anywhere}.muted{color:#51636a}@media(max-width:540px){dl{grid-template-columns:1fr}dt{font-weight:600}dd{margin-bottom:8px}}",
             "</style></head><body><main><p class=\"eyebrow\">Sun Bridge · Private local review</p>",
             "<h1>Understand the notice.<br>Check the permit.</h1>",
             "<p>Review each proposed event and project match before making a decision in your usual workflow.</p>",
             "<p class=\"notice\">This file has no update buttons or live connections. The tool does not authenticate senders or establish a current permit status.</p>",
             "<p>" + _safe(report.get("warning")) + "</p><div class=\"stats\">"]
    for key, label in (("input_messages", "Messages imported"), ("review_items", "Items to review"), ("duplicates_skipped", "Duplicates skipped")):
        parts.append("<div class=\"stat\"><strong>" + _safe(summary.get(key)) + "</strong>" + label + "</div>")
    parts.append("</div>")
    if isinstance(report.get("crm_import"), dict):
        parts.append(_crm_section(report["crm_import"]))
    parts.append("<h2>Review queue</h2>")
    if not report.get("items"):
        parts.append("<p>No messages to review.</p>")
    for row in report.get("items", []):
        event, match, source = row.get("event", {}), row.get("match", {}), row.get("original_message", {})
        evidence = event.get("evidence", {})
        parts.append("<article><p class=\"muted\">Input " + _safe(row.get("input_position")) + "</p><h2>" + _safe(EVENT_LABELS.get(event.get("event_type"), _label(event.get("event_type")))) + "</h2>")
        fields = [("Handling", HANDLING.get(row.get("decision"), _label(row.get("decision")))),
                  ("Match", _label(match.get("status"))), ("Proposed deal", match.get("deal_id")),
                  ("Permit number", event.get("permit_id")), ("Service address", event.get("address")),
                  ("AHJ profile", event.get("ahj_id")), ("Event scope", _label(event.get("scope"))),
                  ("Message ID", event.get("message_id")), ("Sender (unverified)", source.get("sender")),
                  ("Receipt time", event.get("received_at")),
                  ("Claimed sent date (not receipt or event time)", source.get("date_header_at") or source.get("date_header")),
                  ("Timestamp source", source.get("timestamp_source")),
                  ("Ignored attachments", source.get("ignored_attachment_count")),
                  ("Match method", _label(match.get("method"))), ("Rule", event.get("rule_id"))]
        parts.append("<dl>" + "".join("<dt>" + label + "</dt><dd>" + _safe(value) + "</dd>" for label, value in fields) + "</dl>")
        llm = event.get("llm")
        if isinstance(llm, dict):
            parts.append("<h3>AI proposal details</h3><dl>" + "".join("<dt>" + label + "</dt><dd>" + _safe(llm.get(key)) + "</dd>" for key, label in (("provider", "Provider"), ("model", "Model"), ("prompt_version", "Prompt version"))) + "</dl>")
        parts.append("<h3>Original subject</h3><pre>" + _safe(source.get("subject")) + "</pre>")
        parts.append("<h3>Source evidence · " + _safe(evidence.get("field")) + "</h3><pre>" + _safe(evidence.get("text")) + "</pre>")
        if source.get("body"):
            parts.append("<details><summary>Original plain text body</summary><pre>" + _safe(source.get("body")) + "</pre></details>")
        issues = [*event.get("issues", []), *match.get("issues", []), *source.get("import_issues", [])]
        parts.append("<h3>Review notes</h3><ul>" + "".join("<li>" + _safe(_label(issue)) + "</li>" for issue in dict.fromkeys(issues)) + "</ul>")
        parts.append("<p>Confirm the source, project, and event. Record your decision or the evidence still needed in your usual workflow.</p></article>")
    parts.append("<p class=\"muted\">Keep this report private. Message contents and addresses are displayed as text only.</p></main></body></html>")
    return "".join(parts)
