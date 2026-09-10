# Open Permit Kit

Learn to review permitting communications, connect them to the right project, and maintain reusable knowledge about local permitting offices.

Open Permit Kit is a community toolkit for permit operators and their technical helpers. It combines jurisdiction profiles, synthetic examples, a local review tool, and practical guides. Operators can contribute what they know without writing code, inspect the evidence behind a proposed event, and decide when follow-up is needed.

This first version is experimental. The included examples are synthetic; no profile or parser is certified for production. The tool generates a review preview and does not update a CRM, submit permits, or monitor a live inbox.

The working parser uses explicit rules, not an AI service, to recognize supported subject formats in the fictional training profile. It does not extract events from email bodies or attachments. Cape Coral and Lee County have sourced capability profiles, but no enabled email parsers yet. All proposed events require operator review; a sender allowlist does not authenticate a message.

## Try it in 20 minutes

**No installation:** start with the [browser-only training page](docs/training-preview.md). Read five made-up cases, explain your decisions, and compare them with the answers. A technical helper can set up the working demo when you are ready.

For the working demo, you need Python 3.10 or newer. There are no external Python dependencies. Download and unzip this repository using **Code → Download ZIP**, or clone it:

```sh
git clone https://github.com/kyomi44/open-permit-kit.git
cd open-permit-kit
```

Open a terminal in the repository folder, then run:

```sh
python3 -m permitkit demo
```

Open `private/demo/review.md` to read the result. `private/demo/review.json` contains the structured preview. Work through the [20-minute operator exercise](docs/operator-guide.md) to practice identifying receipt, corrections, issuance, and inspection events.

To validate the shipped data and run the tests:

```sh
python3 -m permitkit validate
python3 -m unittest discover -s tests -v
```

To run the same review process explicitly:

```sh
python3 -m permitkit analyze --messages examples/messages.json --permits examples/permits.json --output private/my-review
```

Keep real messages and CRM exports under `private/` on your own computer. They are private working data, never public examples. See [data handling](docs/data-handling.md) before using your own inputs.

## What is in the kit?

| Component | Purpose |
| --- | --- |
| Jurisdiction profiles | Record official sources, geographic scope, submission methods, notification channels, and ways to verify a status. |
| Synthetic messages and permits | Practice matching and interpretation without sharing a customer's records. |
| Review preview | Show candidate events and matches for an operator to inspect. |
| Operator and contributor guides | Explain decisions, common failure cases, and how to improve coverage. |
| Optional Pipedrive discovery | Read field metadata and a Building Department organization roster into private local files. |

The project distinguishes application receipt, plan review, corrections, approval, permit issuance, inspections, and closeout. Those events have different meanings. A passed inspection, for example, does not by itself prove that a permit is closed or that a utility has granted permission to operate.

## Bring a CRM

The [CRM data guide](docs/crm-data.md) describes the common information needed to match a message to a permit. One deal can have several permits. Names support matching; they do not establish a match on their own.

For an optional, read-only Pipedrive inventory, put your API token in a private file outside the repository and run:

```sh
python3 -m permitkit pipedrive-import --token-file /absolute/path/to/token --output private/pipedrive
```

An already-configured `PIPEDRIVE_API_TOKEN` environment variable is an alternative to `--token-file`. The command reads field definitions and organizations, resolves Building Department classification through metadata, and preserves available city/county information. It does not create fields, edit organizations, or reconcile deals. Read [Pipedrive field discovery](docs/pipedrive-field-discovery.md) for the mapping and its limits.

## Help improve coverage

You do not need to know Git or Python to contribute. Use the repository's **Issues → New issue → Jurisdiction knowledge** form to describe an official process, a missing step, or a changed portal. Include public source links and the date you checked them. Never attach a real inbox export, customer email, CRM screenshot, credential, or live permit link.

Technical contributors can add a profile, improve a parser, or turn a report into a synthetic test. Maintainers review evidence, check examples, and version accepted changes. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [profile guide](docs/jurisdiction-profiles.md).

## Next milestones

Start with one jurisdiction and privately verify representative submission, correction, issuance, and inspection examples. Add a narrowly scoped parser and synthetic regression cases only after checking the original evidence. Measure event accuracy and project-match accuracy separately; a correct event on the wrong deal is still a failure.

Live inbox connections, optional AI-assisted extraction, operator feedback storage, scheduled monitoring, and approved CRM updates are future work. Any AI-assisted proposal should retain its evidence, be able to abstain, and pass the same review and matching checks. This starter does not make an unattended permitting decision.

## Start here

- [No-install training examples](docs/training-preview.md)
- [Operator exercise and daily review](docs/operator-guide.md)
- [Event meanings and review boundaries](docs/event-model.md)
- [CRM fields and matching](docs/crm-data.md)
- [Jurisdiction profiles and official sources](docs/jurisdiction-profiles.md)
- [Private data and public examples](docs/data-handling.md)
- [Security reporting](SECURITY.md)

Code and original project documentation are available under the [MIT License](LICENSE). Third-party sources remain subject to their own terms.
