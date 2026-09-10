# Contributing

Improve the shared jurisdiction and utility data, add a reliable read adapter, or make permit review more accurate. A clear correction with an official source can be as useful as a code change. Operators, installers, public-agency staff, reviewers, and developers are welcome.

The [charter](CHARTER.md) and [governance guide](GOVERNANCE.md) keep operator authority, privacy, and accessible participation central to the work.

## Improve catalog data

Keep public catalog knowledge separate from private CRM mappings and live project records. Use a focused issue or pull request to identify a source record, describe the discrepancy, link the supporting public evidence, and state when it was checked. Verify the source's reuse terms before contributing data; the repository's code license does not automatically license a third-party dataset.

Preserve source identifiers, entity type, geography, reporting period, units, and missing values. An AHJ and a utility with similar names are not the same organization. A postal city is not a jurisdiction boundary. Historical median timelines are not current service commitments, and submission methods do not prove notification coverage. See the [source notes](docs/solartrace-sources.md).

For a source update or normalization change, add tests that cover both intended matches and similar records that must stay separate. Describe how the change affects existing local mappings. Never replace historical observations or unresolved identity questions with an unsupported guess.

## Contribute without code

Open **Issues → New issue → Jurisdiction knowledge** in this repository. Supply the jurisdiction's full name and state, the permit type, the public source URL, when you checked it, and the change you observed. Explain separately how an application is submitted, how updates arrive, and how an operator can verify the result.

If your observation comes only from private work, describe the pattern in your own words and mark it as an observation requiring verification. Do not paste the message or include customer details. You can invent a short example with a fictional customer, fictional address, synthetic permit number, and a non-routable example link.

To improve the [email milestone coverage charts](docs/email-coverage.md), follow the [coverage contribution guide](docs/email-coverage-methodology.md). Contribute presence-only observations, keep candidate wording separate from exact pilot milestones, and regenerate the checked-in charts. Do not publish traffic volumes or promote an observed proposal into a validated integration.

To report a parser problem, use **Synthetic parser example**. Include a minimal made-up message, its expected event, and why the current interpretation is wrong. No coding experience is required.

Use **Learning feedback** to improve an exercise, explain an accessibility barrier, or propose a missing skill. The [learning path](docs/learning-path.md) offers practical ways to demonstrate progress; there is no requirement to become a programmer before contributing. Share no private employment, customer, or CRM details.

## Make a change

For a CRM connection, start with **CRM integration** and the [adapter contract](docs/crm-integrations.md). For a model connection, read the [provider protocol and privacy boundaries](docs/llm-providers.md). A manifest or API key alone is not an integration: contribute a narrow implementation, private mapping/setup, offline tests, documented limits, and a clear operator benefit. Keep planned integrations distinct from tested capabilities.

Keep each contribution focused: one data correction, one parser case, one adapter capability, or one documentation improvement. Read the [profile guide](docs/jurisdiction-profiles.md), [event model](docs/event-model.md), and [data handling rules](docs/data-handling.md) before adding examples.

From the repository folder, check your changes with:

```sh
python3 -m sunbridge validate
python3 -m unittest discover -s tests -v
python3 -m sunbridge demo
```

Inspect the demo report as well as the command results. A technically valid output can still misrepresent what a permit message means. In the pull request, identify the source, describe the behavior before and after, and explain how you checked it.

Explain the human outcome too: what can an operator learn, inspect, challenge, or decide because of the change? For workflow or automation changes, document affected authority, evidence, failure handling, and the relevant [roadmap gate](docs/roadmap.md). Seek an experienced operator's review; if that perspective is unavailable, say so and do not claim the workflow is operationally validated.

Before committing, stage only the intended public files and run `python3 scripts/check_public_files.py --tracked`. Inspect the staged diff manually as well; the checker is a guardrail, not anonymization.

## How contributions become trusted

Maintainers verify public sources and geographic scope, review synthetic examples, and check that matching and event meanings remain conservative. A process supported by documentation may be recorded as documented while its parser remains experimental. Missing evidence stays unknown.

A parser change should demonstrate the intended event and at least one easily confused case, such as an issued permit versus an issued invoice, or final inspection scheduling versus final inspection completion. Maintainers record profile changes in version history and update the date sources were checked. A passing synthetic test does not establish real-world accuracy or complete notification coverage.

Profiles can become stale when an AHJ changes its portal, template, or process. Report the change and its observed date. Maintainers should narrow or suspend unsupported claims until they are checked again.

## Public contribution boundaries

Use only original text, authorized contributions, appropriately licensed public source data, and synthetic message fixtures. Do not contribute real mailboxes, email bodies, attachments, customer names or addresses, real permit identifiers, deal IDs, private CRM organization exports, portal tokens, or credentials. Removing a name alone does not make a message anonymous. Follow [SECURITY.md](SECURITY.md) if private information was exposed.

By contributing, you agree that your original contribution may be distributed under the project's [MIT License](LICENSE). Be respectful and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
