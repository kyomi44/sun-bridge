# Bring your own permitting inbox

Sun Bridge does not require a particular company's mailbox, email address, CRM,
or AI provider. Keep account settings and incoming mail in your own private
environment. The live connector included here is **Gmail/Google Workspace only**;
configurable addresses do not mean every email provider has a working connector.

## Choose an intake path

| Source | Available today | Setup |
| --- | --- | --- |
| Local EML/MBOX export | Local import and review, independent of the original email provider | [Getting started](getting-started.md) |
| Google Group delivered to a Gmail/Workspace mailbox | Experimental read-only push listener with renewal, catch-up, and private queue storage | Example below |
| Other providers, including Microsoft 365 and IMAP servers | No live connector yet; use a supported local export or contribute an adapter | Contribution checklist below |

Live intake and local review are currently separate: the Firestore queue does not
automatically feed the local report, extract milestones, match CRM records, or
authorize updates. No CRM account or model token is needed to collect mail.

## Example: Google Groups to Pub/Sub

All addresses below are fictional placeholders. Use a group and mailbox your
organization owns and is authorized to connect.

```text
Google Group: permitting@example.invalid
    │ delivers each email
    ▼
Gmail mailbox: listener@example.invalid
    │ Gmail watch sends a change notification
    ▼
Pub/Sub topic → authenticated push → private Cloud Run listener
                                       │ retrieves new mail read-only
                                       ▼
                                  private Firestore queue

Cloud Scheduler → daily /renew and five-minute /catch-up
```

1. Choose the permitting group and a dedicated **real Gmail/Workspace mailbox**.
   Add that mailbox as a group member, select **Each email**, and verify delivery
   in the mailbox. A group address or alias cannot authorize Gmail on its own.
   See [Google's subscription settings](https://support.google.com/groups/answer/9792489).
2. Have your cloud administrator select a dedicated billing-enabled Google Cloud
   project, an appropriate region, and an operational owner. Set a budget alert;
   a budget is not a spending cap. Do not reuse someone else's project identifiers.
3. Copy the [configuration example](../deploy/gmail-push/config.env.example) into
   `private/gmail/config.env` and replace its placeholders. Keep that directory
   owner-only (`0700`) and the private file owner-only (`0600`). The file contains
   settings, **never credentials**; it does nothing until explicitly sourced.
4. Complete the [Gmail consent and local authorization guide](gmail-push.md).
   Authorize the listener mailbox, not the group, with Gmail read-only access.
   Keep the Desktop OAuth client and the Pub/Sub topic in the same project.
5. Follow the [deployment runbook](../deploy/gmail-push/README.md) to provision
   private resources and least-privilege identities, mount the credential through
   Secret Manager, deploy the listener, and create authenticated triggers.
   Provisioning is an administrator-run recipe, not a one-click installer.
6. Initialize the watch, then verify actual push delivery, stored private review
   items, catch-up, duplicate handling, and alerts. Start with existing authorized
   traffic or obtain the group owner's approval before sending a test email.
   The first watch starts **new mail only**; it does not import the group archive.

Google's [Gmail push guide](https://developers.google.com/workspace/gmail/api/guides/push)
explains the mailbox-to-Pub/Sub bridge. The group itself is not the publisher.
The runbook includes activation, rejection diagnostics, and pause procedures.
An HTTP health check alone does not prove mail is arriving or that parsing works.

## Contribute another live connector

Open a focused proposal naming the provider, its official notification or polling
API, and the minimum permission required. Do not route another provider's webhook
into `/push`: that endpoint validates the Gmail/Pub/Sub protocol specifically.
There is no universal live-provider plugin interface yet.

Keep transport separate from permit interpretation and CRM writes. An adapter
proposal should cover explicit account verification and source selection,
credential storage, duplicate protection, durable checkpoints, subscription
renewal or polling, missed-event recovery, visible gaps, and an operational pause.
Use provider-specific IDs and receipt times as provenance, not proof of sender
identity or the date a permit milestone occurred.

Include synthetic tests for retries, duplicates, malformed notifications, unrelated
mail, sensitive authentication content, and expired checkpoints. Publish only
fictional fixtures and non-routable example addresses—not real messages with
names removed. Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and the
[data-handling guide](data-handling.md). Mark new connectors experimental until
privately verified; a working intake adapter does not establish parser or CRM
write compatibility.
