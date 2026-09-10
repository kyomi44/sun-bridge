# Set up a local solar operations workspace

Start with a public catalog of AHJs, utilities, and historical solar timelines. Connect it to your organization records, then use private email and permit records to review operational updates. No command in this workflow writes to your CRM or makes a permitting decision.

Install Python 3.10 or newer if needed. Fork and clone the repository, or download its ZIP and unzip it. Open a terminal in that folder. No extra packages are required. On Windows, use `py -3` if `python3` is unavailable.

## 1. Initialize and inspect the public catalog

```sh
python3 -m sunbridge catalog init
python3 -m sunbridge catalog search --state FL --kind building_department --query "Cape Coral"
python3 -m sunbridge catalog show --id ENTITY_ID
```

Replace `ENTITY_ID` with an ID from search. Initialization reads the bundled public SolarTRACE data and creates `private/catalog/sunbridge.sqlite`; it requires no account, API key, or network request. The catalog is independent of a CRM connection.

Use a record's source, entity type, geography, and reporting period together. Historical medians are measured in business days for 2017–2024 installation cohorts; they are not current permit statuses, deadlines, service commitments, or a forecast for your project. Recheck requirements with the responsible authority before treating them as current instructions. A submission method is not evidence that email status notifications are available. Read the [source and methodology notes](solartrace-sources.md).

## 2. Export and reconcile organization knowledge

```sh
python3 -m sunbridge catalog export --state FL --output private/catalog-export
```

Export writes `organizations.json`, `benchmarks.json`, `requirements.json`, `source.json`, and `NOTICE.txt`. Use these records for your own analysis or a deliberately mapped CRM import. Preserve source attribution and the notice when redistributing source-derived data; the data are not relicensed under the software's MIT license.

Prepare `private/organizations.json` as an array using this format. This example is fictional; replace it with your own organization records, not customer or deal records:

```json
[
  {
    "organization_id": "crm-example-1",
    "name": "Fictional County Building Department",
    "kind": "building_department",
    "state": "FL"
  }
]
```

Use `utility_company` for utility records. You may add a verified source `geo_id` for a building department or `eia_id` for a utility; preserve either identifier as an exact string, including leading zeros. Do not invent source IDs from names or copy a CRM organization's ID into those fields. The fictional row above is only a format example and is not expected to match a real entity.

```sh
python3 -m sunbridge catalog reconcile --organizations private/organizations.json --output private/catalog-reconciliation
```

Reconciliation suggests catalog links for operator review. Even an exact source-ID candidate requires inspection; a name candidate is never an automatic merge. Neither export nor reconciliation updates a CRM or establishes which authority serves a particular property. See the [catalog guide](catalog.md) for the complete workflow.

Keep the source's stable identifiers alongside your own organization's ID. Preserve AHJs and utilities as different entity types. Duplicate names, missing geography, and unclear service areas need verification, not a forced match. Catalog organization links and the permit-to-deal matching below answer different questions and must not be substituted for each other.

## 3. Try the email review flow

```sh
python3 -m sunbridge start --open
```

Expected result: a browser opens `private/demo/review.html` with fictional messages, proposed events, matching outcomes, and evidence. JSON and Markdown versions are beside it. There are no account connections or network requests. Repeating the command replaces only its generated reports. If browser opening is unavailable, open the HTML file manually.

Inspect the difference between application receipt, approval, and permit issuance. Find an ambiguous match and an unsupported message. The [operator guide](operator-guide.md) provides an optional exercise with expected results before evaluating private data.

## 4. Create a reusable private review workspace

```sh
python3 -m sunbridge setup --interactive
python3 -m sunbridge doctor
```

Choose the fictional demo, your own normalized JSON records, or Pipedrive. Without `--interactive`, setup defaults to the demo. The files live in `private/workspace/`:

- `sunbridge.json`: input paths, adapter choice, selected deals, output location, and a batch limit.
- `START-HERE.md`: your next steps and commands.
- `llm-config.json`: an inactive template, not a connection.
- `pipedrive-mapping.json`: created only for Pipedrive; replace its placeholders before use.

Setup never connects accounts, requests a key, or overwrites an existing nonempty workspace. For a second setup, use a different `--output`, then supply that configuration's path to doctor/run:

```sh
python3 -m sunbridge setup --crm pipedrive --output private/pipedrive-pilot
python3 -m sunbridge doctor --config private/pipedrive-pilot/sunbridge.json
```

Paths inside configuration are relative to the repository folder, not to the configuration file. Absolute input paths are accepted; outputs must stay below this clone's `private/`. Do not put literal credentials in JSON. Keep token files outside the repository and configure their paths, or use the documented environment variables.

## 5. Bring a small email sample from one verified authority

Keep an authorized EML/MBOX export under `private/`. Start with a few messages whose correct meanings you know. Choose the AHJ profile only after verifying the authority. This command assigns one profile to the whole import; do not use it on a mixed-jurisdiction inbox.

```sh
python3 -m sunbridge import-mail --input private/sample.eml --ahj PROFILE_ID --output private/mail
```

Replace `PROFILE_ID` with the exact ID of a loaded profile. See `profiles/` and the [profile guide](jurisdiction-profiles.md). If your authority is missing, contribute a sourced profile or create a private profile directory using the documented schema and set `profiles_path` accordingly. Standalone import commands do not read workspace configuration: also add `--profiles private/your-profiles` to `import-mail` (and to `pipedrive-deals` if using that standalone command). Do not borrow another city's profile to make a check pass.

