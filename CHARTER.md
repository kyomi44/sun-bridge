# Solar Bridge charter

## Purpose

Solar Bridge exists to empower people to understand, supervise, and improve increasingly automated solar operations. Shared permitting knowledge and useful software are means to that end—not a substitute for the people doing the work.

We want operators to gain transferable skills, meaningful decision-making authority, and opportunities to help shape the systems they use. We welcome people learning these skills as well as experienced practitioners.

The project currently provides a read-only review tool, synthetic training examples, and documented jurisdiction profiles. It does not monitor a live inbox, update a CRM, submit permits, or make approval decisions. Commitments below concerning live automation are requirements for future work, not claims about features available today.

## Commitments

### 1. Learning is part of the product

Documentation, exercises, explanations, and approachable contribution paths are first-class project work. Someone should be able to progress from interpreting evidence to matching records, testing rules, investigating errors, and maintaining a narrowly scoped integration.

Useful contributions include explaining a process, questioning an interpretation, improving an exercise, and identifying an exception. Programming is one contribution path, not the price of admission.

Supported learning and paid training opportunities are project priorities. We seek employer-supported learning time, mentorship, and paid pathways where resources permit. No funded training program, job opening, or employment guarantee is implied by this charter. Unpaid public contributions must not be presented as a promise of a job.

### 2. Operators have meaningful authority

An operator must be able to understand the evidence and uncertainty behind a proposed action, question its interpretation, and reject it without being treated as an obstacle to automation.

Before future integrations can change external records, they must provide a clear way for authorized operators to pause automation, correct its assumptions, inspect its history, and recover from mistakes. Recovery may require a documented corrective action where a direct reversal is impossible. These controls must be taught and tested, not merely listed in documentation.

Human review must involve judgment and sufficient information—not a requirement to approve whatever the system proposes.

### 3. Automation earns a bounded responsibility

We progress from read-only proposals to supervised changes and only then consider narrowly authorized automatic actions. Each transition needs representative evidence, separate measures of interpretation and record-matching accuracy, known limitations, an accountable owner, and a tested failure response.

Systems must be able to say “unknown.” A synthetic test passing does not establish production readiness. Missing notifications do not prove that a process has stopped or finished.

Governmental permitting decisions remain the responsibility of the relevant authority; utility decisions remain with the relevant utility. Future AI-assisted review is not permission for Solar Bridge to grant approvals or obscure who is accountable.

### 4. Skills and knowledge remain portable

Prefer understandable data formats, documented interfaces, and reusable examples over dependence on a single employer, CRM, model provider, or proprietary service. Teach why a decision is justified, not only which button to press.

Jurisdiction and, eventually, utility knowledge should be reusable while preserving the differences between their workflows and legal authority.

### 5. Transparency respects people and context

Share verified public process information and synthetic examples. Keep customer records, private correspondence, credentials, and operational exports out of the public repository. Follow the [data handling guide](docs/data-handling.md).

Future timeline reporting must distinguish agency review from applicant response time, disclose missing observations and sample limitations, and protect private records. Incomplete inbox evidence must not become an unsupported jurisdiction ranking. Provide a way for operators and jurisdictions to challenge or correct published claims.

Modernization should be developed with the people responsible for the process, not presented as technology imposed on them.

### 6. Success includes human outcomes

Evaluate operator understanding, ability to catch errors, decision authority, accessibility of learning, and documented opportunities alongside time saved. Evaluate wrong-record updates, unsupported status changes, missed events, and recovery effectiveness alongside automation coverage.

When claiming learning or employment outcomes, state what was actually measured and what remains unknown. Do not claim that the project guarantees net job creation or work that can never be automated. Reduced staffing is not a project success metric.

## Stewardship and limits

The [governance process](GOVERNANCE.md) makes maintainers accountable for these commitments and explains how they may change.

The project retains its [MIT License](LICENSE). This charter guides project stewardship; it does not add license restrictions or guarantee how every downstream organization will use the software or make employment decisions.
