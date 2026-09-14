# Private Gmail listener deployment

Experimental operator-run pilot, not a one-click managed service. Complete the
[mailbox and OAuth setup](../../docs/gmail-push.md) first. These commands are a
deployment recipe, not evidence that a service is live or that cloud IAM has been
tested in your project. Use a dedicated, billing-enabled project. Stop if billing,
organization policies, regional availability, or permissions are unresolved;
do not silently use another account or make the service public.

## Infrastructure contract

Use the same selected region for Cloud Run, Scheduler, Artifact Registry, and
the staging bucket; choose a supported Firestore location deliberately before
creating the default native-mode database. Keep deletion protection enabled.
Do not enable public Firebase client access. All queue access is server-side IAM.

Enable Gmail, Pub/Sub, Cloud Run, Cloud Build, Artifact Registry, Secret Manager,
Firestore, Cloud Scheduler, IAM, IAM Credentials, Cloud Logging, and Cloud Storage
APIs. The OAuth Desktop client must be in this same project.

Create the following dedicated identities and resources through an authorized
cloud administrator. Resource names below are suggested; the examples assume them.
No service-account keys or domain-wide delegation are needed.

| Principal | Minimum intended access |
| --- | --- |
| `sunbridge-gmail-runtime` service account | `roles/datastore.user` in this dedicated project; `roles/secretmanager.secretAccessor` on `sunbridge-gmail-oauth` only. |
| `sunbridge-gmail-push` service account | `roles/run.invoker` on this Cloud Run service only. |
| `sunbridge-gmail-scheduler` service account | `roles/run.invoker` on this Cloud Run service only. |
| `gmail-api-push@system.gserviceaccount.com` | `roles/pubsub.publisher` on the `sunbridge-gmail` topic only. |
| Pub/Sub service agent `service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com` | `roles/iam.serviceAccountTokenCreator` on the push service account only, to mint push OIDC tokens. |
| `sunbridge-gmail-build` service account | `roles/artifactregistry.writer` on the `sunbridge` repository; `roles/storage.objectViewer` on its private build-source bucket; `roles/logging.logWriter` in this project. No mail/secret/queue access. |

