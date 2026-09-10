# AHJ and utility catalog

Start with useful public reference data, link it deliberately to your organizations, and keep new operational evidence separate from the historical source. All commands run from the checkout and keep their database and reports under `private/`. Nothing here contacts a CRM, changes a permit, or calls a model.

## First run

```sh
python3 -m sunbridge catalog init
python3 -m sunbridge catalog search --state FL --kind building_department --query "Cape Coral"
python3 -m sunbridge catalog search --state FL --kind utility_company
python3 -m sunbridge catalog show --id ENTITY_ID
```

Replace `ENTITY_ID` with a result's exact `entity_id`. `--query` searches names, recorded aliases, and source IDs; it is not a property-to-jurisdiction lookup. Results default to 50; set `--limit` from 1 to 1,000. Omit a state or kind filter to search more broadly. Every catalog command accepts `--db private/your-catalog.sqlite` if you need a separate local database.

The bundled v9-9-2025 snapshot contains:

| Included records | Count |
| --- | ---: |
| Identified building departments, using source geography ID plus state | 11,662 |
| Identified utilities, using source EIA ID | 1,004 |
| Unresolved AHJ source-row entries | 88 |
| Unresolved utility source-row entries | 104 |
| Source-reported historical benchmarks after repeated-median deduplication | 28,455 |
| Historical requirement rows | 8,706 |

The 12,858 total entity entries are **not** 12,858 confidently unique authorities. An unresolved entry is kept separate by source sheet and row, even if its name resembles another entry. Some timeline cells have neither a utility name nor ID: their values remain in raw source rows and the initialization summary counts them as unassigned; no authority is invented. The catalog is not an exhaustive national authority registry.

## Read historical timelines correctly

Every benchmark retains its entity, **source state**, installation year, source size-band label (`0-10kW` or `10-20kW`), project technology (`PV Only` or `PV+Storage`), metric, median, and business-day unit. The years are 2017–2024. Utility IDs can occur across states; their state-specific observations are not combined.

| Metric key | Source label |
| --- | --- |
| `ahj_permit` | Median AHJ Permit Time |
| `pre_install_ix` | Median Pre-Install IX Time |
| `inspection` | Median Inspection Time |
| `final_ix_to_pto` | Median Final IX to PTO |

AHJ permit and inspection medians are repeated across utility pair rows in the workbook; utility medians repeat across AHJ pair rows. Sun Bridge deduplicates identical observations at the proper entity/state/cohort/metric scope and retains each contributing cell reference. It does not average medians. If a compatible input reports inconsistent numbers for the same key, the benchmark has `status: conflict`, a null selected value, and all alternatives. Review the source conflict rather than selecting a winner.

Blank, `NA`, and numeric zero remain distinct in the source rows. A missing benchmark is not zero. Only numeric observations become normalized benchmarks; completely unreported cohorts remain in the source rows. `sample_n` is always null: the workbook's AHJ–utility installation counts are not the metric's sample size. The separate `installations` table contains only positive reported counts; its absent rows must not be interpreted as proof of zero installations. Zero and missing count cells remain in `source_rows`.

Read the benchmark flags. A zero pre-install interval may reflect no required pre-install approval rather than a measured instant approval. Inspection definitions conflict within the workbook. The [methodology notes](solartrace-sources.md) retain these source caveats, vintage information, and attribution. These medians are historical comparisons, not deadlines, promises, current statuses, or individualized forecasts.

## Export to your database or CRM import process

```sh
python3 -m sunbridge catalog export --state FL --output private/catalog-export
```

The command creates a new directory containing:

- `organizations.json`: catalog entities and their original ID namespaces, states, aliases, and references.
- `benchmarks.json`: state-filtered, cohort-qualified historical measurements and evidence.
- `requirements.json`: state-filtered source fields with their sheet and row references.
- `source.json`: source version, workbook checksum, source URL, included sheets, and attribution.
- `NOTICE.txt`: complete required source notice and change disclosure.

Omit `--state` for the full source-derived export. A multistate utility may retain all its source aliases/states, but benchmark and requirement rows respect the requested state. Private email proposals are deliberately excluded. Keep the notice and source metadata with copied source-derived files, and disclose your further changes. Existing output files are never overwritten; choose a new directory for a new export.

For a quick-start import, map `kind` to your CRM's organization-type picklist. Keep `entity_id`, `geo_id`/`eia_id`, state, and source version in separate fields. Store historical benchmarks in a related table or structured record; one undated “permit turnaround” field would lose the cohort and metric. Review unresolved entities and existing records before creating new organizations. Sun Bridge supplies JSON and SQLite, **not a one-click Pipedrive create/update operation**.

The source's online submission/acceptance fields do not establish a status-retrieval method. Leave `status retrieval` unverified until you have dated evidence of email, portal, API, or manual status access. Do not infer the notification channel from online application availability.

