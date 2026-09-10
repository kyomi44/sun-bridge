# SolarTRACE source and import notes

The SolarTRACE catalog is a historical reference for authorities having jurisdiction (AHJs), utilities, requirements, and project timelines. It is not a live permit-status feed, an exhaustive registry of all authorities, or a guarantee of present-day requirements or approval times. Importing a source entry does not establish that it matches an operator's CRM organization or that the authority supports email automation.

## Source and version

The source is *Solar Permitting, Inspection, and Interconnection Cycletimes and Requirements*, by Jeffrey Cook, Jesse Cruce, Emily Fekete, and Shiyuan (Sara) Dong, originally cataloged in 2021, DOI [10.7799/1774106](https://doi.org/10.7799/1774106). The [lab catalog](https://data.nlr.gov/submissions/160) and [OpenEI record 8221](https://data.openei.org/submissions/8221) point to the same workbook resource.

Those are the 2021 catalog citation creators. The workbook separately credits Jesse Cruce, Emily Dalecki, Noah Frey, Katie Nissen, Pablo Botín Garcia-Planas, and Jeff Cook, all NREL, in `Information!A53:A58`. Both attributions are retained.

| Provenance item | Value |
| --- | --- |
| Workbook | `SolarTRACE Dataset v9-9-2025.xlsx` |
| Workbook completion date | September 9, 2025, as stated in `Information!A2` |
| Catalog resource version | 3 |
| Lab catalog last updated | March 12, 2026; distinct from the workbook completion date |
| Actual historical timeline headers | 2017–2024 |
| Supplied workbook and matching official download SHA-256 | `3a4d51ba622d1132e2451387c9b359dbd6674e1d8e94e7f59733019ccb4a6d26` |
| Official download match verified | September 10, 2026 |
| Source/license metadata checked | September 10, 2026 |

Download from the [stable official resource URL](https://data.nlr.gov/system/files/160/1763653965-SolarTRACE%20Dataset%20v9-9-2025.xlsx). The server can redirect to an expiring signed download; do not save that temporary URL as the source identity. On September 10, 2026, locally computed SHA-256 hashes confirmed that the official download exactly matches the supplied workbook. The hash above is locally verified, not a checksum published by the source; no published checksum was found in the two catalog records. Verify any newly downloaded workbook separately before treating it as the same snapshot.

## What this first catalog contains

The derivative selects three data worksheets: `AHJ-Utility Timelines`, `AHJ permits reqs`, and `Utility IX reqs`. It also retains the `Information` worksheet's definitions and acknowledgments for provenance. Their raw rows are preserved in [rows.json.gz](../catalog/solartrace/rows.json.gz), including original headers and missing-value markers, with snapshot provenance in [manifest.json](../catalog/solartrace/manifest.json) and the accompanying [NOTICE.txt](../catalog/solartrace/NOTICE.txt). The raw workbook is not bundled. The SQL import is a separate normalized representation with entities, historical benchmarks, and requirements; it does not alter the preserved source rows.

State-level results and quartile results are intentionally outside this first catalog import. Other workbook sheets are not implied to be included. Do not describe the derivative as the complete SolarTRACE workbook.

Timeline observations must retain their source AHJ/utility pairing, year, system-size cohort, project type, metric, and any reported sample count. The catalog description distinguishes PV-only from PV-plus-storage and separates size groups; the preserved worksheet headers control the actual cohort labels. Do not combine cohorts or average their medians into a purported overall median. Retain zero, blank, and textual missing-value markers distinctly: zero may be meaningful, and missing information is not evidence that a requirement or timeline is zero.

Keep source identifiers in their own namespaces and preserve their original representations. AHJ geography identifiers and utility identifiers are not interchangeable with CRM organization IDs. Matching a name, a city, or an office mailing address is not enough to establish jurisdiction or a CRM link. Operator-specific mappings belong in the operator's database, not the public source snapshot.

## Definitions and source caveats

- `Information!C12` still describes a 2017–2022 period, while the selected historical data headers run through 2024. Preserve and disclose this inconsistency; do not silently truncate the data to the older prose description.
- `Information!C13` describes the AHJ permit statistic as median business days from the original permit submission to final approval, including resubmissions, with a minimum-10-install reporting rule. It is not a mean, a statutory deadline, or necessarily the time spent actively reviewing an application. Preserve the associated source counts and omissions rather than filling unreported values.
- The inspection wording in `Information!C15` is ambiguous when read against `Information!C47` and its installation-to-last-inspection description. Retain the metric's source label and this caveat. The import must not silently resolve the conflict into a new, more precise definition.
- The [current official viewer](https://maps.nlr.gov/solarTRACE/) describes business-day intervals for permit submission to issuance, pre-install interconnection application to approval, installation completion to final inspection approval, PTO request to PTO approval, and contract signing to PTO. It explicitly permits a zero pre-install interconnection interval when that process is not required. Viewer wording helps explain the measures but does not repair contradictory workbook notes.
- The source catalog warns that the dataset may be incomplete and may repeat errors from partner-provided requirements lists. Historical requirements must be rechecked with the relevant authority before use as current operating instructions. The dataset does not establish the format, consistency, or availability of status-update emails.

Do not import exclusion rules from other SolarTRACE publications without checking that they apply to this workbook. For example, the [2022 pandemic analysis](https://docs.nlr.gov/docs/fy22osti/83529.pdf) describes a study-specific subset and exclusion of total timelines over 260 business days. That is not evidence that this workbook uses the same exclusion.

## Attribution and reuse

The [OpenEI record](https://data.openei.org/submissions/8221) identifies the dataset as [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), which permits redistribution and adaptation with attribution, the license link, and disclosure of changes. The lab catalog also links a [dataset-specific notice](https://data.nlr.gov/node/160/license) requiring the complete notice in copies, DOE/NREL/ALLIANCE credit, and no implied endorsement. These source licensing statements are both recorded rather than declaring one silently superseded. The lab notice also disclaims warranties, support, and any obligation to provide updates.

The complete lab notice, attribution, license links, and the derivative's change description are in [the accompanying notice](../catalog/solartrace/NOTICE.txt). Keep it with source-derived data copies and exports. The source data are not relicensed under the repository's software license and are not represented as public domain. Sun Bridge's extraction or normalization does not imply endorsement or independent verification by DOE, NREL, ALLIANCE, or the National Laboratory of the Rockies.

## Future updates

Treat each upstream workbook as a new, explicit import candidate. Record its resource URL, workbook completion date, catalog date, SHA-256, worksheet/header inventory, and license metadata. Compare IDs, cohorts, missing-value conventions, and metric definitions before accepting the update. Preserve prior snapshots and operator mappings; report changed or unmatched records instead of silently replacing approved mappings. A downloader still uses the data under the source terms and does not remove attribution requirements.
