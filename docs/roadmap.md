# Sun Bridge roadmap

Build a dependable shared knowledge base, connect it to real operations, and expand automation only when its evidence and controls justify doing so. The milestones below are capability gates, not delivery dates or commitments from partner organizations.

## 1. A useful public catalog — available now

Import the bundled SolarTRACE data locally, search building departments and utilities, inspect source-reported requirements and historical timelines, and export selected records. Preserve source identifiers, reporting periods, units, and unknowns. See the [source notes](solartrace-sources.md).

The historical medians describe business-day timelines for 2017–2024 installation cohorts. They are not current permit statuses, forecasts, guarantees, or a complete inventory of every jurisdiction. A source-reported submission method does not establish notification coverage.

Next improvements should make source updates reproducible, identify changed records, and make corrections easy to trace to evidence. Do not silently replace historical observations with new claims.

## 2. Reconcile and maintain organization knowledge

Use catalog reconciliation to propose links to an operator's private organization records. Check the entity type, source identity, state, and actual jurisdiction or utility scope before accepting a link. Keep the approved mapping in the operator's own controlled process; reconciliation does not write to a CRM or prove which authority serves a property.

Explicit profile-to-catalog links can attach a private review report's proposed event evidence to catalog entities. Keep those proposals separate from confirmed statuses and from the source's historical benchmarks; attachment is not approval or automatic correction of source data.

Extend sourced profiles with verified submission methods, notification channels, and status-verification channels as separate facts. Dates and confidence in the evidence matter more than filling every field. A missing value should remain unknown.

Pipedrive provides a read-only organization discovery path and explicitly selected deal imports. Additional CRM adapters should preserve the same privacy, mapping, and review boundaries rather than claim compatibility from a manifest alone.

## 3. Validate real permitting communications

Local EML/MBOX import, guided setup, offline checks, and private reports are available. Optional model extraction is experimental and explicitly authorized. A catalog record or documented profile does not establish a reliable email parser; the real AHJ rule parsers are not enabled.

Validate a narrow permit type and event set with someone who knows the process. Include corrections, late notices, missing identifiers, multiple permits, duplicates, and unfamiliar formats. Check interpretations against original evidence and official records; reserve unseen cases for evaluation.

**Gate:** measure event interpretation and permit matching separately, report errors and abstentions, identify missing channels, and assign a responsible reviewer. Publish only authorized public knowledge and synthetic regression cases. A model or test result alone cannot authorize an operational change.

## 4. Reviewed updates and reliable monitoring — proposed

Add saved review decisions before integrating external writes. The workflow owner must define allowed fields, supported events, approval authority, and corrective procedures. Require evidence, duplicate protection, conflict checks, an audit trail, and recovery that respects intervening edits.

Live inbox connections and scheduled monitors need explicit access limits, health and coverage checks, a working pause control, and an owner for exceptions. Validate missed-run recovery and changed templates. Begin with observation and proposed updates; expand only within the user's authorization.

**Gate:** operators can reject, pause, investigate, escalate, and recover in a safe test environment. These controls, CRM writes, and live monitoring are not implemented today.

## 5. Transparent operational timelines — proposed

The catalog supplies existing historical benchmarks. New operational analytics need their own measurement contract: explicit start/end events, verified timestamps, observation periods, sample sizes, permit scopes, excluded records, and treatment of still-open cases. Email arrival is not automatically the underlying event time.

Separate agency review from verified time awaiting an applicant or another party. Do not assign responsibility without evidence or combine materially different project types into an unexplained average. Medians from separate groups must not be treated as individual observations and averaged into a new overall median.

**Gate:** explain the clock and its uncertainty, protect small or identifying groups, and provide a correction path. Sparse inbox samples cannot fairly rank departments. Share no private project-level history in the public repository.

## 6. Utility workflows and institutional collaboration — proposed

Utility entities and historical benchmarks are in the public catalog; live utility account connectors and interconnection workflows are not implemented. Extend operations with distinct utility IDs, interconnection application IDs, events, and verification sources. A building permit, passed inspection, interconnection approval, and permission to operate remain separate decisions.

Work with willing AHJs and utilities on structured notifications, downloadable exports, and supported APIs. Agree on field meanings, access, change notices, correction paths, and ongoing ownership. Existing tools such as [SolarAPP+](https://www.energy.gov/cmei/systems/streamlining-solar-permitting-solarapp) and its [local-system integrations](https://help.gosolarapp.org/article/120-how-does-solarapp-work-with-existing-ahj-permitting-software) provide useful references, not claimed project partnerships.

**Gate:** the responsible institution participates in acceptance testing and retains decision authority. Any later AI-assisted code review needs appropriate evaluation and an accountable approval process; an LLM cannot grant a permit unilaterally.

## People and accountability across every milestone

Better data and software should increase the operator's ability to inspect, challenge, and improve the process. Evaluate those capabilities alongside accuracy and time saved. Support documentation, mentorship, and compensated maintenance where resources permit, without promising jobs or programs that do not exist. The [charter](../CHARTER.md), [governance](../GOVERNANCE.md), and [learning path](learning-path.md) describe these commitments.
