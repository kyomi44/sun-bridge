# Contributing

Permit operators, installers, reviewers, and developers can all improve Open Permit Kit. A clear correction with an official source can be as useful as a code change.

## Contribute without code

Open **Issues → New issue → Jurisdiction knowledge** in this repository. Supply the jurisdiction's full name and state, the permit type, the public source URL, when you checked it, and the change you observed. Explain separately how an application is submitted, how updates arrive, and how an operator can verify the result.

If your observation comes only from private work, describe the pattern in your own words and mark it as an observation requiring verification. Do not paste the message or include customer details. You can invent a short example with a fictional customer, fictional address, synthetic permit number, and a non-routable example link.

To report a parser problem, use **Synthetic parser example**. Include a minimal made-up message, its expected event, and why the current interpretation is wrong. No coding experience is required.

## Make a change

Keep each contribution focused: one jurisdiction change, one parser case, or one documentation improvement. Read the [profile guide](docs/jurisdiction-profiles.md), [event model](docs/event-model.md), and [data handling rules](docs/data-handling.md) before adding examples.

From the repository folder, check your changes with:

```sh
python3 -m permitkit validate
python3 -m unittest discover -s tests -v
python3 -m permitkit demo
```

Inspect the demo report as well as the command results. A technically valid output can still misrepresent what a permit message means. In the pull request, identify the source, describe the behavior before and after, and explain how you checked it.

## How contributions become trusted

Maintainers verify public sources and geographic scope, review synthetic examples, and check that matching and event meanings remain conservative. A process supported by documentation may be recorded as documented while its parser remains experimental. Missing evidence stays unknown.

A parser change should demonstrate the intended event and at least one easily confused case, such as an issued permit versus an issued invoice, or final inspection scheduling versus final inspection completion. Maintainers record profile changes in version history and update the date sources were checked. A passing synthetic test does not establish real-world accuracy or complete notification coverage.

Profiles can become stale when an AHJ changes its portal, template, or process. Report the change and its observed date. Maintainers should narrow or suspend unsupported claims until they are checked again.

## Public contribution boundaries

Use only original text, authorized contributions, public source links, and synthetic fixtures. Do not contribute real mailboxes, email bodies, attachments, customer names or addresses, real permit identifiers, deal IDs, organization exports, portal tokens, or credentials. Removing a name alone does not make a message anonymous. Follow [SECURITY.md](SECURITY.md) if private information was exposed.

By contributing, you agree that your original contribution may be distributed under the project's [MIT License](LICENSE). Be respectful and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
