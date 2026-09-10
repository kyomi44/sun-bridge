# CRM support and contribution contract

Support names a capability, not just a vendor. A working read adapter does not imply writes, OAuth, synchronization, automatic field discovery/mapping, or production reliability.

The machine-readable inventory is [integrations/crms.json](../integrations/crms.json). Inspect it from a clone:

```sh
python3 -m sunbridge integrations
python3 -m sunbridge integrations --json
```

## Current matrix

| Adapter | Status | Authentication | What it can do | Verification limits |
| --- | --- | --- | --- | --- |
| Normalized JSON file | Available locally | None | Read deliberate permit records and reconcile locally. | Synthetic tests; not native support for the CRM that supplied an export. |
| Pipedrive | Experimental | Token file or `PIPEDRIVE_API_TOKEN` | Discover organization/deal fields, inventory Building Departments, read explicitly selected deals with private mappings. | Organization discovery had a limited live read; new deal reads have offline mock coverage, not live certification. |
| HubSpot | Planned | Not implemented | No native API adapter. | Contribution target only. |
| Salesforce | Planned | Not implemented | No native API adapter. | Contribution target only. |
| Zoho CRM | Planned | Not implemented | No native API adapter. | Contribution target only. |

**Every adapter currently has CRM writes disabled.** There is no periodic synchronization, saved decision queue, or automatic status field update. See [Pipedrive setup](pipedrive-deals.md) and the [CRM data model](crm-data.md).

## Smallest useful contribution

Open a **CRM integration** issue before a substantial connector. Identify a specific read capability, one maintainable permit-mapping approach, official API documentation, and the operator who can evaluate the workflow. Do not share your actual account configuration or token. A wishlist entry remains `planned` until working code, documentation, and tests exist.

Use [templates/crm-adapter.json](../templates/crm-adapter.json) as a manifest starting point. Implement an adapter alongside `permitkit/crm.py`, then explicitly wire it into workspace validation/setup, offline doctor checks, and the CLI. Adding a manifest alone does not register executable behavior. Update the support matrix and tests together; `validate` checks that listed implemented files and tests exist, not that every claimed behavior is proven.

A submission should contain:

1. **Narrow authority.** The exact read endpoints, requested fields, explicit project/deal selection, authentication boundary, and pagination/rate-limit behavior. Do not bundle write scopes into a read-only pilot.
2. **A private mapping template.** Stable account-specific field codes and verified AHJ references. Preserve separate permit/application identifiers, full service address and unit, and optional customer display name. No heuristic assignment by postal city or name alone.
3. **Normalized output.** A `permits` array plus safe `issues` and `summary`. Each permit row needs `deal_id` and `ahj_id`, with `permit_id`, `service_address`, optional `customer_name`, and source-field provenance when applicable. See the synthetic [records](../examples/permits.json). Never supply opaque model instructions or an already-authorized update action.
4. **Failure handling.** Hold missing/ambiguous fields, duplicate permits, unknown jurisdictions, stale credentials, unavailable records, and partial reads visibly. Never invent a permit number or silently treat a skipped record as successfully synchronized.
5. **Privacy and transport.** Keep tokens out of URLs/logs/configuration literals; restrict requests to documented destinations and redirects; retain only required projected fields in private files. Never send the CRM roster to a model.
6. **Offline tests.** Cover synthetic happy paths, exact field selection, multiple permits, cross-jurisdiction conflicts, units, no match, malformed/private error payloads, pagination boundaries, and the absence of writes. CI must not require live credentials.
7. **A reproducible pilot guide.** Include a fictional smoke test, supported API/version/field types, limitations, maintainer/contact mechanism, and dated live-check scope if one exists. Do not publish actual evaluation records.
8. **A human learning outcome.** Show how an operator inspects evidence, identifies a wrong match, understands an import issue, and contributes a regression with a technical helper.

Keep the core matching rules CRM-independent. A proposed event comes from evidence; a local matcher finds candidates; a person evaluates both. Future writes require the separate authority, audit, conflict, and recovery gates in [governance](../GOVERNANCE.md), not just an additional API method.

## Status meanings

- **Planned:** an invitation to contribute, not an implemented connector.
- **Experimental:** code, instructions, and offline tests exist; account setup and a bounded supervised evaluation are still required.
- **Available:** a scoped capability can be used as documented; this label alone does not certify real-world parser accuracy, a provider, or an entire CRM product.

Publish exactly what was verified. A simulated API test, a successful connection, an organization inventory, and an operator-reviewed permitting pilot are different kinds of evidence.
