# Sun Bridge

Helping people learn to understand, supervise, and improve increasingly automated work—starting with residential solar.

Sun Bridge is an open-source learning and operations project. Operators contribute permitting knowledge and evaluate the evidence; technical teams build reusable connections and tests. **Empowering people is the primary goal.** Software is a way to build capability and agency, not a promise of job security or a substitute for the people doing the work.

## Start in five minutes

You need **Python 3.10 or newer**. No extra Python packages, account, API key, or customer data are needed for the demo.

Fork this repository on GitHub if you want to contribute, then clone your fork. To try the original:

```sh
git clone https://github.com/kyomi44/sun-bridge.git
cd sun-bridge
python3 -m sunbridge start --open
```

Or use **Code → Download ZIP**, unzip it, and open a terminal in the extracted folder. On Windows, use `py -3` in place of `python3` if needed. Run commands from that folder; a standalone installed-package distribution is not supported yet.

The command opens a private, browser-readable review of fictional emails and permit records. It also saves Markdown and JSON under `private/demo/`. No CRM is changed, no AI service is called, and nothing is hosted or uploaded. Omit `--open` on a machine without a browser and open `private/demo/review.html` yourself.

Not ready for a terminal? Start with the [no-install training cases](docs/training-preview.md), then pair with a technical helper on the [operator exercise](docs/operator-guide.md).

## Bring your own workflow

```sh
python3 -m sunbridge setup --interactive
python3 -m sunbridge doctor
python3 -m sunbridge run --open
```

Setup creates a private configuration and a `START-HERE.md`; it does **not** connect accounts. The demo choice runs immediately. A real-data choice needs your email sample, field mapping, and selected records first. `doctor` checks readiness offline and tells you what still needs attention.

Follow the [getting-started guide](docs/getting-started.md) for the complete path: import local email → prepare CRM records → optionally configure a model → inspect a proposed event and match. Every event still requires a person's review.

## What works today

This is a **developer pilot**, not a production-certified permitting agent.

| Capability | Current scope |
| --- | --- |
| Local review | Synthetic demo, guided setup, offline readiness checks, and private HTML/Markdown/JSON reports. |
| Email import | Local EML files or MBOX samples; no live inbox connection or attachment extraction. |
| CRM-neutral input | Documented JSON permit records; other CRM exports must be deliberately transformed into this format. |
| Pipedrive | Read-only organization discovery, deal-field discovery, and imports of explicitly selected deals using account-specific mappings. New deal reads are mock-tested, not live-certified. |
| Optional model | Experimental, opt-in OpenAI-compatible Chat Completions extraction, including compatible loopback servers. No provider/model is live-certified. |
| Jurisdiction knowledge | Cape Coral and Lee County have sourced profiles; their rule parsers remain disabled. A fictional training profile has a working subject parser. |

Rules recognize supported **subjects**, not arbitrary email bodies. Optional model extraction can examine subject/body text even when a profile's rule parser is disabled, but that does not validate the profile, authenticate a sender, or establish accuracy. Ambiguous and unsupported messages remain unknown.

Submission confirmation, corrections, approval, issuance, inspections, and closeout are distinct events. A customer name alone never establishes a CRM match. AHJ plus a unique permit identifier or an exact, complete service address provides a candidate for review; multiple permits and conflicts remain visible.

There are **no CRM writes, saved approve/reject controls, scheduled monitors, live inbox subscriptions, utility connectors, or autonomous government approvals** in this release.

## Supported CRMs and model connections

Run `python3 -m sunbridge integrations` or read the [CRM support matrix](docs/crm-integrations.md). Support is capability-specific: a read adapter is not a complete two-way integration.

Pipedrive is the first native read adapter. HubSpot, Salesforce, and Zoho are contribution targets, **not working native connectors**. The [adapter template](templates/crm-adapter.json), normalized input contract, synthetic tests, and CRM contribution issue form give other teams a concrete starting point.

A provider's API key alone does not make its API compatible. Choose a supported protocol, endpoint, exact model, and credential reference. See [model connections and data transfer](docs/llm-providers.md). The model receives selected email content only after explicit authorization; it never receives the CRM roster or chooses which deal to update.

## People are the point

The [charter](CHARTER.md), [governance](GOVERNANCE.md), and [learning path](docs/learning-path.md) keep operator judgment, accessible learning, and accountability central. The adopted charter and governance retain the previous name until their documented amendment process completes; their commitments apply unchanged to Sun Bridge.

Contributing can mean explaining a department's process, improving an exercise, identifying a failure, teaching someone, or writing an adapter. Do not assume someone's ability to learn from their age, background, or job title.

Employers can propose funded learning time, mentorship, and defined paid opportunities. No hiring guarantee, apprenticeship, or partnership program is established in this release. Public contributions should not become unpaid production work performed for a speculative job.

## Invite another team to contribute

Ask a team to run the fictional demo, pair an operator with a technical helper, and contribute **one scoped improvement**:

- A sourced jurisdiction correction or newly invented parser example.
- A read-only CRM adapter with explicit mapping, private outputs, and offline tests.
- A model-protocol adapter with consent, grounded output validation, and no tools or write authority.
- An easier exercise or evidence-review explanation.

Use the issue templates and [contribution guide](CONTRIBUTING.md). Never upload real inbox archives, CRM exports, customer information, live permit links, tokens, or private configuration. Review [data handling](docs/data-handling.md) before using real data.

Check a contribution from the repository folder:

```sh
python3 -m sunbridge validate
python3 -m unittest discover -s tests -v
python3 scripts/check_public_files.py --tracked
```

## Where this can go

First, privately validate one narrow AHJ workflow with experienced operators. Later gates cover saved review decisions, authorized CRM updates, reliable monitoring, fair aggregate timelines, separate utility workflows, and collaboration with willing public institutions. Each step must advance the skills and controls needed to supervise it. See the [roadmap](docs/roadmap.md) and [pilot decision record](docs/decisions/0001-forkable-pilot.md).

Sun Bridge is a working name, formerly Solar Bridge and Open Permit Kit—not a naming-clearance or affiliation claim. Old `solarbridge` and `permitkit` commands still work. See [name and compatibility notes](docs/project-name.md).

Original code and documentation are [MIT-licensed](LICENSE). Third-party sources retain their own terms.