Retain Google's standard service-agent roles, including Cloud Scheduler's service
agent role, rather than granting those roles to a human or runtime identity. The
deployer needs the applicable resource-management permissions and `actAs` on the
specific service accounts used. Restrict administrator access and audit IAM.
See [authenticated Pub/Sub delivery](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
and [Scheduler authentication](https://docs.cloud.google.com/scheduler/docs/http-target-auth).

Create the private Secret Manager secret and add the locally authorized JSON as
a version with `--data-file=private/gmail/oauth.json`. Never use a credential value
in a command argument, a build substitution, public source, or a normal environment
variable. Pin the numeric secret version for the deployment. Keep the build bucket
private with uniform bucket-level access and public access prevention.

## Build and deploy

Run from the repository root. Set your own non-secret values; these examples do
not modify the globally configured gcloud project. Resource provisioning above
must be complete first. Select a region supported by all required services.

```sh
export SUNBRIDGE_PROJECT='your-dedicated-project'
export SUNBRIDGE_REGION='us-east1'
export SUNBRIDGE_MAILBOX='listener@example.invalid'
export SUNBRIDGE_GROUP='permitting@example.invalid'
export SUNBRIDGE_SECRET_VERSION='1'
export SUNBRIDGE_IMAGE="$SUNBRIDGE_REGION-docker.pkg.dev/$SUNBRIDGE_PROJECT/sunbridge/gmail-listener:pilot"
export SUNBRIDGE_RUNTIME="sunbridge-gmail-runtime@$SUNBRIDGE_PROJECT.iam.gserviceaccount.com"
export SUNBRIDGE_PUSH="sunbridge-gmail-push@$SUNBRIDGE_PROJECT.iam.gserviceaccount.com"
export SUNBRIDGE_SCHEDULER="sunbridge-gmail-scheduler@$SUNBRIDGE_PROJECT.iam.gserviceaccount.com"

gcloud meta list-files-for-upload
gcloud builds submit . --project="$SUNBRIDGE_PROJECT" --region="$SUNBRIDGE_REGION" \
  --config=deploy/gmail-push/cloudbuild.yaml --ignore-file=.gcloudignore \
  --service-account="projects/$SUNBRIDGE_PROJECT/serviceAccounts/sunbridge-gmail-build@$SUNBRIDGE_PROJECT.iam.gserviceaccount.com" \
  --gcs-source-staging-dir="gs://$SUNBRIDGE_PROJECT-build-source/source" \
  --substitutions="_IMAGE=$SUNBRIDGE_IMAGE"

gcloud run deploy sunbridge-gmail --project="$SUNBRIDGE_PROJECT" --region="$SUNBRIDGE_REGION" \
  --image="$SUNBRIDGE_IMAGE" --service-account="$SUNBRIDGE_RUNTIME" \
  --no-allow-unauthenticated --invoker-iam-check \
  --min=0 --max=1 --concurrency=1 --memory=512Mi --cpu=1 --timeout=240 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$SUNBRIDGE_PROJECT,GMAIL_MAILBOX=$SUNBRIDGE_MAILBOX,GMAIL_GROUP_ADDRESS=$SUNBRIDGE_GROUP,GMAIL_TOPIC=projects/$SUNBRIDGE_PROJECT/topics/sunbridge-gmail,GMAIL_SUBSCRIPTION=projects/$SUNBRIDGE_PROJECT/subscriptions/sunbridge-gmail-push,GMAIL_OAUTH_SECRET_JSON=/var/secrets/gmail/oauth.json" \
  --set-secrets="/var/secrets/gmail/oauth.json=sunbridge-gmail-oauth:$SUNBRIDGE_SECRET_VERSION"
```

Inspect the source upload list **before** building: only the four allow-listed
package files and deployment build files belong there. Inspect the built image
and use an immutable image digest for subsequent production revisions. The
runtime image cannot import the CRM or LLM adapters because they are not copied.
The `.dockerignore` and `.gcloudignore` files are strict allow-lists, not a
substitute for a manual privacy check. Dependency ranges need review at each build.

The Gmail settings above are required. `GMAIL_STATE_COLLECTION` is optional and
defaults to `sunbridge_mailboxes`. Firestore uses the `(default)` database and
hashed mailbox document IDs. Mail and checkpoints are private, not anonymized.

## Authenticated triggers and activation

Read the actual Cloud Run service URL; do not guess it. Grant the push and
scheduler identities service-scoped `roles/run.invoker` before creating triggers.
Verify neither `allUsers` nor `allAuthenticatedUsers` has invocation permission,
including through inherited project IAM, and that the invoker IAM check is enabled.

```sh
export SUNBRIDGE_URL="$(gcloud run services describe sunbridge-gmail \
  --project="$SUNBRIDGE_PROJECT" --region="$SUNBRIDGE_REGION" --format='value(status.url)')"

gcloud pubsub subscriptions create sunbridge-gmail-push --project="$SUNBRIDGE_PROJECT" \
  --topic=sunbridge-gmail --push-endpoint="$SUNBRIDGE_URL/push" \
  --push-auth-service-account="$SUNBRIDGE_PUSH" --push-auth-token-audience="$SUNBRIDGE_URL" \
  --ack-deadline=240 --min-retry-delay=10s --max-retry-delay=600s \
  --message-retention-duration=7d --expiration-period=never

gcloud scheduler jobs create http sunbridge-gmail-renew --project="$SUNBRIDGE_PROJECT" \
  --location="$SUNBRIDGE_REGION" --schedule='0 6 * * *' --time-zone=Etc/UTC \
  --uri="$SUNBRIDGE_URL/renew" --http-method=POST \
  --oidc-service-account-email="$SUNBRIDGE_SCHEDULER" --oidc-token-audience="$SUNBRIDGE_URL" \
  --attempt-deadline=240s --max-retry-attempts=5 --min-backoff=30s --max-backoff=600s

gcloud scheduler jobs create http sunbridge-gmail-catch-up --project="$SUNBRIDGE_PROJECT" \
  --location="$SUNBRIDGE_REGION" --schedule='*/5 * * * *' --time-zone=Etc/UTC \
  --uri="$SUNBRIDGE_URL/catch-up" --http-method=POST \
  --oidc-service-account-email="$SUNBRIDGE_SCHEDULER" --oidc-token-audience="$SUNBRIDGE_URL" \
  --attempt-deadline=240s --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s

gcloud scheduler jobs run sunbridge-gmail-renew --project="$SUNBRIDGE_PROJECT" --location="$SUNBRIDGE_REGION"
```

The first successful renewal starts **new mail only**. Gmail emits an immediate
notification; a push racing initialization retries safely. A successful Scheduler
dispatch alone is not proof the watch initialized—verify its completed attempt,
the watch expiration, and durable listener state. Then run catch-up once manually.
Google recommends [daily watch renewal](https://developers.google.com/workspace/gmail/api/guides/push).
Watch renewal does not keep a revoked or Testing-mode OAuth token alive.

## Acceptance checks and operations

Before treating the listener as live, verify all of the following privately:

- Anonymous requests and requests with an incorrect OIDC audience are rejected.
- The authorized Gmail primary address matches the selected mailbox, and the
  mailbox actually receives the selected group's **Each email** deliveries.
- A controlled, non-sensitive group-delivered test creates one review record.
  Get the group's owner's approval before sending a test to coworkers.
- Repeated delivery creates no second review record. A catch-up retrieves mail
  whose push was deliberately missed; renewal does not replace the processed cursor.
- Messages outside the group and detected authentication messages store only
  exclusion markers. A permit email with ordinary portal-login instructions is
  not discarded merely for saying to log in. Inspect truncation and exclusions.
- A stale history cursor remains visibly blocked with `resync_required=true`.
  Exercise this with synthetic tests, not by corrupting a real production cursor.
- Runtime IAM cannot access Pipedrive credentials, send mail, or invoke an LLM.
- Alerts reach a named owner for failed renewals/catch-ups, old `last_sync`, watch
  expiry approaching within 24 hours, growing push backlog, and history gaps.

These alerts and the queue review interface are **not automatically provisioned**
by this repository. `/health` only confirms the HTTP process is running; zero new
messages is not proof of a failure or proof of successful group delivery. Logs
contain fixed outcome labels, not message bodies or raw provider errors. Access
Firestore only through authorized private tooling and establish a retention policy.

To pause intake, pause both Scheduler jobs and remove both trigger identities'
`roles/run.invoker` bindings from this service. Wait for already-running requests
to finish. Do not delete the checkpoint, queue, subscription, or secret as a pause
mechanism. Revoking this OAuth grant is an additional deliberate way to stop Gmail
access, but requires fresh consent to resume. Restoring invocation and schedules
resumes from the existing cursor; an extended pause may need an explicitly scoped
backfill. Never fix a history gap by silently replacing its cursor.

Scale-to-zero is not a spending cap: Scheduler, builds, storage, reads/writes, and
other services can incur charges. Set a billing budget/alerts and review usage.
Do not connect automatic CRM writes until event interpretation, matching, approval,
conflict handling, and audit controls have been separately validated.
