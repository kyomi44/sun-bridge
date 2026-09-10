# Sun Bridge roadmap

Sun Bridge aims to make permitting work easier to understand, supervise, and improve. Operators, technical contributors, and public agencies should be able to contribute expertise and review the results. These phases describe proposed work and the evidence needed to advance; they are not delivery dates or commitments from partner organizations.

## 1. Learn and review locally — available now

The starter includes three profiles: two sourced real AHJs with disabled rule parsers, and one fictional training authority. Fourteen synthetic input messages demonstrate event interpretation, matching, duplicates, and exceptions. The local review tool makes no CRM changes. Guided setup, offline readiness checks, local EML/MBOX import, and private browser-readable reports support a bounded pilot. Optional Pipedrive adapters discover fields and organizations and read explicitly selected deals using account-specific mappings. Optional model extraction is experimental, requires explicit data-transfer authorization, and cannot choose deals or update records. Neither the new deal reads nor any model/provider is live-certified; there is no inbox monitoring.

Start with the [learning path](learning-path.md). The immediate contribution is clearer documentation, a sourced jurisdiction correction, or a synthetic example with an expected result. Synthetic test success does not establish real-world accuracy.

**Operator outcome:** explain a proposed event and match, catch a planted failure, and state what evidence is still missing. A mentor records demonstrated competence separately from software test results.

## 2. Validate one AHJ privately — proposed

Choose a narrow permit type and event set with an operator who knows the process. Review representative private examples across dates and formats, including corrections, late notices, missing identifiers, duplicates, and multiple permits per project. Check events against original evidence and official records.

Before calling the pilot reliable, define acceptable error and abstention rates, measure event interpretation and permit matching separately, and reserve unseen cases for evaluation. Report sample scope, known missing channels, and failure cases. Publish only reviewed process knowledge, code, and synthetic regression examples. Real messages, customer details, and CRM mappings stay private.

**Operator outcome:** investigate an unfamiliar exception, challenge an incorrect interpretation, and contribute a test that prevents its recurrence. Confirm these skills on unseen cases before expanding responsibility.

## 3. Reviewed updates and monitoring — proposed, after pilot gates

Add saved operator decisions and a review queue before integrating writes. A workflow owner must define which fields may change, which events are supported, and who can authorize or correct a change. Require evidence links, duplicate protection, conflict detection, an audit trail, and a tested reversal procedure that respects intervening edits.

Live inbox connections and scheduled monitors need explicit access and action limits, visible health and coverage checks, a working pause control, and a responsible person for exceptions. Validate recovery from missed runs and changed templates. Begin with observation and proposed updates; expand automation only for validated cases within the owner's authorization. These controls and integrations are not implemented in the current demo.

**Operator outcome:** demonstrate rejection, pause, escalation, and recovery using the implemented controls in a safe test environment. A successful technical integration alone does not authorize an untrained person or the software to change production records.

## 4. Fair timeline reporting — proposed

Useful aggregate timelines must describe their clocks and their limits. Define start and end events separately for submission-to-intake, review, applicant correction, issuance, inspection, and utility interconnection. Separate elapsed time from verified periods awaiting an applicant or another party; do not assign responsibility when the evidence cannot establish it. Email receipt time is not automatically the underlying event time.

For every aggregate, state the observation period, source coverage, sample size, permit scope, missing timestamps, excluded records, and treatment of still-open cases. Separate materially different project types and show distributions rather than a single unexplained average. Sparse or selectively observed inbox samples cannot fairly rank departments. Establish minimum publication thresholds, suppress small or identifying groups, and share no project-level private data.

**Operator outcome:** explain what a timeline measures, identify unfair comparisons or missing evidence, and handle a correction request. Learners should be able to distinguish an observed delay from an unsupported attribution of blame.

[SolarTRACE's permitting, inspection, and interconnection dataset](https://data.openei.org/submissions/8221) is existing work to study: it reports timeline results across AHJs and utilities and documents coverage limitations. Sun Bridge has no partnership with that project and does not currently import its data or produce comparable analytics.

## 5. Utility workflows and agency collaboration — proposed

Extend the model to utilities only with distinct utility IDs, interconnection application IDs, events, and verification sources. A building permit, passed inspection, interconnection approval, and permission to operate are separate evidence requirements. Utility imports, parsers, and workflows are not enabled in this starter.

Invite willing AHJs and utilities to help define structured notifications, downloadable exports, or supported APIs. Agree on field meanings, access, change notices, correction paths, and ongoing ownership. A useful collaboration could reduce repeated status inquiries while retaining clear accountability for decisions.

[SolarAPP+ already automates eligible solar permitting for participating authorities](https://www.energy.gov/cmei/systems/streamlining-solar-permitting-solarapp), and its [integration documentation](https://help.gosolarapp.org/article/120-how-does-solarapp-work-with-existing-ahj-permitting-software) describes working with local permitting systems. These are references for compatibility and learning, not claimed Sun Bridge partnerships or implemented integrations.

Any later AI assistance should make evidence review easier, expose uncertainty, and undergo independent evaluation and operator feedback. Work affecting official code review or permit approval would require the responsible authority's participation and approval process. An LLM's output must not become unilateral authority to approve a permit.

**Operator outcome:** translate process knowledge into clear information requirements, verify that a utility event is not being mistaken for a permit decision, and participate in acceptance testing with the responsible institution.

## People make each phase work

Pair new contributors with experienced reviewers, document operational knowledge, and recognize maintenance as ongoing work. The [learning path](learning-path.md) proposes competency milestones and possible future paid learning or mentorship programs. Advance capability together with the people and controls needed to supervise it.
