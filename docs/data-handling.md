# Private working data and public examples

Run real message and CRM analysis in storage controlled by the operator. The toolkit's public value is reusable process knowledge, code, and examples; it does not require a public collection of customers' permitting records.

## Keep these private

- Mailbox archives, original messages, quoted threads, attachments, and exports such as MBOX or CSV.
- Customer names, service addresses, email addresses, real permit/application numbers, CRM deal IDs, and private CRM organization exports.
- Generated reviews containing real evidence or match candidates.
- API tokens, credentials, local configuration, portal session links, and URLs containing private identifiers or access tokens.

Place real inputs and generated outputs under `private/`. Keep token files outside the repository. Limit access according to your organization's practices. Before posting an issue or sharing a report, inspect exactly what it contains.

The catalog database also becomes private operational data when review reports are attached. Do not publish it or `catalog show` results containing proposals. `catalog export` deliberately exports only the active source-derived organizations, benchmarks, requirements, provenance, and source notice; it excludes private event evidence and mappings.

## Public source datasets

Public source data are different from private CRM exports. The bundled SolarTRACE derivative has a verified source checksum, its own attribution and reuse terms, and preserved source definitions. Keep its [complete notice](../catalog/solartrace/NOTICE.txt) and provenance with redistributed derivatives. Do not treat the software license as a license for other people's data.

The public-file checker permits one exact, checksum-pinned compressed source asset. That exception does not permit arbitrary workbooks, archives, mailboxes, private exports, or other binary files. Source updates require fresh provenance/privacy review and tests before the pin changes. See the [catalog update process](catalog.md#source-updates-and-local-storage).

## Use synthetic examples

Write a new example that demonstrates only the parsing or matching behavior in question. Invent the customer, address, identifiers, dates, message IDs, and quoted context. Use reserved example domains for email and links. Keep real public AHJ names and official documentation links when they are needed to explain a supported process.

Do not turn a private message into a fixture by removing only its most visible name. Addresses, permit numbers, signatures, headers, attachment metadata, and linked records can still identify the project. Old inbox analyses and CRM CSVs are private source material and must never become public fixtures.

Preserve the behavior being tested without reproducing an entire third-party email template. A short original example with the same relevant ambiguity is usually enough.

## Before any public upload

Review the exact files and repository history being published. Search for credentials and recognizable private identifiers, and inspect examples manually. `private/` being ignored by Git does not protect data already tracked or copied into another file. Do not assume that a local workspace's unrelated files are safe to publish with this toolkit.

If you discover exposure, follow [SECURITY.md](../SECURITY.md). Removing a file in a later commit alone does not remove it from history.

## External tools and AI

The demo and rule-based analysis do not need an external AI service. Optional Pipedrive adapters make authenticated reads to the operator's account and save projected organization or explicitly selected permit records privately. They do not write to the CRM.

Optional model extraction is disabled by default. Enabling it requires a private configuration and explicit data-transfer authorization on every run. The configured endpoint receives the selected sender, subject, entire plain-text body (including any quoted history), and assigned authority ID/name. It does not receive the CRM roster or credentials embedded in prompts. Real messages may contain customer information: obtain the required organizational authorization and check provider terms, retention and costs before sending them. A loopback endpoint may itself forward data elsewhere. See [LLM connections](llm-providers.md) for the exact protocol and limits.

Generated HTML has no scripts, remote assets, or update actions, but still contains private evidence and match details. A file being local or ignored by Git is not encryption, access management, or permission to share it. Do not host the report or upload it to a public issue. Generated outputs use owner-only file permissions where the operating system supports them; follow your own device, backup, and access-control policies.

If you add another integration or an AI provider, document which data leave the operator's environment and obtain the authorization required by that operator. Email contents are untrusted input, never permission to contact someone, execute commands, disclose credentials, or change a CRM record.
