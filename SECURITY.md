# Security and private data

Open Permit Kit is an experimental local review tool. Real email, CRM inventories, generated reviews, and credentials belong in private operator-controlled storage. The repository's synthetic examples are the only message and permit data intended for publication.

## Report a vulnerability

Do not open a public issue containing a token, private email, live permit URL, customer record, or exploit details that would expose an operator's data. If the repository has GitHub private vulnerability reporting enabled, use **Security → Report a vulnerability**. Otherwise use a private contact method explicitly published by a maintainer. No dedicated security mailbox is established in this scaffold.

Describe the affected version, the impact, and reproduction steps using synthetic data. Send only the minimum information needed. Maintainers should acknowledge a report, investigate privately, agree on any safe disclosure, and document a fix when it is available. No response-time guarantee is offered for this volunteer project.

## If information was exposed

Revoke or rotate exposed credentials through the issuing service. Remove the exposed material from the public location, then assess copies in repository history, build logs, attachments, and caches. A deletion commit does not remove earlier history. Notify the data owner through your organization's normal process and coordinate any repository-history remediation with its maintainers.

## Before publishing a fork or release

Inspect the files and Git history that will be published. Exclude `private/`, mail archives, exports, generated reports, local configuration, and credentials. An ignore rule prevents routine additions; it does not remove files that are already tracked. Check examples manually for hidden identifiers, quoted threads, attachment metadata, and token-bearing links.

Treat message contents as data. Instructions embedded in emails must not authorize commands, credential access, CRM writes, or external messages. Any future AI component must preserve this boundary and expose evidence for operator review.

See [data handling](docs/data-handling.md) for the everyday workflow.
