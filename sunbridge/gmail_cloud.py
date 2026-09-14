"""Private Cloud Run Gmail adapter. No outgoing mail, attachments, or event inference.

Cloud Run *must* require IAM authentication: Pub/Sub and Scheduler are the only
invokers. HTTP handlers do not substitute for that deployment boundary. Optional
cloud dependencies are imported lazily, so ordinary package imports stay offline.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import getaddresses
from pathlib import Path

from .gmail_listener import (
    Busy, HistoryExpired, Incomplete, InvalidNotification, Listener,
    ListenerError, MailboxMismatch, NotInitialized, RecoveryRequired,
)

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/"
MAX_ITEM_BYTES = 50_000
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PARTS = 100
HEADERS = ("From", "To", "Delivered-To", "List-Id", "Subject", "Date", "Message-ID")
# Map only developer-owned literals to safe operational reason codes. Never log
# exception text: future adapters may put upstream content or secrets in it.
_NOTIFICATION_REJECTION_REASONS = {
    "Notification JSON contains duplicate fields.": "duplicate_fields",
    "A valid expected subscription is required.": "subscription_configuration",
    "Push subscription or envelope is invalid.": "subscription_or_envelope",
    "Push delivery metadata is invalid.": "delivery_metadata",
    "Push message is invalid.": "message_shape",
    "Push message metadata is invalid.": "message_metadata",
    "Push attributes are invalid.": "attributes",
    "Notification data is missing or exceeds its size limit.": "data_size",
    "Push envelope exceeds its size limit.": "envelope_size",
    "Notification encoding is invalid or too large.": "encoding_or_size",
    "Notification must contain valid base64-encoded JSON.": "encoding_or_json",
    "Notification mailbox or history identifier is invalid.": "mailbox_or_history",
}
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_EMAIL = re.compile(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+\Z")
_SENSITIVE = re.compile(
    r"\b(?:reset|forgot|recover|temporary|new|your)\s+(?:your\s+)?(?:password|passcode)\b|"
    r"\bpassword\s+(?:reset|recovery|changed|is)\b|"
    r"\b(?:otp|one[- ]time[\s-]+(?:password|passcode|code)|verification\s+code|"
    r"security\s+code|authentication\s+code|recovery\s+code|magic\s+link)\b|"
    r"\b(?:sign[- ]?in|log[- ]?in|two[- ]factor|multi[- ]factor)\s+(?:code|link|verification)\b|"
    r"\b(?:password|passcode|client[_ -]?secret|refresh[_ -]?token|"
    r"access[_ -]?token|api[_ -]?key)\s*[:=]|"
    r"\b(?:use|enter)\s+(?:(?:this|the)\s+)?code\s+[:\s]*[A-Za-z0-9]{4,12}\s+to\s+(?:sign|log|access|verify)\b|"
    r"\b(?:do\s+not|never)\s+share\s+(?:this|the|your)\s+code\b|"
    r"https?://\S*(?:[?&](?:token|code|secret|password)=|/(?:reset|verify|auth)/)",
    re.IGNORECASE,
)


class CloudError(ListenerError):
    """Sanitized transient cloud failure; never includes upstream response text."""


class ConfigurationError(CloudError):
    """Invalid non-secret configuration."""


class _ResponseTooLarge(CloudError):
    pass


class _MessageFormatError(CloudError):
    """Permanent malformed message data, safe to quarantine without its content."""


def _email(value):
    if not isinstance(value, str) or not _EMAIL.fullmatch(value) or len(value) > 254:
        raise ConfigurationError("An exact mailbox or group email address is required.")
    return value.lower()


def _bounded_utf8(value, limit):
    return value.encode("utf-8", "replace")[:limit].decode("utf-8", "ignore")


def _excluded(message_id, reason):
    # No subject, addresses, body, or upstream error text for excluded mail.
    return {"status": "excluded", "reason": reason, "review_required": False,
            "message_id_sha256": hashlib.sha256(message_id.encode()).hexdigest()}


def _headers(message):
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        raise _MessageFormatError("Malformed Gmail message.")
    values = payload.get("headers", [])
    if not isinstance(values, list) or len(values) > 200:
        raise _MessageFormatError("Malformed Gmail headers.")
    headers = {}
    allowed = {name.lower() for name in HEADERS}
    for entry in values:
        if not isinstance(entry, dict):
            raise _MessageFormatError("Malformed Gmail headers.")
        name, value = entry.get("name"), entry.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise _MessageFormatError("Malformed Gmail headers.")
        if name.lower() in allowed:
            try:
                value = str(make_header(decode_header(value)))
            except (ValueError, LookupError, UnicodeError):
                raise _MessageFormatError("Malformed Gmail header encoding.") from None
            headers.setdefault(name.lower(), []).append(value)
    return headers


def _in_group(headers, group):
    # Exact parsed addresses, never substring matches. These are routing hints,
    # not authentication: a matching From or List-Id does not verify a sender.
    for name in ("delivered-to", "to"):
        if any(address.lower() == group for _, address in getaddresses(headers.get(name, []))):
            return True
    list_id = group.replace("@", ".")
    for value in headers.get("list-id", []):
        match = re.fullmatch(r"\s*(?:[^<>]*\s)?<([^<>\s]+)>\s*", value)
        if match and match.group(1).lower() == list_id:
            return True
    return False


def _text_body(payload):
    stack, plain, html, issues = [payload], [], [], []
    count, decoded_bytes = 0, 0
    while stack:
        part = stack.pop()
        count += 1
        if count > MAX_PARTS or not isinstance(part, dict):
            raise _ResponseTooLarge("Message MIME structure exceeds the limit.")
        part_headers = part.get("headers", [])
        if (not isinstance(part_headers, list) or len(part_headers) > 200
                or any(not isinstance(entry, dict) or not isinstance(entry.get("name"), str)
                       or not isinstance(entry.get("value"), str) for entry in part_headers)):
            raise _MessageFormatError("Malformed Gmail MIME headers.")
        disposition = next((entry.get("value", "") for entry in part_headers
                            if isinstance(entry, dict) and str(entry.get("name", "")).lower()
                            == "content-disposition"), "")
        body = part.get("body", {})
        if not isinstance(body, dict):
            raise _MessageFormatError("Malformed Gmail body.")
        mime = str(part.get("mimeType", "")).lower()
        if part.get("filename") or body.get("attachmentId") or disposition.lower().startswith("attachment") or mime == "message/rfc822":
            issues.append("attachments_not_fetched")
            continue
        children = part.get("parts", [])
        if not isinstance(children, list):
            raise _MessageFormatError("Malformed Gmail MIME structure.")
        if children:
            stack.extend(reversed(children))
            continue
        if mime not in ("text/plain", "text/html"):
            continue
        data = body.get("data", "")
        if not isinstance(data, str) or len(data) > 256_000:
            raise _ResponseTooLarge("Message body exceeds the limit.")
        try:
            raw = base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True)
        except (ValueError, binascii.Error):
            raise _MessageFormatError("Malformed Gmail body encoding.") from None
        decoded_bytes += len(raw)
        if decoded_bytes > 192_000:
            raise _ResponseTooLarge("Message body exceeds the limit.")
        content_type = next((entry.get("value", "") for entry in part_headers
                             if isinstance(entry, dict) and str(entry.get("name", "")).lower()
                             == "content-type"), "")
        charset = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type, re.IGNORECASE)
        try:
            text = raw.decode(charset.group(1) if charset else "utf-8", errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
            issues.append("unknown_charset")
        if _SENSITIVE.search(text):
            return None, ["authentication_content"]
        (plain if mime == "text/plain" else html).append(text)
    if plain:
        return "\n".join(plain).strip(), sorted(set(issues))
    if html:
        from .mail import _PlainHTML
        converter = _PlainHTML()
        converter.feed("\n".join(html))
        converter.close()
        issues.append("html_converted_to_plaintext")
        return "\n".join(line.strip() for line in "".join(converter.text).splitlines() if line.strip()), sorted(set(issues))
    return "", sorted(set(issues + ["no_supported_text_body"]))


def sanitize_message(message, message_id, group):
    """Convert selected group mail into a bounded, explicitly unverified review item."""
    headers = _headers(message)
    if not _in_group(headers, group):
        return _excluded(message_id, "outside_selected_group")
    if any(_SENSITIVE.search(value) for values in headers.values() for value in values):
        return _excluded(message_id, "authentication_content")
    try:
        body, issues = _text_body(message.get("payload", {}))
    except _ResponseTooLarge:
        return _excluded(message_id, "message_over_limit")
    if body is None or _SENSITIVE.search(body):
        return _excluded(message_id, "authentication_content")
    raw_internal_date = message.get("internalDate")
    try:
        if not isinstance(raw_internal_date, str) or not re.fullmatch(r"\d{1,16}", raw_internal_date):
            raise ValueError()
        received = datetime.fromtimestamp(int(raw_internal_date) / 1000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise _MessageFormatError("Gmail receipt timestamp is invalid.") from None
    source_headers = {name: [_bounded_utf8(value, 1000) for value in values[:2]]
                      for name, values in headers.items()}
    item = {"status": "review_required", "review_required": True,
            "subject": _bounded_utf8(" ".join(headers.get("subject", [])), 2000),
            "body": _bounded_utf8(body, 30_000),
            "source": {"provider": "gmail", "gmail_message_id": message_id,
                       "gmail_internal_date_ms": raw_internal_date,
                       "received_at": received, "timestamp_source": "gmail_internalDate",
                       "date_header_is_unverified": True, "sender_is_unverified": True,
                       "displayed_from": _bounded_utf8(" ".join(headers.get("from", [])), 1000),
                       "headers": source_headers},
            "issues": sorted(set(issues + ["routing_headers_do_not_authenticate_sender", "no_event_inference"]))}
    if item["body"] != body:
        item["issues"].append("body_truncated")
    # JSON escaping and multibyte characters can inflate stored content.
    overhead = len(json.dumps({**item, "body": ""}, ensure_ascii=False).encode())
    if overhead > 20_000:
        return _excluded(message_id, "message_over_limit")
    while len(json.dumps(item, ensure_ascii=False).encode()) > MAX_ITEM_BYTES - 2000:
        item["body"] = _bounded_utf8(item["body"], max(0, len(item["body"].encode()) - 2000))
        if "body_truncated" not in item["issues"]:
            item["issues"].append("body_truncated")
    return item


def _http_bytes(session, method, url, *, limit=MAX_RESPONSE_BYTES, deadline=None, **kwargs):
    """Bound bytes/time; deny redirects, including OAuth redirects with secrets."""
    response = None
    deadline = deadline or time.monotonic() + 30
    try:
        if time.monotonic() >= deadline:
            raise CloudError("Google request time limit exceeded.")
        response = session.request(method, url, timeout=(5, 10), allow_redirects=False,
                                   stream=True, **kwargs)
        if 300 <= response.status_code < 400:
            raise CloudError("Google redirects are not accepted.")
        data = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if time.monotonic() >= deadline:
                raise CloudError("Google request time limit exceeded.")
            data.extend(chunk)
            if len(data) > limit:
                if response.status_code != 200:
                    raise CloudError("Google request was not successful.")
                raise _ResponseTooLarge("Google response exceeds the limit.")
        return response.status_code, dict(response.headers), bytes(data)
    except CloudError:
        raise
    except Exception:
        raise CloudError("Google request failed.") from None
    finally:
        if response is not None:
            response.close()


class _TokenResponse:
    def __init__(self, status, headers, data):
        self.status, self.headers, self.data = status, headers, data


class _TokenRequest:
    def __init__(self, session):
        self.session = session
        self.deadline = time.monotonic() + 40

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        if url != TOKEN_URL or method.upper() != "POST":
            raise ConfigurationError("Unexpected OAuth destination.")
        return _TokenResponse(*_http_bytes(self.session, "POST", TOKEN_URL, limit=64_000,
                                         deadline=self.deadline, data=body, headers=headers))


class GmailClient:
    def __init__(self, mailbox, topic, group, credentials, session):
        self.mailbox, self.group = _email(mailbox), _email(group)
        if not re.fullmatch(r"projects/[a-z][a-z0-9-]{4,61}[a-z0-9]/topics/[A-Za-z][A-Za-z0-9._~+%-]{2,254}", topic):
            raise ConfigurationError("A full Gmail Pub/Sub topic is required.")
        self.topic, self.credentials, self.session = topic, credentials, session
        self._profile_verified = False

    def _api(self, method, path, *, limit=MAX_RESPONSE_BYTES, **kwargs):
        headers = {}
        try:
            self.credentials.before_request(_TokenRequest(self.session), method, GMAIL_URL + path, headers)
        except Exception:
            raise CloudError("Gmail authorization failed.") from None
        status, _, raw = _http_bytes(self.session, method, GMAIL_URL + path,
                                     limit=limit, headers=headers, **kwargs)
        if status == 404 and path == "history":
            raise HistoryExpired("Gmail history is no longer available.")
        if status == 404 and path.startswith("messages/"):
            return None
        if status != 200:
            raise CloudError("Gmail request was not successful.")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise CloudError("Gmail returned malformed JSON.") from None
        if not isinstance(result, dict):
            raise CloudError("Gmail returned an invalid object.")
        return result

    def profile(self):
        result = self._api("GET", "profile", limit=64_000)
        if not isinstance(result.get("emailAddress"), str) or result["emailAddress"].lower() != self.mailbox:
            raise MailboxMismatch("Authorized Gmail account does not match the configured mailbox.")
        self._profile_verified = True
        return result

    def _verify(self):
        if not self._profile_verified:
            self.profile()

    def watch(self):
        self._verify()
        # No INBOX filter: messages automatically archived by Groups still matter.
        return self._api("POST", "watch", json={"topicName": self.topic}, limit=64_000)

    def history(self, start_history_id, page_token=None):
        self._verify()
        if not re.fullmatch(r"\d{1,30}", str(start_history_id)):
            raise CloudError("Invalid Gmail history cursor.")
        params = {"startHistoryId": str(start_history_id), "maxResults": 100,
                  "historyTypes": "messageAdded"}
        if page_token is not None:
            if not isinstance(page_token, str) or not 0 < len(page_token) <= 4096:
                raise CloudError("Invalid Gmail page token.")
            params["pageToken"] = page_token
        return self._api("GET", "history", params=params)

    def message(self, message_id):
        self._verify()
        if not isinstance(message_id, str) or not _ID.fullmatch(message_id):
            raise CloudError("Invalid Gmail message identifier.")
        path = "messages/" + message_id
        try:
            metadata = self._api("GET", path, params={"format": "metadata", "metadataHeaders": list(HEADERS)}, limit=64_000)
            if metadata is None:
                return _excluded(message_id, "message_no_longer_available")
            headers = _headers(metadata)
            if not _in_group(headers, self.group):
                return _excluded(message_id, "outside_selected_group")
            if any(_SENSITIVE.search(value) for values in headers.values() for value in values):
                return _excluded(message_id, "authentication_content")
            full = self._api("GET", path, params={"format": "full"})
            if full is None:
                return _excluded(message_id, "message_no_longer_available")
            return sanitize_message(full, message_id, self.group)
        except _ResponseTooLarge:
            return _excluded(message_id, "message_over_limit")
        except _MessageFormatError:
            return _excluded(message_id, "malformed_message")


def load_credentials(path, *, project=None, mailbox=None):
    """Read only the explicitly mounted authorized-user secret; never print it."""
    try:
        with Path(path).open("rb") as source:
            raw = source.read(32_001)
        if len(raw) > 32_000:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("type") != "authorized_user" or value.get("token_uri") != TOKEN_URL:
            raise ValueError()
        if any(not isinstance(value.get(key), str) or not value[key] for key in ("client_id", "client_secret", "refresh_token")):
            raise ValueError()
        scopes = value.get("scopes")
        if scopes != [READONLY_SCOPE]:
            raise ValueError()
        provenance = value.get("_sunbridge")
        if provenance is not None:
            if not isinstance(provenance, dict) or provenance.get("consent_mode") not in ("internal", "production"):
                raise ValueError()
            if project is not None and provenance.get("project_id") != project:
                raise ValueError()
            if mailbox is not None and provenance.get("mailbox") != _email(mailbox):
                raise ValueError()
    except (OSError, ValueError, TypeError):
        raise ConfigurationError("Mounted Gmail OAuth secret is invalid.") from None
    from google.oauth2.credentials import Credentials
    return Credentials(token=None, refresh_token=value["refresh_token"], token_uri=TOKEN_URL,
                       client_id=value["client_id"], client_secret=value["client_secret"],
                       scopes=[READONLY_SCOPE])


class FirestoreStore:
    """Token-fenced distributed lease; every cursor/message write rechecks it."""
    def __init__(self, client, mailbox, collection="sunbridge_mailboxes", *, clock=None, run_transaction=None):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,99}", collection):
            raise ConfigurationError("Invalid mailbox state collection.")
        self.client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._runner = run_transaction
        self.ref = client.collection(collection).document(hashlib.sha256(_email(mailbox).encode()).hexdigest())
        self.token = None
        self.generation = None

    def _transaction(self, callback):
        if self._runner:
            return self._runner(callback)
        from google.cloud import firestore
        return firestore.transactional(callback)(self.client.transaction(max_attempts=3))

    def _read(self, transaction, ref=None):
        snapshot = (ref or self.ref).get(transaction=transaction, timeout=10, retry=None)
        return snapshot.to_dict() if snapshot.exists else {}

    def _check(self, data):
        lease = data.get("lease", {})
        if (not self.token or lease.get("token") != self.token
                or lease.get("generation") != self.generation
                or not isinstance(lease.get("expires_at"), datetime)
                or lease["expires_at"] <= self.clock()):
            raise Busy("Mailbox lease is not owned by this worker.")

    @contextmanager
    def lease(self):
        if self.token:
            raise Busy("Mailbox lease is already active.")
        token = uuid.uuid4().hex

        def acquire(transaction):
            data = self._read(transaction)
            lease = data.get("lease", {})
            now = self.clock()
            if isinstance(lease.get("expires_at"), datetime) and lease["expires_at"] > now:
                raise Busy("Another worker owns the mailbox lease.")
            generation = int(data.get("lease_generation", 0)) + 1
            transaction.set(self.ref, {"lease_generation": generation,
                                      "lease": {"token": token, "generation": generation,
                                                "expires_at": now + timedelta(seconds=120)}},
                            merge=["lease_generation", "lease"])
            return generation

        self.generation = self._transaction(acquire)
        self.token = token
        try:
            yield self
        finally:
            def release(transaction):
                data = self._read(transaction)
                lease = data.get("lease", {})
                if lease.get("token") == token and lease.get("generation") == self.generation:
                    transaction.set(self.ref, {"lease": {}}, merge=["lease"])
            try:
                self._transaction(release)
            finally:
                self.token, self.generation = None, None

    def assert_owned(self):
        self._transaction(lambda transaction: self._check(self._read(transaction)))

    def renew(self):
        def update(transaction):
            data = self._read(transaction)
            self._check(data)
            lease = dict(data["lease"], expires_at=self.clock() + timedelta(seconds=120))
            transaction.set(self.ref, {"lease": lease}, merge=["lease"])
        self._transaction(update)

    def load_state(self):
        def read(transaction):
            data = self._read(transaction)
            self._check(data)
            return data.get("state", {})
        return self._transaction(read)

    def save_state(self, state):
        def save(transaction):
            self._check(self._read(transaction))
            transaction.set(self.ref, {"state": state}, merge=["state"])
        self._transaction(save)

    def put_message(self, message_id, item):
        if not isinstance(message_id, str) or not _ID.fullmatch(message_id):
            raise CloudError("Invalid review item identifier.")
        if not isinstance(item, dict) or len(json.dumps(item, ensure_ascii=False).encode()) > MAX_ITEM_BYTES:
            raise CloudError("Review item exceeds the storage limit.")
        ref = self.ref.collection("messages").document(message_id)

        def create(transaction):
            self._check(self._read(transaction))
            snapshot = ref.get(transaction=transaction, timeout=10, retry=None)
            if snapshot.exists:
                return False
            transaction.create(ref, item)
            return True
        return self._transaction(create)


def _runtime_listener():
    """A separate lease/client context per request prevents cross-request fencing."""
    import requests
    from google.cloud import firestore
    required = ("GOOGLE_CLOUD_PROJECT", "GMAIL_MAILBOX", "GMAIL_TOPIC", "GMAIL_SUBSCRIPTION",
                "GMAIL_GROUP_ADDRESS", "GMAIL_OAUTH_SECRET_JSON")
    if any(not os.environ.get(name) for name in required):
        raise ConfigurationError("Required Gmail runtime configuration is missing.")
    project, topic, subscription = (os.environ[name] for name in ("GOOGLE_CLOUD_PROJECT", "GMAIL_TOPIC", "GMAIL_SUBSCRIPTION"))
    if not topic.startswith("projects/" + project + "/topics/") or not re.fullmatch(
            r"projects/" + re.escape(project) + r"/subscriptions/[A-Za-z][A-Za-z0-9._~+%-]{2,254}", subscription):
        raise ConfigurationError("Gmail resources must belong to the dedicated project.")
    session = requests.Session()
    session.trust_env = False
    gmail = GmailClient(os.environ["GMAIL_MAILBOX"], topic, os.environ["GMAIL_GROUP_ADDRESS"],
                        load_credentials(os.environ["GMAIL_OAUTH_SECRET_JSON"],
                                         project=project, mailbox=os.environ["GMAIL_MAILBOX"]), session)
    store = FirestoreStore(firestore.Client(project=project, database="(default)"),
                           os.environ["GMAIL_MAILBOX"], os.environ.get("GMAIL_STATE_COLLECTION", "sunbridge_mailboxes"))
    return Listener(mailbox=os.environ["GMAIL_MAILBOX"], gmail=gmail, store=store)


def create_app(listener_factory=None, *, expected_subscription=None):
    """Create IAM-protected endpoints. Never return/log message or exception text."""
    from flask import Flask, jsonify, request
    from werkzeug.exceptions import HTTPException
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16_384, PROPAGATE_EXCEPTIONS=False)
    factory = listener_factory or _runtime_listener

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    def invoke(operation):
        listener = None
        try:
            listener = factory()
            if operation == "push":
                envelope = request.get_json(silent=True)
                if not isinstance(envelope, dict):
                    app.logger.warning("push_rejected_invalid_payload")
                    return "", 204
                subscription = expected_subscription or os.environ.get("GMAIL_SUBSCRIPTION", "")
                if not subscription:
                    raise ConfigurationError("Expected subscription is missing.")
                listener.push(envelope, subscription)
            elif operation == "renew":
                listener.renew()
            else:
                listener.sync()
            return jsonify(status="ok")
        except InvalidNotification as error:
            # Exact strings only: do not invoke __str__ on an arbitrary argument
            # or permit user-supplied text to become a structured log field.
            reason = (_NOTIFICATION_REJECTION_REASONS.get(error.args[0], "unknown")
                      if len(error.args) == 1 and type(error.args[0]) is str else "unknown")
            app.logger.warning("push_rejected_invalid_notification reason=%s", reason)
            return ("", 204) if operation == "push" else (jsonify(status="rejected"), 400)
        except MailboxMismatch:
            app.logger.error("gmail_configured_mailbox_mismatch")
            return jsonify(status="mailbox_configuration_error"), 503
        except RecoveryRequired:
            return jsonify(status="history_recovery_required"), 503
        except (Busy, NotInitialized, Incomplete):
            return jsonify(status="retry_later"), 503
        except HTTPException as error:
            if operation == "push" and error.code in (400, 413, 415):
                app.logger.warning("push_rejected_invalid_payload")
                return "", 204
            return jsonify(status="request_rejected"), error.code or 400
        except Exception:
            # Broad boundary intentionally suppresses SDK response/token/email text.
            return jsonify(status="temporarily_unavailable"), 503
        finally:
            if listener_factory is None and listener is not None:
                # Default runtime resources are request-local, not a connection pool.
                for resource in (listener.gmail.session, listener.store.client):
                    try:
                        resource.close()
                    except Exception:
                        pass

    @app.post("/push")
    def push():
        return invoke("push")

    @app.post("/renew")
    def renew():
        return invoke("renew")

    @app.post("/catch-up")
    def catch_up():
        return invoke("catch-up")

    return app
