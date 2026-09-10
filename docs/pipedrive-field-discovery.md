# Import your building-department organizations

This is a read-only setup step for an operator's own Pipedrive account. It reads organization-field definitions and the organization directory, keeps only records whose Type is Building Department, and writes a small local inventory. It does not update Pipedrive, read customer deals, or send emails.

From the repository folder, run:

```sh
python3 -m sunbridge pipedrive-import --token-file /absolute/path/to/your-token-file --output private/pipedrive
```

The token file is a plain text file containing only your own API token. Keep it outside the repository. Alternatively, a technical helper can supply `PIPEDRIVE_API_TOKEN` through their environment or secret manager. Do not put the token in a command, contribution, screenshot, or issue.

## What is discovered

The importer reads the actual field definitions; it does not assume that another account uses the same custom-field codes or numeric option IDs. It recognizes the Building Department option from its label. Use `--type-field EXACT_FIELD_CODE_OR_NAME` and `--type-label "YOUR_LABEL"` if your setup differs.

The baseline mapping supports these concepts when explicitly present:

| CRM field concept | Treatment |
|---|---|
| Type | Filter for Building Department, including option labels and numeric values |
| Jurisdiction Type | Preserve City, County or another explicit value; missing means unknown |
| County | Preserve a text value or a link to another organization, according to its field type |
| State / City / Country | Use dedicated jurisdiction fields if present |
| Parent organization | Keep an explicit CRM reference without assuming legal authority |

An organization-reference field named County has a different meaning from a free-text county field. Its linked record can help identify the county associated with a city department. It does not automatically mean the county department issues permits for that city, or supervises its building official. A city and county can have distinct profiles with the same county geography and no regulatory parent relation.

The office address is intentionally excluded. Its postal city/state is not proof of the area the department serves. If an account's custom fields use names the importer cannot recognize, missing values remain unknown and the local summary identifies the gap. Add tests and a documented mapping before expanding discovery.

## Local output

The importer writes four JSON files in `private/pipedrive/`:

- `building_departments.json`: selected departments and their projected metadata.
- `import_summary.json`: selected field metadata, counts by jurisdiction type, missing metadata, duplicate names, and county-reference issues.
- `profile_candidates.json`: unverified local candidates for further research.
- `crm_mapping.json`: the mapping from local candidate IDs to CRM organization IDs.

Original account IDs and field codes stay in these private files.

The command refuses to overwrite an existing inventory. Choose a fresh private output directory for a later snapshot and retain the earlier files according to your organization's policy.

Candidate IDs beginning with `pending` identify local CRM records only. They are not shared AHJ IDs and must not be used to identify an incoming email's authority. Candidates contain empty `status_channels` and `official_sources` lists. Use `templates/ahj-profile.json` to add the full submission, notification, verification, and parser structure, then fill it from official information and reviewed observations.

To turn a candidate into a shared profile:

1. Check the official department name, state, county and city; resolve duplicate names.
2. Verify its actual area and permit types. County membership alone is insufficient.
3. Compare it with the existing shared profiles to avoid duplicate authorities.
4. Copy `templates/ahj-profile.json` and assign a stable geographic ID.
5. Add dated official sources, and keep unresearched capabilities unknown.
6. Submit only the reviewed public profile and fictional examples. Keep the mapping to your CRM organization ID in `private/`.

This organization importer does not import deals, establish confirmed AHJ boundaries, publish profiles automatically, or create CRM fields. For a separate, explicitly selected deal read, use the [Pipedrive deal adapter](pipedrive-deals.md) with its own private mapping and validation. Organization inventory alone does not establish a permit's jurisdiction.

## API behavior

Requests use Pipedrive's official API host and two GET endpoints: `/api/v2/organizationFields` and `/api/v2/organizations`. Cursor pagination is followed to completion. The API may return other organization types during collection; only the selected departments are kept in local files. HTTP errors expose the status code without printing credentials or response bodies.

See the [organization API reference](https://developers.pipedrive.com/docs/api/v1/Organizations) and [organization-field reference](https://developers.pipedrive.com/docs/api/v1/OrganizationFields). The documentation URLs retain `v1` in their path while documenting the v2 inventory endpoints.
