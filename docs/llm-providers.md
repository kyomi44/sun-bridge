# Optional LLM extraction

Sun Bridge can optionally ask a language model to propose one event from an email's subject or plain-text body. This is constrained extraction, not an autonomous agent: it has no tools, CRM roster, ability to choose a deal, or authority to update a record. Every result still requires operator review and passes through the separate local matching process.

The ordinary demo and rule-based analysis do not require an API key or send messages to an LLM. LLM extraction is enabled only when you select a private configuration and explicitly allow data transfer. No provider or model has been live-certified by this release; its automated tests use fictional responses without network access.

## Supported protocol

| Option | What this release supports |
| --- | --- |
| OpenAI-compatible Chat Completions | A JSON POST to the configured base URL plus `/chat/completions`, using a model ID you choose and a bearer token from one named environment variable. |
| Loopback server using that protocol | The same request format at literal `127.0.0.1` or `[::1]`; an API key is optional. You must install and configure the server separately. |
| Native Anthropic or another distinct API | Not implemented. A provider's key alone does not make its API compatible. |

Chat Completions is used as a compatibility interface, not a claim that it is the newest or preferred API for every use case. Providers and individual models differ in their supported parameters, prompt roles, JSON behavior, retention policies, and cost. Check the chosen provider's official documentation. For OpenAI, see the [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## Configure a provider

Copy `templates/llm-config.json` to `private/llm.json` in your checkout and edit the private copy. Keep configuration and credentials out of public contributions.

```json
{
  "protocol": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "YOUR_MODEL_ID",
  "api_key_env": "SUNBRIDGE_LLM_API_KEY",
  "max_output_tokens": 1200,
  "token_parameter": "max_completion_tokens"
}
```

Replace `YOUR_MODEL_ID` with an exact model available to your provider account. The placeholder is intentionally invalid: Sun Bridge does not silently select a model. A technical helper can supply your key through the named environment variable or a secret manager in the process running the command. Never paste the key into this JSON, a command-line argument, a public issue, or a screenshot. This module does not automatically load `.env` files or retrieve account credentials.

`max_output_tokens` is sent under `token_parameter`, which accepts only `max_completion_tokens` or `max_tokens`. Select the field supported by your model. This is an output limit, not a dollar budget; some models count reasoning tokens within their completion limit. Unsupported parameters fail visibly, without automatic fallback to another model or another billed request. The client sends a developer-role instruction to `api.openai.com` and a system-role instruction to other endpoints; the chosen model must support that role.

Remote endpoints must use HTTPS and a key. Base URLs cannot contain credentials, queries, fragments, whitespace, or encoded path components. Arbitrary headers and unknown config fields are rejected. Redirects and environment proxy settings are disabled so a request cannot silently forward its authorization header to a different endpoint. If your network requires a proxy, this client does not currently support that setup.

For an already-running compatible local server, a private configuration can use a base URL such as `http://127.0.0.1:8080/v1`, your server's exact model ID, `api_key_env: null`, and its supported token parameter. Only the literal loopback addresses qualify for optional credentials and HTTP; `localhost`, other private-network hosts, and alternate numeric aliases do not. A local endpoint may itself forward requests elsewhere: verify your server's behavior. Loopback is not a guarantee of offline inference.

## Check the connection with fictional data

```sh
python3 -m sunbridge llm-check --config private/llm.json --allow-llm-data-transfer
```

This sends one fixed fictional application-receipt example—not an inbox sample or CRM export. A successful check confirms that one request returned the expected constrained result; it does not establish general model accuracy, future uptime, or suitability for real permitting. The command reports configuration provenance and status, not generated message content. The check can incur a provider charge.

## Analyze a small, authorized sample

Use the [CRM guide](crm-data.md) to prepare messages and permit records in private storage. Assign each message's AHJ only after an operator has verified the relevant authority; the model is not allowed to infer it. Start with synthetic data, then use a narrow private evaluation set whose correct outcomes are known.

```sh
python3 -m sunbridge analyze --messages examples/messages.json --permits examples/permits.json --llm-config private/llm.json --allow-llm-data-transfer --output private/llm-review
```

The explicit data-transfer flag is required even for a loopback server. An API key is not consent to send customer information. Follow your organization's authorization, privacy rules, and the provider's terms before using real messages.

Only the normalized sender address, selected subject and entire plain-text body, and the operator-assigned profile ID and name are transmitted. The body can include customer information and quoted history; transmission is not limited to the final cited excerpt. Sun Bridge does not send the CRM permit roster, deal records, message IDs, receipt timestamps, profile sources, or unrelated message fields. The provider key is used only in the authorization header. Do not put credentials in message text.

Each extraction makes at most one HTTP request with a 45-second timeout and no automatic retry. Inputs over 2,000 subject characters or 20,000 body characters are held rather than silently truncated. Responses are size-limited. Batch size, input length, the chosen model, and output limits affect cost; rerunning a batch makes new requests. Check provider usage separately—this release does not enforce a total spending budget.

## What the safeguards do—and do not do

- Require a message ID, valid sender, and exact message/profile AHJ match before requesting extraction. A nonempty profile sender allowlist is enforced; an empty list produces an explicit warning, not sender authentication.
- Allow explicit LLM extraction when a profile's subject parser is disabled, while labeling that distinction. This does not enable or validate the profile's rule parser.
- Treat email and profile text as untrusted data. Do not provide tools or forward model-generated instructions to another system.
- Accept only the documented event fields, event/scope combinations, and a single JSON result. Reject extra fields, refusals, tool calls, truncated responses, and malformed output.
- Require an exact source excerpt containing the proposed identifiers. Reject invented identifiers, partial revision identifiers, and evidence found only in common quoted-history sections. Common reply/forward subject prefixes are held before a request.
- Preserve the configured authority, message metadata, provider/model/prompt provenance, and review requirement. Do not manufacture an event timestamp or treat email arrival as the event time.

These checks catch some failure modes; they do not prove that the model understood a negation, distinguished multiple events, resisted every prompt injection, or read an address correctly. Quoted-history detection is conservative and incomplete. A model can cite real text while drawing the wrong conclusion. Verify evidence and matching separately, track abstentions and errors, and keep ambiguous cases for a person. See the [event model](event-model.md), [data handling guide](data-handling.md), and [learning path](learning-path.md).

The connection check and optional extraction are current capabilities. Live inbox monitoring, saved approval controls, CRM writes, autonomous government decisions, and their pause/recovery controls remain separate future work.
