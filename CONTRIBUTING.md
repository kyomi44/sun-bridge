# Contributing

Permit operators, installers, reviewers, mentors, and developers can all improve Sun Bridge. A clear correction with an official source can be as useful as a code change. Start with the [charter](CHARTER.md) and [governance guide](GOVERNANCE.md): the project's primary goal is people gaining the skills and authority to shape automated work.

## Contribute without code

Open **Issues → New issue → Jurisdiction knowledge** in this repository. Supply the jurisdiction's full name and state, the permit type, the public source URL, when you checked it, and the change you observed. Explain separately how an application is submitted, how updates arrive, and how an operator can verify the result.

If your observation comes only from private work, describe the pattern in your own words and mark it as an observation requiring verification. Do not paste the message or include customer details. You can invent a short example with a fictional customer, fictional address, synthetic permit number, and a non-routable example link.

To report a parser problem, use **Synthetic parser example**. Include a minimal made-up message, its expected event, and why the current interpretation is wrong. No coding experience is required.

Use **Learning feedback** to improve an exercise, explain an accessibility barrier, or propose a missing skill. The [learning path](docs/learning-path.md) offers practical ways to demonstrate progress; there is no requirement to become a programmer before contributing. Share no private employment, customer, or CRM details.

## Make a change

For a CRM connection, start with **CRM integration** and the [adapter contract](docs/crm-integrations.md). For a model connection, read the [provider protocol and privacy boundaries](docs/llm-providers.md). A manifest or API key alone is not an integration: contribute a narrow implementation, private mapping/setup, offline tests, documented limits, and an operator learning outcome. Keep planned integrations distinct from tested capabilities.

Keep each contribution focused: one jurisdiction change, one parser case, or one documentation improvement. Read the [profile guide](docs/jurisdiction-profiles.md), [event model](docs/event-model.md), and [data handling rules](docs/data-handling.md) before adding examples.

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

Use only original text, authorized contributions, public source links, and synthetic fixtures. Do not contribute real mailboxes, email bodies, attachments, customer names or addresses, real permit identifiers, deal IDs, organization exports, portal tokens, or credentials. Removing a name alone does not make a message anonymous. Follow [SECURITY.md](SECURITY.md) if private information was exposed.

By contributing, you agree that your original contribution may be distributed under the project's [MIT License](LICENSE). Be respectful and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