Set `messages_path` to the generated `private/mail/messages.json`. Imports refuse to overwrite existing files; use a new output directory for a new batch and update the path. The guided run accepts at most 100 messages. Attachments are ignored. A sender's Date header is retained as an unverified claimed send time, never manufactured into receipt or event time. See [email import](email-import.md).

## 6. Prepare the CRM side

For **Pipedrive**, configure `PIPEDRIVE_API_TOKEN` in the running process or use a private token file. Read field metadata:

```sh
python3 -m sunbridge pipedrive-fields --token-file /absolute/path/to/your-token-file --output private/deal-fields
```

With an environment variable already configured, omit `--token-file`. Inspect the private field-code list, then edit the workspace's `pipedrive-mapping.json`. Map the actual AHJ reference, permit-number fields, full service address, and optional customer display field. Map exact stored AHJ IDs to profile IDs; labels and postal cities are not enough. Do not assume the deal's primary organization is its building department.

In `sunbridge.json`, set `crm.deal_ids` to a small explicit selection, and set `crm.token_file` to your private file path or leave it `null` for the environment variable. No whole-account deal search occurs. The [selected-deal guide](pipedrive-deals.md) explains supported field types, multiple permit fields, and skipped-record issues. Organization discovery remains a separate optional inventory, not automatic jurisdiction mapping.

For **another CRM**, use `json_file` and create a private array in the format shown in [examples/permits.json](../examples/permits.json). Point `crm.permits_path` at it. This is a deliberate data transformation, not native support for that product. The [CRM matrix](crm-integrations.md) explains contribution targets.

Required matching context: an explicit deal ID, verified AHJ, permit/application identifier where available, and full project service address including unit. Customer names are supporting display information, not a matching key. Preserve separate permits; do not merge their decisions into one status without review.

## 7. Choose rules or an optional model

With `llm_config_path: null`, no LLM is called. Only the fictional profile currently has an enabled rule parser; real profiles will hold unsupported messages as unknown.

To evaluate model extraction, edit the private LLM template with a compatible endpoint, exact model, and key environment-variable name. Follow [model setup and privacy](llm-providers.md), including its fictional connection check. Set `llm_config_path` in `sunbridge.json` to that private configuration only when you intend to use it.

The model receives the selected sender, subject, entire plain-text body, and assigned authority name/ID—not the CRM roster. The body may contain customers and quoted history. Check organizational authorization and provider terms first. Every enabled run requires an explicit flag and may cost money:

```sh
python3 -m sunbridge doctor --config private/pipedrive-pilot/sunbridge.json
python3 -m sunbridge run --config private/pipedrive-pilot/sunbridge.json --allow-llm-data-transfer --open
```

Without a model, omit `--allow-llm-data-transfer`. A successful doctor check means configuration readiness, not a tested credential, complete channel coverage, or reliable extraction. No model/provider has been live-certified by the project. A failed model request is held for review, not silently replaced with a different provider or interpretation.

## 8. Inspect evidence and resolve exceptions

Open the generated HTML. Review CRM import issues first, then inspect the original subject/body, cited evidence, proposed event and scope, identifier/address, matching candidates, duplicates, and warnings. Distinguish event extraction errors from record-matching errors. Do not treat a match or a passed synthetic test as approval to change a deal.

Record pilot decisions in your existing private process; this release has no saved approve/reject workflow. Verify any real operational change independently through your authorized process. The report is not an official status source or a complete audit log.

To keep proposed event evidence alongside catalog entities, prepare `private/catalog-links.json` as an object mapping each reviewed AHJ profile ID to its verified catalog entity ID. Then attach the review report:

```sh
python3 -m sunbridge catalog attach-review --report private/workspace/review/review.json --links private/catalog-links.json
```

Use your actual report path if you chose a different workspace. Attachment stores proposed evidence privately; it does not accept an event, rewrite a source benchmark, establish a current status, or update a CRM. The [catalog guide](catalog.md) explains link preparation and the evidence boundary.

Before expanding the pilot, use unseen cases, measure errors and abstentions separately, and identify a responsible reviewer. Share only synthetic regressions, public process knowledge, and code. Do not share the workspace, reports, tokens, or customer records with a public fork or issue.

## Common setup problems

| Symptom | Next step |
| --- | --- |
| Python/module not found | Check the Python version and open the terminal in the extracted repository folder. Run from the checkout. |
| Setup directory already exists | Use the existing config, or choose a new `--output`; setup does not erase your previous work. |
| Doctor needs attention | Check the named input/mapping step above. Doctor is offline; it cannot verify a live credential or actual remote field availability. |
| No event is recognized | Check the assigned profile and parser coverage; a sourced profile does not imply an enabled parser. Optional LLM extraction needs explicit setup and evaluation. |
| No match or several candidates | Inspect AHJ mapping, permit identifiers, full addresses/units, and multiple permits. Never force a match using a customer name alone. |
| A provider rejects the request | Check its model ID, supported protocol/role/token parameter, credential, and availability. No automatic model fallback or retry occurs. |
| Imported timestamp is missing | EML Date is not a receipt time. Keep the warning and obtain verified timing from an appropriate source if needed. |

For learning questions, open a Learning feedback issue with fictional examples only. Security or exposure concerns follow [SECURITY.md](../SECURITY.md).
