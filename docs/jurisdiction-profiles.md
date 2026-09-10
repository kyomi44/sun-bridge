# Jurisdiction profiles

A profile records what is known about one permitting authority and how an operator can check it. It is scoped knowledge with sources and dates, not a promise that every permit follows the same process.

## What belongs in a profile

| Dimension | Record |
| --- | --- |
| Identity and scope | Canonical AHJ name, state, city/county coverage where established, permit types, and geographic limitations. |
| `submission_method` | Where an applicant submits an application and supporting documents. |
| `notification_channels` | How updates may arrive, and which events are supported by evidence. |
| `verification_channels` | Where an operator can check a status or resolve a missing update. |
| `automated_review` | Platform, eligible project scope, and documented limits where known. |
| Sources and currency | Official source URLs, `last_checked`, schema version, and unresolved questions; preserve revisions in version history. |
| Evidence status | Unknown, documented, or experimental as appropriate to the claim. |

Use the shipped profiles as the exact machine-readable structure. Do not infer geographical authority from a postal city, organization name, software vendor, or an email sender alone.

**Unknown** means evidence is insufficient. **Documented** means the stated claim has supporting documentation within the described scope. **Experimental** means a proposed behavior or parsing rule still needs validation. A profile may document email notifications while its parser remains experimental. None of these labels means production-certified.

## A useful Cape Coral example

Cape Coral's official permitting page describes online submission through EnerGov. Its CSS guide says a designated account email receives application status updates, invoices, and process information. The portal also exposes application and permit status and inspection outcomes. Those sources support distinct submission, notification, and verification capabilities; they do not establish the exact wording or completeness of every email event. Checked September 9, 2026. [Permitting services](https://www.capecoral.gov/departments/development_services/permitting_services_division/index.php), [CSS documentation](https://www.capecoral.gov/departments/development_services/permitting_services_division/energov_citizen_self_service_css.php).

Operators should use synthetic examples to describe a message pattern and maintain private evaluations on real records. A format observed in an old inbox should be recorded with its observation period and checked against current behavior before being relied on.

## Central policy and local process

California's SB 379 program requires most non-exempt cities and counties to implement online automated permitting for eligible residential solar and paired storage. Local platforms include SolarAPP+, Symbium, and custom systems. This does not establish one statewide permitting office or one universal portal. The CEC's dashboard shows jurisdiction-specific adoption and identifies its data as self-reported. [CEC program](https://www.energy.ca.gov/programs-and-topics/programs/residential-solar-permit-reporting-program-sb-379), [CEC dashboard](https://www.energy.ca.gov/programs-and-topics/programs/residential-solar-permit-reporting-program-sb-379/residential-solar).

Florida uses a statewide Building Code with local enforcement by authorized governments and districts, subject to statutory exceptions. Municipal and county workflows therefore need separate profiles. [Florida Statutes 553.73](https://www.flsenate.gov/Laws/Statutes/2026/553.73), [Florida Statutes 553.80](https://www.flsenate.gov/Laws/Statutes/2026/553.80).

Washington electrical permits are handled by L&I except in listed city or utility jurisdictions, including Seattle. Profiles should identify the authority for the relevant permit type rather than assume that all permits in a state share an office. [Washington L&I jurisdiction guide](https://www.lni.wa.gov/licensing-permits/electrical/electrical-permits-fees-and-inspections/city-electrical-permits-inspections).

These background sources were checked September 9, 2026. They explain the profile model; consult each current jurisdiction's official instructions for a particular project.

## Maintenance

Contributors can submit a source or correction through the Jurisdiction knowledge issue form. Maintainers check its scope and date, record the profile change in version history, and add or amend synthetic tests where behavior changes. Change `schema_version` only when the data structure changes. Keep historical observations distinguishable from current documentation. If a source or template changes, narrow the affected claim or mark it for review until evidence supports it again.
