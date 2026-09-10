# Reading and contributing email coverage

The [coverage charts](email-coverage.md) answer two different questions: which AHJs appear to send useful permitting emails, and which specific milestones have produced proposals in a private pilot. They do not certify an integration or turn on an automated CRM update.

## What the marks mean

| Mark | Evidence | What it does not mean |
| --- | --- | --- |
| Pilot observed | A body-aware experimental rule produced that specific event proposal during a private historical review. | Human-validated accuracy, authenticated sender, correct current project status, a published parser, or permission to update a CRM. |
| Candidate signal | Historical email subjects contained wording associated with a broad permitting family. | A consistently parseable template, an exact milestone, a usable project identifier, or complete notification coverage. |
| Not demonstrated | This review did not establish the claim. | The AHJ never sends the notice or cannot support an integration. |

The pilot and candidate charts are deliberately separate. Body text can establish a proposed milestone even when the subject screen misses it. In the current observations, Charlotte County has receipt and action-required pilot evidence despite no matching subject-family flags. Do not require a subject flag before recording independently reviewed body-level evidence.

Private pilot proposals were evaluated with AI-produced challenge labels and synthetic safety tests, not operator-approved ground truth. Reusing those labels after changes is regression testing, not fresh acceptance evidence. These observations remain experimental and historical. The registry review date identifies when the summary was reviewed; it does not certify current email behavior.

## Preserve milestone meanings

| Family or event | Keep separate |
| --- | --- |
| Submission | Sent, received, and accepted. Receipt can acknowledge an application or newly supplied documents. |
| Review / corrections | Review activity, requests for information, incomplete intake, and terminal denial. |
| Approval | Stamped-plan approval, a review-step approval, and the final permit disposition. |
| Issuance | An issued permit, an issued certificate, an invoice, and readiness to issue. |
| Inspection | Scheduling, an individual inspection result, and final permit closure. |
| Payment | An invoice, fees due, and money actually received. |
| Expiration | A future-expiration warning and an explicitly expired permit. |

Expiry was not a family in the broad subject screen. It appears only where the private pilot produced an explicit expired-permit proposal. Utility permission to operate and permit closure are not established by an inspection pass.

## Identity and scope

AHJ names are provisional display groups, not jurisdiction boundaries or accepted CRM/catalog crosswalks. Similar historical domains or sender spellings can be grouped for this overview without merging operational organizations. The registry's identity note makes these cases visible:

- `historical_domain_aliases`: multiple historical domain-name variants; official equivalence is not certified here.
- `sender_spelling_variant`: sender-name spelling variants grouped for display.
- `cross_platform_identity`: direct and shared-platform labels grouped provisionally.
- `provisional_office_grouping`: offices shown under a jurisdiction heading; preserve their separate roles and routes. In particular, a county clerk and a building department are not interchangeable organizations.
- `unusual_domain_alias`: an unusual domain spelling needs identity review; do not authorize a sender from this label.
- `none`: no special grouping note, not a claim of verified identity.

Unresolved vendor tenants and payment processors do not become AHJs. A shared vendor name alone cannot identify the responsible agency. City and county names must remain separate. The list is a historical review scope, not an exhaustive national directory, and absence is not evidence of incompatibility.

## Propose catalog links for review

Registry entries carry names, not catalog entity IDs. To find the catalog rows a name could refer to, run the read-only proposal command from the repository root after `catalog init`:

```sh
python3 -m sunbridge catalog reconcile-coverage --state FL --output private/coverage-reconciliation
```

The private `review.json` lists one item per registry entry:

| Status | Meaning | What it does not mean |
| --- | --- | --- |
| `single_candidate` | Exactly one building department in the catalog shares the name within the state hint. | A verified identity, a jurisdiction boundary, or an operational sender. |
| `ambiguous` | Several catalog rows share the name within the state hint. Every candidate is listed; none is selected. | That the entry is unusable; a reviewer chooses or splits it. |
| `unmatched` | No catalog row shares the name within the state hint. Out-of-state candidates are listed separately when they exist. | That the AHJ does not exist or never sends notices; the catalog is not a complete registry. |

Three match methods are reported. `exact_name` normalizes only case and whitespace, the same rule the organization reconciliation uses. `place_name` additionally removes one trailing Census municipal form from the catalog side, so that `Cape Coral` can reach `Cape Coral city`. `county_name` removes a trailing `County` or `Parish`, so that `Miami-Dade` can reach `Miami-Dade County`; it also means a bare place name surfaces a county of the same name, which the reviewer must rule in or out. Registry names are never shortened except for a leading `Village of` / `City of` / `Town of` / `County of` prefix, which is retained as `registry_legal_form` and compared against the candidate's form. A trailing `, XX` state code in a registry name is the only state read from the name; `--state` supplies a default for the rest.

Issue codes explain the result: `state_not_specified_all_states_searched`, `candidates_only_in_other_states`, `no_catalog_candidate`, `candidate_identity_unresolved_in_source`, `registry_legal_form_differs_from_catalog`, and `registry_identity_note_*`, which repeats the registry's own identity note so provisional groupings are not silently linked.

Treat the output as a worksheet. Confirm the jurisdiction and the sending office from official sources before writing a link into a private profile-to-catalog crosswalk for `catalog attach-review`. The command does not modify the registry, the catalog, a profile, a chart, or a CRM, and this document does not publish any resulting links; a reviewed crosswalk remains an operator's private decision until a sourced profile records it.

## Public data boundary

[The registry](../coverage/ahj-email-signals.json) contains agency labels, display-only identifiers, qualitative identity notes, and presence-only signal/event arrays. It contains no email volumes, percentages, rankings, customer information, real permit numbers, deal IDs, CRM organization IDs, sender addresses, source message text, private file paths, or mailbox fingerprints. The charts contain no hidden business metrics or embedded private dataset. Dates and SVG layout coordinates are presentation/provenance values, not operational volumes.

The public generator reads only this reviewed registry. It does not open a mailbox, connect to a CRM, or publish private pilot rules. Capability flags cannot configure trusted senders, establish a catalog link, or enable a parser. Existing real-AHJ parsers remain disabled.

## Contribute a narrow observation

For an AHJ addition or correction, propose a small change to the registry and explain the agency identity, the observed meaning, the review date, and the limits. Use original wording and synthetic examples. Never attach real customer emails or reveal traffic volumes to justify a mark.

For example, a hypothetical candidate-only contribution would look like this:

```json
{
  "id": "example-county",
  "name": "Example County",
  "candidate_signals": ["inspection"],
  "pilot_events": [],
  "identity_note": "none"
}
```

Only add a `pilot_events` value when an independently reviewed private evaluation supports that exact proposed event. Identify whether the evaluator was an operator or AI; do not turn an observation into a validation claim. Test easily confused notices and retain private evidence in the contributor's own authorized environment. A public source can support general notification behavior without proving an exact email template.

After editing the registry, regenerate and verify the public charts from the repository root:

```sh
python3 scripts/render_email_coverage.py
python3 scripts/render_email_coverage.py --check
python3 -m unittest discover -s tests -v
```

The [schema](../schemas/email-signal-coverage.schema.json) and strict validator reject undeclared fields, including ad hoc metrics or message payloads. Maintainers must still review every public name and observation: a schema is not an anonymizer or an evidence review. Update generated files together; CI rejects stale charts. Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for the broader evidence and privacy requirements.

Before operational use, separately verify current sender/tenant identity, service address and permit matching, milestone-to-field meanings, chronology, duplicate handling, and operator approval. Those gates are not satisfied by a mark on a chart.
