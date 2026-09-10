# Import a local email sample

Sun Bridge can convert one `.eml` file, a folder's top-level `.eml` files, or a standard `.mbox` export into private JSON message records. The importer runs locally using Python's email parser. It does not connect to Gmail or Google Groups, retrieve a live inbox, call an LLM, or update a CRM.

First select messages belonging to one verified AHJ. The import assigns the profile you supply to every message; it does not infer or verify jurisdiction from the sender, address, or contents. Do not assign a mixed-jurisdiction inbox to a single profile.

From the repository folder:

```sh
python3 -m sunbridge import-mail --input private/sample.eml --ahj PROFILE_ID --output private/mail
```

Replace `PROFILE_ID` with the exact profile ID appropriate to your sample. Use a directory or `.mbox` path for a batch. The command writes `private/mail/messages.json` and prints a count; it does not write a separate summary file. With private profiles, add `--profiles private/your-profiles`; standalone commands do not read workspace configuration. This is a conversion step; use the review command separately:

```sh
python3 -m sunbridge analyze --messages private/mail/messages.json --permits private/permits.json --output private/mail-review
```

Your permit records must use the [documented input structure](crm-data.md). A real AHJ profile without an enabled parser will produce unknown events for review. Imported body text being available does not establish parser coverage.

## What is retained and flagged

Encoded headers are decoded. MIME text/plain is preferred; HTML-only bodies become plain text. HTML scripts, styles, embedded active content, and tracking-image references are not executed or fetched. Attachments and attached messages are ignored and their presence is annotated; permit PDFs are not extracted or interpreted.

An email's `Date` header is supplied by its sender and is not an inbox receipt timestamp or proof of when a permitting event happened. The importer keeps it as `date_header` and, if valid and timezone-aware, `date_header_at`. It leaves `received_at` empty, labels `timestamp_source`, and adds `import_issues` for review. Invalid dates and decoding replacements remain visible as issues.

A missing Message-ID receives a stable synthetic identifier derived from the raw message bytes and is flagged. Identical bytes produce the same identifier; this does not prove distinct exports represent the same business event. Existing duplicate IDs are retained for the review workflow to assess.

## Limits and private handling

The default message limit is 100. `--limit` can raise it up to 1,000. Total input is capped at 25 MiB, each message at 5 MiB, and each message's inspected MIME structure at 200 parts. If a limit is exceeded, the import fails with a request to split or reduce the export; it does not silently omit excess messages. Symbolic links are rejected. Folder imports are not recursive and select only top-level `.eml` entries.

Keep originals, converted JSON, and reports under `private/`. Never attach real samples to a public issue; use newly invented examples. See [data handling](data-handling.md).

Review output includes a standalone `review.html` alongside Markdown and JSON. Open it in your browser to read the summary, original subject, source evidence, sender, timestamps, matching outcome, and review notes. It has no scripts, external assets, clickable message links, forms, or update actions. It is a private local file, not a hosted site or a monitoring dashboard.
