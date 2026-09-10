# Read selected Pipedrive deals

This optional adapter reads only the deal IDs you explicitly select and projects mapped fields into the permit-record format used by Sun Bridge. It does not list all deals, fetch contacts, notes or email, or update Pipedrive. It requires Python 3.10 or newer and runs from the clone.

First discover your account's deal field codes:

```sh
python3 -m sunbridge pipedrive-fields --output private/deal-fields
```

Use an already configured `PIPEDRIVE_API_TOKEN`, or add `--token-file /absolute/path/to/your-token-file` to either command. Keep credentials outside the repository. Field discovery writes `private/deal-fields/fields.json`, containing each field's code, name and type. For single-option (`enum`) and multiple-option (`set`) fields, it also retains the metadata's `options` list as `{ "id": ..., "label": ... }` entries. These are configured choices, not values read from deals. Other metadata such as descriptions, colors and visibility rules is excluded.

Pipedrive's v2 list response provides these options; discovery makes no extra field-detail or deal requests. Missing or null options are omitted, meaning the API did not supply them, not that the field has no choices. An explicit empty list is preserved. Labels retain their original text, including horizontal tabs from pasted choices; the JSON output escapes those tabs. Whitespace-only labels and other unprintable characters are rejected. Custom option IDs remain positive integers; built-in IDs may also be bounded exact strings. Malformed, duplicate or oversized option metadata stops discovery with a sanitized error rather than silently dropping choices. Local safety limits are 10,000 fields, 100 pages, and 10,000 total options; option IDs and labels are length/type bounded. Treat this account-specific metadata as private even though it contains no deal values.

Copy the [mapping template](../templates/pipedrive-deal-mapping.json) into `private/pipedrive-mapping.json` and replace its placeholders using the discovered codes. The template intentionally cannot run unchanged.

| Mapping key | Required meaning |
| --- | --- |
| `schema_version` | The integer `1`. |
| `ahj_field` | Exact custom field code for the permitting authority, or built-in `org_id` only if that organization really represents the AHJ. |
| `permit_fields` | One or more distinct custom text-field codes, one for each permit identifier to preserve. |
| `address_field` | Exact custom address or text-field code containing the complete project service address, including unit. |
| `customer_name_field` | `null`, an exact custom text-field code, or explicitly selected built-in `title`. This optional display value is not used for matching. |
| `ahj_map` | Exact stored AHJ values mapped to reviewed Sun Bridge profile IDs. For organization references and enum fields, use the ID as a string key, not its display label. |

Mappings use exact codes validated against account metadata, not guesses based on field labels. Custom codes use Pipedrive's 40-character lowercase hexadecimal format. Built-in `id` is used only as the selected deal's identifier; it cannot substitute for a permit number. Other standard fields are unsupported. At most 15 unique custom fields can be selected across the mapping.

Confirm which authority each organization reference represents. A deal's primary organization is not necessarily its building department. An organization named for a city, a customer's address, and a similarly named profile do not establish that relationship. Unknown AHJ mappings produce issues and no permit rows for that deal; the adapter never creates a public jurisdiction profile.

For an organization reference, obtain its numeric organization ID from the verified Pipedrive organization record's URL or an existing private building-department inventory, then use that ID as a JSON string key in `ahj_map`. Do not use the deal ID or infer an ID from a name. For a custom single-option AHJ field, find its entry in `fields.json`, verify the option's authority, and use the option's integer `id` converted to a JSON string key, not its `label`. Multiple-option fields are discoverable but unsupported as the AHJ mapping because an individual permit row needs one explicit authority. If options were not supplied, confirm the stored option ID in Pipedrive before proceeding; do not substitute a label.

Then choose up to 100 unique deal IDs you are authorized to inspect. These example numbers are fictional; replace them with your own selection:

```sh
python3 -m sunbridge pipedrive-deals --mapping private/pipedrive-mapping.json --deal-ids 101,102 --output private/permits
```

If your mapping targets reviewed profiles in a custom directory, add `--profiles private/your-profiles` to that command. The standalone command defaults to the clone's `profiles/` directory; it does not read a workspace configuration's `profiles_path`. Every mapped profile must be loaded before the command will read Pipedrive.

The CLI and workspace configuration reject repeated input deal IDs; provide a distinct list. For callers using the Python `import_deal_permits` function directly, repeated IDs are read once and counted as ignored in the summary. Different permit fields remain separate rows even if they contain the same identifier, with `source_field` recording their origin. Existing reconciliation treats duplicate matching rows as ambiguous; the importer does not collapse them into a confident match.

Permit identifiers must be nonempty strings: leading zeros, punctuation and embedded whitespace are preserved. Missing or numeric permit values create an issue and no row for that field. A missing service address is reported while a valid AHJ-plus-permit row can remain usable. Invalid address structures or contradictory units exclude the deal. Full address text is retained; when an address object explicitly provides a separate unit omitted from the text, that unit is appended. No geocoding or office-address substitution occurs.

Inspect the private issues report before using the imported records. Unavailable or mismatched deal responses are skipped without retaining their raw payload. The adapter returns only selected permit rows, issue codes and summary counts; CLI output stays under this clone's `private/` directory. Do not publish the mapping, metadata export or permit records.

The implementation follows Pipedrive's [deal detail API](https://developers.pipedrive.com/docs/api/v1/Deals), [deal field metadata API](https://developers.pipedrive.com/docs/api/v1/DealFields), and the field-option response shape in its [official v2 OpenAPI specification](https://developers.pipedrive.com/docs/api/v1/openapi-v2.yaml). It uses GET requests to the fixed official API host, token headers, bounded cursor pagination for metadata, bounded retries, and no redirects. Automated CRM changes remain outside this adapter.
