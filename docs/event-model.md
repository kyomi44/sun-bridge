# Event meanings and review boundaries

A message is evidence of a possible event. An event is associated with a particular permit and a particular stage of its process. A current status is a conclusion drawn from the accepted event history. These are separate records conceptually, even when a small CRM implementation stores them together.

## Keep the meanings separate

| Event | Evidence to look for | Common confusion |
| --- | --- | --- |
| Receipt / submission acknowledgement | Explicit acknowledgement of the identified application. | An applicant's sent email is not an AHJ acknowledgement. |
| Intake accepted | Explicit statement that intake or completeness checks passed. | Receipt alone does not establish completeness. |
| Review underway | An identified review entered an active review stage. | A payment receipt is not review progress. |
| Corrections required | A request to revise or supply information. | A correction cycle is not necessarily a denial. |
| Review approved | Approval of the stated review or discipline. | One discipline's approval may leave others outstanding. |
| Permit issued | Explicit issuance of the identified permit. | An issued invoice or an approval subject to fees is different. |
| Denied / rejected | Explicit disposition, with the object and scope preserved. | A rejected document upload may not mean a denied permit. |
| Inspection scheduled | A named inspection has a scheduled date. | Scheduling does not prove it occurred. |
| Inspection passed / failed | A result for a named inspection. | One passed inspection does not establish permit closeout. |
| Permit closed / finaled | Explicit permit-level closeout evidence. | Utility permission to operate is a separate approval. |
| Expiration / cancellation | Explicit expiration or cancellation of the permit. | A warning that expiration is approaching is not expiration. |

This table is the interpretation guide. The current demo covers only the event patterns implemented by its parser; it does not recognize every wording or every event in the table. Preserve the original phrase and avoid forcing unsupported messages into a known category.

## Preserve evidence and time

Retain the source message identifier, the evidence that supports the event, the event's stated date when available, and the time the message was received. Preserve uncertainty when a date or scope is missing. A forwarded or quoted old message does not establish a new event just because it arrived today.

Handle repeated messages without duplicating business events. Do not advance or reverse a permit solely because an email arrived last. A later correction may reopen a review, while a delayed acknowledgement may add historical evidence without changing the current status. Conflicting events require review of their scope and dates.

## Review gates

Before accepting an event, check that the source is attributable to the correct jurisdiction, that the permit match is unique, and that the text supports the proposed meaning. Shared software sender addresses require additional jurisdiction evidence. Customer names alone cannot establish a match.

Unrecognized wording, missing identifiers, conflicting dates, multiple possible permits, or a changed notification template should produce a review task. Absence of email is missing evidence, not a status. The jurisdiction's verification channel provides the next place to check.

Future AI assistance may suggest an interpretation or summarize evidence. Its confidence score is not a substitute for matching evidence, validated event rules, or operator judgment. Message text must never become instructions to run commands or take external actions.
