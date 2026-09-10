# Solar Bridge

Helping people learn to understand, supervise, and improve increasingly automated work—starting with residential solar.

Solar Bridge is an open-source learning and operations project. Shared permitting knowledge and practical tools give operators and technical helpers a way to build transferable skills together. Operators can contribute without writing code, inspect the evidence behind a proposed event, and help determine how automation should behave.

**Empowering people is the primary goal.** We aim to increase capability, agency, and economic opportunity alongside reliable solar processes. The [charter](CHARTER.md) makes this mission explicit; the [governance guide](GOVERNANCE.md) explains how it informs project decisions. Learning and employment outcomes must be measured, not promised in advance.

Solar Bridge is the working name of this independent community project, formerly Open Permit Kit. Similar commercial names exist; this is not a claim of affiliation or naming clearance. See the [name and compatibility notes](docs/project-name.md).

## What works today

This first version is experimental. The included examples are synthetic; no profile or parser is certified for production. The tool generates a review preview and does not update a CRM, submit permits, or monitor a live inbox.

The working parser uses explicit rules, not an AI service, to recognize supported subject formats in the fictional training profile. It does not extract events from email bodies or attachments. Cape Coral and Lee County have sourced capability profiles, but no enabled email parsers yet. All proposed events require operator review; a sender allowlist does not authenticate a message.

## Try it in 20 minutes

**No installation:** start with the [browser-only training page](docs/training-preview.md). Read five made-up cases, explain your decisions, and compare them with the answers. A technical helper can set up the working demo when you are ready.

For the working demo, you need Python 3.10 or newer. There are no external Python dependencies. Download and unzip this repository using **Code → Download ZIP**, or clone it:

```sh
git clone https://github.com/kyomi44/solar-bridge.git
cd solar-bridge
```

Open a terminal in the repository folder, then run:

```sh
python3 -m solarbridge demo
```

Open `private/demo/review.md` in a Markdown preview to read the result. `private/demo/review.json` contains the structured preview. Work through the [20-minute operator exercise](docs/operator-guide.md), then use the [learning path](docs/learning-path.md) to demonstrate interpretation, matching, and error-investigation skills with a mentor.

To validate the shipped data and run the tests:

```sh
python3 -m solarbridge validate
python3 -m unittest discover -s tests -v
```

To run the same review process explicitly:

```sh
python3 -m solarbridge analyze --messages examples/messages.json --permits examples/permits.json --output private/my-review
```

Keep real messages and CRM exports under `private/` on your own computer. They are private working data, never public examples. See [data handling](docs/data-handling.md) before using your own inputs.

Existing users can continue using `python3 -m permitkit`. The rename does not change the version 1 profile format or move private files. Run from the repository checkout; an installed-package distribution is not supported yet.

## What is in the project?

| Component | Purpose |
| --- | --- |
| Jurisdiction profiles | Record official sources, geographic scope, submission methods, notification channels, and ways to verify a status. |
| Synthetic messages and permits | Practice matching and interpretation without sharing a customer's records. |
| Review preview | Show candidate events and matches for an operator to inspect. |
| Operator and contributor guides | Explain decisions, common failure cases, and how to improve coverage. |
| Charter, governance, and learning path | Tie technical progress to operator capability, authority, and supported learning. |
| Optional Pipedrive discovery | Read field metadata and a Building Department organization roster into private local files. |

The project distinguishes application receipt, plan review, corrections, approval, permit issuance, inspections, and closeout. Those events have different meanings. A passed inspection, for example, does not by itself prove that a permit is closed or that a utility has granted permission to operate.

## Bring a CRM

The [CRM data guide](docs/crm-data.md) describes the common information needed to match a message to a permit. One deal can have several permits. Names support matching; they do not establish a match on their own.

For an optional, read-only Pipedrive inventory, put your API token in a private file outside the repository and run:

```sh
python3 -m solarbridge pipedrive-import --token-file /absolute/path/to/token --output private/pipedrive
```

An already-configured `PIPEDRIVE_API_TOKEN` environment variable is an alternative to `--token-file`. The command reads field definitions and organizations, resolves Building Department classification through metadata, and preserves available city/county information. It does not create fields, edit organizations, or reconcile deals. Read [Pipedrive field discovery](docs/pipedrive-field-discovery.md) for the mapping and its limits.

## Help improve coverage

You do not need to know Git or Python to contribute. Use the repository's **Issues → New issue → Jurisdiction knowledge** form to describe an official process, a missing step, or a changed portal. Include public source links and the date you checked them. Never attach a real inbox export, customer email, CRM screenshot, credential, or live permit link.

Technical contributors can add a profile, improve a parser, or turn a report into a synthetic test. Maintainers review evidence, check examples, and version accepted changes. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [profile guide](docs/jurisdiction-profiles.md).

Use **Issues → New issue → Learning feedback** when an exercise is unclear or a useful operator skill is missing. Documentation, teaching, and well-explained failure cases count as contributions.

## Next milestones

Our [roadmap](docs/roadmap.md) connects each technical milestone to a learning outcome and a release gate. First, validate a small AHJ workflow privately with experienced operators. Later stages cover supervised integrations, fair aggregate timeline reporting, separate utility workflows, and modernization partnerships with willing institutions.

Live inbox connections, AI-assisted extraction, scheduled monitoring, CRM writes, utility integrations, and government approval automation are not implemented. Government permitting and utility interconnection retain separate identifiers and decisions; neither process can stand in for the other.

## Learning and employer participation

We invite operators, technical mentors, employers, utilities, and local departments to help shape the project. Employers can propose funded training time, mentorship, or defined paid opportunities. There is no established apprenticeship, hiring guarantee, or partnership program in this release. Any future opportunity must state its funding, compensation, criteria, and limits. Public contributions are optional evidence of skill, not a requirement to perform unpaid production work for a speculative job.

## Start here

- [People-first charter](CHARTER.md)
- [Project governance](GOVERNANCE.md)
- [Competency-based learning path](docs/learning-path.md)
- [Roadmap and readiness gates](docs/roadmap.md)
- [No-install training examples](docs/training-preview.md)
- [Operator exercise and daily review](docs/operator-guide.md)
- [Event meanings and review boundaries](docs/event-model.md)
- [CRM fields and matching](docs/crm-data.md)
- [Jurisdiction profiles and official sources](docs/jurisdiction-profiles.md)
- [Private data and public examples](docs/data-handling.md)
- [Security reporting](SECURITY.md)

Code and original project documentation are available under the [MIT License](LICENSE). Third-party sources remain subject to their own terms.
