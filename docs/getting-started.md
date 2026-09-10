# From a fresh fork to a reviewed permit update

Start with fictional data. Then pair an experienced permit operator with a technical helper for a small private pilot. This release produces a review report; it does not save approvals, change a CRM, or watch an inbox.

## 1. Get a working example

Install Python 3.10 or newer if needed. Fork and clone the repository, or download its ZIP and unzip it. Open a terminal in that folder. No extra packages are required. On Windows, use `py -3` if `python3` is unavailable.

```sh
python3 -m sunbridge start --open
```

Expected result: a browser opens `private/demo/review.html` with fictional messages, proposed events, matching outcomes, and evidence. JSON and Markdown versions are beside it. There are no account connections or network requests. Repeating the command replaces only its generated reports. If browser opening is unavailable, open the HTML file manually.

Have the operator explain the difference between application receipt, approval, and permit issuance. Find an ambiguous match and an unsupported message together. The [operator guide](operator-guide.md) supplies an exercise and expected results.

## 2. Create a reusable private workspace

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

## 3. Bring a small email sample from one verified authority

Keep an authorized EML/MBOX export under `private/`. Start with a few messages whose correct meanings you know. Choose the AHJ profile only after verifying the authority. This command assigns one profile to the whole import; do not use it on a mixed-jurisdiction inbox.

```sh
python3 -m sunbridge import-mail --input private/sample.eml --ahj PROFILE_ID --output private/mail
```

Replace `PROFILE_ID` with the exact ID of a loaded profile. See `profiles/` and the [profile guide](jurisdiction-profiles.md). If your authority is missing, contribute a sourced profile or create a private profile directory using the documented schema and set `profiles_path` accordingly. Standalone import commands do not read workspace configuration: also add `--profiles private/your-profiles` to `import-mail` (and to `pipedrive-deals` if using that standalone command). Do not borrow another city's profile to make a check pass.

Set `messages_path` to the generated `private/mail/messages.json`. Imports refuse to overwrite existing files; use a new output directory for a new batch and update the path. The guided run accepts at most 100 messages. Attachments are ignored. A sender's Date header is retained as an unverified claimed send time, never manufactured into receipt or event time. See [email import](email-import.md).

## 4. Prepare the CRM side

For **Pipedrive**, configure `PIPEDRIVE_API_TOKEN` in the running process or use a private token file. Read field metadata:

```sh
python3 -m sunbridge pipedrive-fields --token-file /absolute/path/to/your-token-file --output private/deal-fields
```

With an environment variable already configured, omit `--token-file`. Inspect the private field-code list, then edit the workspace's `pipedrive-mapping.json`. Map the actual AHJ reference, permit-number fields, full service address, and optional customer display field. Map exact stored AHJ IDs to profile IDs; labels and postal cities are not enough. Do not assume the deal's primary organization is its building department.

In `sunbridge.json`, set `crm.deal_ids` to a small explicit selection, and set `crm.token_file` to your private file path or leave it `null` for the environment variable. No whole-account deal search occurs. The [selected-deal guide](pipedrive-deals.md) explains supported field types, multiple permit fields, and skipped-record issues. Organization discovery remains a separate optional inventory, not automatic jurisdiction mapping.

For **another CRM**, use `json_file` and create a private array in the format shown in [examples/permits.json](../examples/permits.json). Point `crm.permits_path` at it. This is a deliberate data transformation, not native support for that product. The [CRM matrix](crm-integrations.md) explains contribution targets.

Required matching context: an explicit deal ID, verified AHJ, permit/application identifier where available, and full project service address including unit. Customer names are supporting display information, not a matching key. Preserve separate permits; do not merge their decisions into one status without review.

## 5. Choose rules or an optional model

With `llm_config_path: null`, no LLM is called. Only the fictional profile currently has an enabled rule parser; real profiles will hold unsupported messages as unknown.

To evaluate model extraction, edit the private LLM template with a compatible endpoint, exact model, and key environment-variable name. Follow [model setup and privacy](llm-providers.md), including its fictional connection check. Set `llm_config_path` in `sunbridge.json` to that private configuration only when you intend to use it.

The model receives the selected sender, subject, entire plain-text body, and assigned authority name/ID—not the CRM roster. The body may contain customers and quoted history. Check organizational authorization and provider terms first. Every enabled run requires an explicit flag and may cost money:

```sh
python3 -m sunbridge doctor --config private/pipedrive-pilot/sunbridge.json
python3 -m sunbridge run --config private/pipedrive-pilot/sunbridge.json --allow-llm-data-transfer --open
```

Without a model, omit `--allow-llm-data-transfer`. A successful doctor check means configuration readiness, not a tested credential, complete channel coverage, or reliable extraction. No model/provider has been live-certified by the project. A failed model request is held for review, not silently replaced with a different provider or interpretation.

## 6. Review with the person who knows the work

Open the generated HTML. Review CRM import issues first, then inspect the original subject/body, cited evidence, proposed event and scope, identifier/address, matching candidates, duplicates, and warnings. Distinguish event extraction errors from record-matching errors. Do not treat a match or a passed synthetic test as approval to change a deal.

Record pilot decisions in your existing private process; this release has no saved approve/reject workflow. Verify any real operational change independently through your authorized process. The report is not an official status source or a complete audit log.

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