## Reconcile existing organizations

Use the normalized organization input in [getting started](getting-started.md#2-export-and-reconcile-organization-knowledge), then run:

```sh
python3 -m sunbridge catalog reconcile --organizations private/organizations.json --output private/catalog-reconciliation
```

The `review.json` contains your `organization_id`, candidate entity IDs, issues, source provenance, and a review-required flag. The possible outcomes are:

| Outcome | Meaning |
| --- | --- |
| `exact_identifier_candidate` | Exact source ID, correct entity kind, and an observed state match. Still requires identity review. |
| `name_candidate` | One normalized exact name/alias match within kind and state. A suggestion, not a confirmed link. |
| `ambiguous` | More than one candidate; no winner selected. |
| `unmatched` | No candidate under the supplied evidence. A conflicting source ID never falls back to a name. |
| `held` | Missing or invalid required context; inspect issues. |

Only case and whitespace are normalized in names. The tool does not guess that a city office, county office, postal city, county parent, and unincorporated area are the same jurisdiction. A utility's EIA ID also needs a source state match; it is not a service-territory map. A `geo_id`/`eia_id` is never a CRM organization ID.

This input contract is CRM-neutral. An existing `pipedrive-import` inventory is a different shape and must be deliberately transformed first: its `crm.organization_id` identifies your record, `organization_name` supplies the name, and verified organization type/state supply `kind`/`state`. Retain conflicting metadata for review; do not derive state from a mailing address or treat a county organization reference as a geography ID. No live account access is needed for catalog reconciliation.

## Attach new proposed evidence without changing source facts

Create a private crosswalk after verifying the relationship between a parser profile and catalog authority. For example, this is a **placeholder structure**, not a verified mapping:

```json
{
  "YOUR_VERIFIED_AHJ_PROFILE_ID": "ENTITY_ID_FROM_CATALOG_SEARCH"
}
```

Save the completed crosswalk as `private/catalog-links.json`. Run the [email/CRM review workflow](getting-started.md#3-try-the-email-review-flow), then attach its JSON report:

```sh
python3 -m sunbridge catalog attach-review --report private/workspace/review/review.json --links private/catalog-links.json
python3 -m sunbridge catalog show --id ENTITY_ID
```

Use your actual report path. Every nonempty AHJ profile in the batch needs a verified crosswalk entry; an unmapped profile stops the entire attachment. Only building-department entities can receive this permit-event evidence. Empty-AHJ items are retained in the report and counted as skipped. Reattaching an identical report is idempotent; an existing report cannot be reassigned through a different crosswalk.

Proposals retain the report digest, input position, source snapshot, extraction/matching results, warnings, and original supporting evidence. They are **not accepted decisions or confirmed current status**. Attachment does not alter benchmarks, requirements, CRM records, or approval state. Source-version changes do not erase prior proposals. Catalog lookup may show private evidence after attachment, so do not publish that output. Only the source-only export above is intended for source-data exchange.

AHJ catalog coverage is not email-parser coverage. Utility catalog data are available now, but utility mail/account connectors and utility-specific event review are future work. No scheduled monitor or automatic updater ships in this release.

## Source updates and local storage

`catalog init` is idempotent for the bundled source digest. It activates that source; if a different local snapshot was active, the prior one stays stored. To inspect a compatible workbook privately:

```sh
python3 -m sunbridge catalog import-workbook --input /absolute/path/to/reviewed-workbook.xlsx --db private/candidate-catalog.sqlite
```

The importer supports only the reviewed v9-9-2025 worksheet/header/cohort layout and completion marker. A newer layout or version must first receive a reviewed importer change; this is not a generic Excel importer. A different checksum is marked unverified with no official-source URL, even if its layout matches. Importing is not independent verification. Use a separate candidate DB first, verify licensing and provenance, and compare differences before deliberately activating it in your operating database. Distinct source digests retain separate snapshots; reimporting the same digest does not overwrite stored rows or proposals.

To regenerate the checked-in public derivative from the exact official workbook:

```sh
python3 scripts/build_solartrace_seed.py --input /absolute/path/to/SolarTRACE-workbook.xlsx
```

Public generation accepts only the pinned official checksum. A new release needs source and license review, source-pin/format changes, revised manifest and fixed privacy-check allowlist, independent source-cell comparisons, and regression tests. Never use an inbox archive, CRM export, or arbitrary workbook as a public seed.

The database uses SQLite and owner-only file permissions. Its schema holds `sources`, `entities`, `benchmarks`, `requirements`, `installations`, `source_rows`, `review_reports`, and `proposed_events`, plus metadata and a reserved operator-annotation table. The annotation table is not an implemented approval UI. Database writes are transactional; source versions and attached reports are retained. Keep private backups and do not modify the database schema manually. There is no SQLite encryption, hosted service, authentication UI, or multiuser deployment included.
