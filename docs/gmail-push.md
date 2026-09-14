# Gmail push listener setup

The Gmail listener is an experimental, separately deployed intake backend. These instructions do not mean a Cloud project, service, subscription, or live mailbox watch has been deployed. The authorization helper prepares one private credential; it does not start a listener, call a model, or update a CRM. See the [deployment runbook](../deploy/gmail-push/README.md) for infrastructure, activation, verification, and pause procedures.

## Mailbox and project prerequisites

Use a dedicated Sun Bridge Google Cloud project. The Desktop OAuth client and Pub/Sub topic must belong to that same project; Gmail requires the topic's project to match the project executing the watch. Enable Gmail API and the backend's required Google Cloud services. Allow `gmail-api-push@system.gserviceaccount.com` to publish to the dedicated topic, following [Google's Gmail push guide](https://developers.google.com/workspace/gmail/api/guides/push).

Authorize a real Gmail or Google Workspace mailbox that receives the messages. A Google Group and a mail alias are not separate Gmail mailboxes. For group delivery, make the listener mailbox a group member with **Each email** delivery, then confirm messages actually arrive in that mailbox. The helper verifies the signed-in account's primary address through Gmail `users/me/profile`; an alias is not accepted as that primary address. It requests only `gmail.readonly`, not permission to send, modify, or delete mail.

Configure the Google OAuth consent screen before downloading a **Desktop app** client JSON from that project:

- **Internal:** available for an eligible Google Workspace/Cloud Identity organization; the authorized user must be inside that organization.
- **Production:** use the applicable verification and policy process for this restricted Gmail scope. Selecting Production does not itself establish verification, policy compliance, or remove other applicable restrictions.

Do not use external **Testing** for a durable listener. With Gmail scopes, refresh tokens from an external app in Testing expire after **7 days**. Daily watch renewal cannot extend that refresh token. Other revocation and expiration conditions still apply in Internal or Production. See [Google's refresh-token expiration documentation](https://developers.google.com/identity/protocols/oauth2#expiration) and [Desktop OAuth flow documentation](https://developers.google.com/identity/protocols/oauth2/native-app).

## Authorize locally

Use a local browser on the same computer as the helper. Install `google-auth-oauthlib` in a dedicated virtual environment; ordinary Sun Bridge imports and the synthetic helper tests do not require it. Keep the downloaded client JSON private, and do not paste it, tokens, or callback URLs into a task or issue.

From the repository folder, substitute the real client-file path, primary mailbox, and dedicated project ID:

```sh
python3 scripts/authorize_gmail_listener.py \
  --client-file /absolute/private/path/desktop-client.json \
  --mailbox listener@example.invalid \
  --project YOUR_SUN_BRIDGE_PROJECT_ID \
  --output private/gmail/oauth.json \
  --consent-mode internal
```

Use `--consent-mode production` only when that is the actual configuration. This required argument is an **operator acknowledgement**, not a machine-verified consent-screen check. The helper cannot determine your organization eligibility, publishing state, or verification status.

The helper opens browser consent with PKCE, a random-port `127.0.0.1` callback, and offline access. Finish within five minutes. It does not print the authorization URL, authorization code, state, access token, refresh token, or provider error bodies; callback logging is suppressed. If a browser cannot open, retry on a computer with a local browser. There is no printed-URL or out-of-band-code fallback.

Before saving, the helper requires an explicitly confirmed grant containing exactly Gmail read-only access, a refresh token, and a matching primary mailbox. It rejects broader grants and fails closed if granted scopes cannot be confirmed. If an old app grant prevents a fresh, read-only refresh grant, revoke that app's existing access in the Google account and authorize again; do not revoke unrelated applications.

The output must be a new file inside this clone's `private/` folder with no symbolic links. Existing credential files are never replaced. The helper creates missing credential directories with owner-only permissions (`700`) and the file with owner-only permissions (`600`). Existing credential directories must already be owned by you and owner-only. The JSON uses Google's `authorized_user` fields plus private `_sunbridge` project/mailbox/consent-mode provenance. It contains the client secret and refresh token, but **no access token**. Never commit, publish, or email it. Runtime credential installation belongs in the deployment's private secret store; do not include it in a container image or environment-value logs.

## Private backend and current limits

The backend design uses an authenticated, private Cloud Run service. Pub/Sub's authenticated push caller invokes `/push`; a separately authorized scheduler invokes `/renew` daily and a catch-up operation every five minutes. Grant only the dedicated caller identities permission to invoke the service. Gmail notifications carry a mailbox/history pointer, not the complete message; the listener retrieves the corresponding mail read-only. It makes no CRM updates or model calls.

The first successful watch establishes a **new-mail-only** baseline. It does not automatically import the existing inbox or group archive. Later catch-up follows the saved Gmail history cursor, including when a push was missed. If Gmail rejects an expired history cursor with `404`, the gap must remain visible for operator review; there is no silent cursor reset or automatic historical backfill. Any deliberate backfill needs a separately reviewed scope and procedure. See [Google's synchronization guide](https://developers.google.com/workspace/gmail/api/guides/sync).

Watch expiry and credential expiry are independent. Daily watch renewal and five-minute catch-up are intended operational checks, not guarantees of delivery or substitutes for monitoring failures. Verify the deployed service, identity restrictions, scheduler results, active watch, and a controlled test message before calling the listener live.

Only messages routed to the configured group are eligible for private review storage. Routing headers are not proof of the original sender's identity. Unrelated messages, detected authentication/reset messages, oversized content, and unsupported mail receive content-free exclusion records. Detection is a precaution, not a guarantee that all sensitive content is removed; the entire queue remains private. Attachments are not separately retrieved or stored, and plain-text content is bounded. Nothing in this intake path establishes permit approval, issuance, a CRM match, or authority to change a record.

The queue currently lives in Firestore; a connection to the local Sun Bridge review report and an operator-facing review queue are not implemented. Repeated pushes and interrupted runs use Gmail message IDs for durable duplicate protection. Work exceeding the bounded scan or request duration leaves the cursor unchanged and requires investigation if retries cannot drain it. There is no automatic history reset, queue retention policy, historical backfill, or operational dashboard. Decide retention and failure ownership before production use; do not use a passing `/health` response as proof that email delivery is healthy.
