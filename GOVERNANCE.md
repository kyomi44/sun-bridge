# Solar Bridge governance

## An early-stage project

Solar Bridge is maintainer-led. Maintainers with repository write access are responsible for reviewing contributions, protecting private information, explaining consequential decisions, and keeping the project aligned with its [charter](CHARTER.md).

This document and the charter are the project's initial governance adoption. Subsequent amendments follow the review process below.

The project does not currently claim an elected board, an operator council, institutional partnerships, or a funded training program. We invite operators, learners, jurisdiction staff, utility staff, developers, and employers to participate. Contribution volume or sponsorship does not automatically confer decision-making authority.

## Everyday decisions

Use focused issues and pull requests so people can understand and review a proposed change. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

For routine fixes, maintainers review correctness, evidence, privacy, tests, and documentation before merging. A public source can establish a documented process without establishing that a parser is reliable. Unknowns must remain visible.

Maintainers should explain a declined contribution constructively and identify a smaller or safer path when one exists. Nontechnical observations and corrections deserve the same respectful review as code.

## Changes affecting operators

Seek review from an operator familiar with the affected work for changes to event meanings, review expectations, matching behavior, training, or automation authority. Provide a plain-language description and an example of the changed experience.

Record whose perspective was sought, the concerns raised, and their resolution, with permission before naming participants. If operator review is unavailable, state that limitation. Do not describe a workflow as operator-validated or promote automation to production readiness on that basis.

Before introducing any capability that writes to an external system, document:

- What authority the user grants and how it is limited.
- What evidence supports each action and how uncertainty is handled.
- How an authorized operator can reject a proposal or pause the integration.
- How incorrect actions are detected, investigated, and corrected or reversed.
- Who maintains the integration and what evaluation supports its intended use.

These are future release requirements. The current tool is read-only and supplies none of the implied external-write or live-monitoring capabilities.

## Mission-impacting decisions

Open a public issue or pull request before changing automation authority, public-data practices, access to learning resources, employment-related programs, or project control. Describe:

1. The need and the people affected.
2. Expected benefits, risks, and alternatives.
3. Effects on operator skills, authority, privacy, and access.
4. Available evidence, unresolved questions, and a way to revisit the decision.

Invite affected perspectives and record the maintainer decision and rationale in the discussion before release. Document material sponsorship or employer interests relevant to the decision. Do not publish personal or confidential information to make a decision “transparent.”

Sponsors may support work and propose priorities, but sponsorship does not bypass review or override the charter. Announce a funded opportunity or partnership only after its terms and participants are confirmed.

## Changing the charter or governance

Changes require a clearly labeled public proposal showing the exact text, rationale, and implications. Allow at least seven calendar days for comment before merging and explicitly invite operator feedback for changes affecting their role.

Record the comments considered, any missing perspectives, the final rationale, and the approving maintainer in the issue or pull request. Do not hide a mission change in an unrelated edit. Prior versions remain available in repository history.

## Concerns and accountability

Raise process or mission concerns in a repository issue without including private records. Maintainers should acknowledge substantive concerns, explain the next step, and document their resolution rather than closing them without explanation.

Follow [SECURITY.md](SECURITY.md) for vulnerabilities or exposed private data. Maintainers may immediately disable or remove an unsafe feature or exposed material, then publish a sanitized explanation when safe. This emergency path does not waive the review required to change the charter.

The governance process directs this project's maintainers. It neither changes the [MIT License](LICENSE) nor controls a downstream employer's staffing decisions. We will report demonstrated outcomes without promising employment or forecasting inevitable labor-market outcomes.
