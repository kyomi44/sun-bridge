# Decision 0001: a forkable, review-only pilot

Status: implemented for developer evaluation; operator and live-provider validation remain outstanding.

## Need and scope

An interested solar team should be able to fork the project, run a fictional example without accounts, and progress to one small authorized private workflow. The immediate implementation adds guided setup, offline readiness checks, email-file import, explicit Pipedrive deal reads, a CRM capability registry, optional constrained model extraction, and private browser-readable reports.

This is not approval to send customer data to a service, write CRM fields, make government decisions, or claim that a contributor is ready for a job. Configuration defaults to no LLM. All proposed events require review. The people-first charter and governance are unchanged.

## Choices and alternatives

Build one explicit Pipedrive read path and a documented common record format before claiming broad CRM coverage. List other vendors as contribution targets. The alternative—calling any export or API key a supported connector—would obscure the work an operator still needs to understand.

Use the OpenAI-compatible Chat Completions protocol as an optional starting point, with an operator-selected endpoint/model. Do not claim compatibility with native APIs that have different request formats. Rules and the fictional demo work without any provider. A future protocol adapter needs its own tests and privacy review.

Keep the model's task narrow: propose a grounded event from one selected email. The model has no tools, CRM roster, deal-selection authority, or write access. Local matching remains separate. Reject invalid output; model transport failures do not trigger an automatic retry, fallback provider, or alternative interpretation.

## Benefits, risks, and controls

Operators can practice evidence interpretation and matching; technical helpers can contribute a small, testable adapter. Reports show original evidence and warnings without requiring the reader to inspect JSON.

Real email content—including quoted history—may leave the computer if a model is enabled. Each such run requires explicit data-transfer authorization. The guide explains the payload and credential handling. This is private operator-controlled processing, not a change to the prohibition on publishing customer records. An endpoint choice is not a privacy or retention guarantee.

Models can misread authentic text; exact quotations are not proof of correct conclusions. Synthetic tests and configuration checks do not establish production accuracy. AHJ assignment, profile coverage, address completeness, CRM field mapping, timestamps, and duplicate handling remain review responsibilities. Read-only adapters can still expose data if their outputs or credentials are shared carelessly.

## Evidence and missing perspectives

Implementation uses official API references, fictional fixtures, offline transport simulations, an independent code review, and a fresh-checkout demo. Earlier organization discovery had a limited private live read; the new Pipedrive deal adapter and model connection are not live-certified. No private customer export is part of the public repository.

An experienced operator's review of the new end-to-end workflow has not yet been obtained. No operator-validation, employer partnership, funded placement, accessibility certification, or production readiness is claimed. Invite operator and technical feedback through the issue forms without publishing their private records or naming participants without consent.

## Revisit before expanding authority

Privately evaluate a narrow AHJ/event set with known outcomes and unseen holdout examples. Measure event and match errors separately, along with abstentions and operator ability to find and explain mistakes. Record scope and unresolved issues publicly using synthetic examples only.

Saved approval decisions, CRM writes, scheduled inbox monitoring, utility work, and public timeline analytics remain separate proposals with the roadmap's controls and review gates. Disable an unsafe connector if evidence warrants it. A later release should update this record with verified pilot scope and missing perspectives, not overwrite its original limits.
