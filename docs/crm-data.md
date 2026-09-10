# CRM data for permit reconciliation

A CRM supplies the project context needed to interpret a permitting message. Keep the model independent of a particular CRM so an operator can use the same jurisdiction knowledge in different systems.

## The minimum useful records

| Record | Information to maintain |
| --- | --- |
| Jurisdiction / Building Department | Stable local ID, canonical name, state, geographic scope, official portal and sources, known notification and verification channels. |
| Deal / project | Internal deal ID, customer display name, complete service address including unit, and links to its permits. |
| Permit / application | Internal permit ID, associated deal ID, verified AHJ ID, external application/permit numbers, permit type, full service address, and known event history. |
| Reviewed event | Source message ID, permit association, event meaning and scope, evidence, relevant dates, review outcome, and reviewer context. |

Application numbers and issued permit numbers may differ. Preserve both and the evidence that links them. Model multiple permits per deal: an electrical permit, building permit, and a revision can have different identifiers and dispositions. A one-field “permit status” on the deal may hide those differences.

## Matching order

Use AHJ plus an exact normalized permit/application number when it uniquely identifies a record. If that is unavailable, an exact complete normalized service address, including unit, can identify a candidate when the jurisdiction is verified and the candidate is unique. Check for multiple permits, historical jobs, and incomplete address details before accepting it.

A name is supporting evidence only. Do not auto-match on a name alone, a shared street number, a partial address, or the postal city. Postal addresses do not define AHJ boundaries. An organizational city/county field can help research jurisdiction; it does not prove that a specific property is under that department.

Preserve original address text alongside normalization. A missing unit must not be silently treated as a matching unit. Keep ambiguous candidates for review and record why the match was accepted or rejected.

## Represent capabilities separately

At the organization level, separate `submission_method`, `notification_channels`, `verification_channels`, and `automated_review`. A department may take applications through a portal, send selected events by email, and require the portal to verify status. A single mutually exclusive “email or website” choice would lose that information.

Also record geographic scope, official sources, when they were checked, and whether each claim is unknown, documented, or experimental. An inbox observation is evidence of a notification that occurred; it does not prove that every applicant receives it or that every lifecycle stage is covered.

## Pipedrive discovery

The optional importer reads field metadata and organizations to help identify Building Department records and available geographic fields. It does not create a new field or populate permit status. Review its output privately before proposing mappings. See [Pipedrive field discovery](pipedrive-field-discovery.md).

Field IDs and option IDs are account-specific. Resolve them from the account's metadata; do not copy IDs from another operator's setup. A missing or ambiguous Building Department classification needs a mapping decision, not a guessed filter.
