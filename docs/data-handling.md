# Private working data and public examples

Run real message and CRM analysis in storage controlled by the operator. The toolkit's public value is reusable process knowledge, code, and examples; it does not require a public collection of customers' permitting records.

## Keep these private

- Mailbox archives, original messages, quoted threads, attachments, and exports such as MBOX or CSV.
- Customer names, service addresses, email addresses, real permit/application numbers, CRM deal IDs, and organization exports.
- Generated reviews containing real evidence or match candidates.
- API tokens, credentials, local configuration, portal session links, and URLs containing private identifiers or access tokens.

Place real inputs and generated outputs under `private/`. Keep token files outside the repository. Limit access according to your organization's practices. Before posting an issue or sharing a report, inspect exactly what it contains.

## Use synthetic examples

Write a new example that demonstrates only the parsing or matching behavior in question. Invent the customer, address, identifiers, dates, message IDs, and quoted context. Use reserved example domains for email and links. Keep real public AHJ names and official documentation links when they are needed to explain a supported process.

Do not turn a private message into a fixture by removing only its most visible name. Addresses, permit numbers, signatures, headers, attachment metadata, and linked records can still identify the project. Old inbox analyses and CRM CSVs are private source material and must never become public fixtures.

Preserve the behavior being tested without reproducing an entire third-party email template. A short original example with the same relevant ambiguity is usually enough.

## Before any public upload

Review the exact files and repository history being published. Search for credentials and recognizable private identifiers, and inspect examples manually. `private/` being ignored by Git does not protect data already tracked or copied into another file. Do not assume that a local workspace's unrelated files are safe to publish with this toolkit.

If you discover exposure, follow [SECURITY.md](../SECURITY.md). Removing a file in a later commit alone does not remove it from history.

## External tools and AI

The demo and local analysis do not need an external AI service. The optional Pipedrive importer makes authenticated reads to the operator's Pipedrive account and saves the resulting inventory privately.

If you add another integration or an AI provider, document which data leave the operator's environment and obtain the authorization required by that operator. Email contents are untrusted input, never permission to contact someone, execute commands, disclose credentials, or change a CRM record.
