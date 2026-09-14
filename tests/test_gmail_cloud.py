"""Offline cloud boundary tests: no account access, real credentials, or network."""
import base64
import copy
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, mock_open, patch

from sunbridge.gmail_cloud import (
    CloudError, ConfigurationError, FirestoreStore, GmailClient, MAX_ITEM_BYTES,
    READONLY_SCOPE, TOKEN_URL, _http_bytes, _in_group, _runtime_listener,
    _TokenRequest, create_app, load_credentials, sanitize_message,
)
from sunbridge.gmail_listener import (
    Busy, HistoryExpired, Incomplete, InvalidNotification, MailboxMismatch,
    NotInitialized, RecoveryRequired, Listener,
)

MAILBOX = "listener@example.invalid"
GROUP = "permits@example.invalid"
TOPIC = "projects/example-project/topics/gmail-events"
SUBSCRIPTION = "projects/example-project/subscriptions/gmail-events"


def message(subject="Permit issued", body="Your permit is ready.", to=GROUP):
    return {"id": "abc123", "internalDate": "1767225600000", "payload": {
        "mimeType": "text/plain", "headers": [
            {"name": "To", "value": to}, {"name": "Subject", "value": subject},
            {"name": "From", "value": "Permit Office <office@example.invalid>"},
            {"name": "Date", "value": "Wed, 31 Dec 2025 23:00:00 +0000"},
            {"name": "Message-ID", "value": "<demo@example.invalid>"}],
        "body": {"data": base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")}}}


class Response:
    def __init__(self, value, status=200):
        self.raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self.closed = False

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.raw), chunk_size):
            yield self.raw[offset:offset + chunk_size]

    def close(self):
        self.closed = True


def client_with(*responses, profile=True):
    values = ([Response({"emailAddress": MAILBOX})] if profile else []) + list(responses)
    session = Mock()
    session.request.side_effect = values
    client = GmailClient(MAILBOX, TOPIC, GROUP, Mock(), session)
    return client, session


class GmailTransportTests(unittest.TestCase):
    def test_profile_is_verified_before_watch_and_no_inbox_filter(self):
        client, session = client_with(Response({"historyId": "10", "expiration": "9999999999999"}))
        self.assertEqual(client.watch()["historyId"], "10")
        self.assertTrue(session.request.call_args_list[0].args[1].endswith("/profile"))
        self.assertEqual(session.request.call_args_list[1].kwargs["json"], {"topicName": TOPIC})
        for call in session.request.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["timeout"], (5, 10))
            self.assertTrue(call.args[1].startswith("https://gmail.googleapis.com/"))

    def test_wrong_mailbox_prevents_watch(self):
        client, session = client_with(Response({"emailAddress": "different@example.invalid"}), profile=False)
        with self.assertRaises(MailboxMismatch):
            client.watch()
        self.assertEqual(session.request.call_count, 1)

    def test_history_expiration_and_pagination(self):
        client, session = client_with(Response({}, status=404))
        with self.assertRaises(HistoryExpired):
            client.history("10", "opaque-page-token")
        self.assertEqual(session.request.call_args.kwargs["params"], {
            "startHistoryId": "10", "maxResults": 100,
            "historyTypes": "messageAdded", "pageToken": "opaque-page-token"})

    def test_other_mail_never_fetches_full_body(self):
        client, session = client_with(Response(message(to="personal@example.invalid")))
        item = client.message("abc123")
        self.assertEqual(item["reason"], "outside_selected_group")
        self.assertEqual(session.request.call_count, 2)
        self.assertNotIn("personal", json.dumps(item))
        self.assertNotIn("subject", item)

    def test_authentication_metadata_never_fetches_full_body(self):
        for subject in ("Reset your password", "Your verification code", "One-time passcode",
                        "=?UTF-8?B?UmVzZXQgeW91ciBwYXNzd29yZA==?="):
            with self.subTest(subject=subject):
                client, session = client_with(Response(message(subject=subject)))
                self.assertEqual(client.message("abc123")["reason"], "authentication_content")
                self.assertEqual(session.request.call_count, 2)

    def test_selected_group_metadata_then_full(self):
        email = message()
        client, session = client_with(Response(email), Response(email))
        result = client.message("abc123")
        self.assertTrue(result["review_required"])
        self.assertEqual([call.kwargs.get("params", {}).get("format")
                          for call in session.request.call_args_list], [None, "metadata", "full"])

    def test_deleted_message_becomes_content_free_marker(self):
        client, _ = client_with(Response({}, status=404))
        self.assertEqual(client.message("abc123")["reason"], "message_no_longer_available")

    def test_large_message_becomes_content_free_marker(self):
        client, _ = client_with(Response(message()), Response(b"x" * (1024 * 1024 + 1)))
        self.assertEqual(client.message("abc123")["reason"], "message_over_limit")

    def test_oversized_server_error_is_transient_not_a_skipped_message(self):
        for status in (429, 500):
            with self.subTest(status=status):
                client, _ = client_with(Response(b"x" * 70_000, status=status))
                with self.assertRaises(CloudError):
                    client.message("abc123")

    def test_permanent_malformed_messages_are_content_free_quarantines(self):
        client, session = client_with(Response(message(subject="=?not-a-real-charset?b?SGVsbG8=?=")))
        self.assertEqual(client.message("abc123")["reason"], "malformed_message")
        self.assertEqual(session.request.call_count, 2)
        for key, malformed in (("headers", "not-a-header-list"), ("parts", "not-a-part-list"),
                               ("body", {"data": "!!"})):
            full = message()
            full["payload"][key] = malformed
            client, _ = client_with(Response(message()), Response(full))
            item = client.message("abc123")
            self.assertEqual(item["reason"], "malformed_message")
            self.assertNotIn("subject", item)

    def test_invalid_identifier_never_enters_path(self):
        client, session = client_with()
        with self.assertRaises(CloudError):
            client.message("../credentials")
        self.assertEqual(session.request.call_count, 1)  # Only account verification.

    def test_redirects_are_rejected_and_closed(self):
        response = Response(b"secret upstream response", status=302)
        session = Mock()
        session.request.return_value = response
        with self.assertRaisesRegex(CloudError, "redirects"):
            _http_bytes(session, "GET", "https://gmail.googleapis.com/")
        self.assertTrue(response.closed)

    def test_errors_do_not_echo_network_details(self):
        session = Mock()
        session.request.side_effect = RuntimeError("secret-token-and-email")
        with self.assertRaises(CloudError) as caught:
            _http_bytes(session, "GET", "https://gmail.googleapis.com/")
        self.assertNotIn("secret", str(caught.exception))

    def test_oauth_destination_is_fixed(self):
        session = Mock()
        for url, method in (("https://other.example.invalid/token", "POST"), (TOKEN_URL, "GET")):
            with self.assertRaises(ConfigurationError):
                _TokenRequest(session)(url, method=method)
        session.request.assert_not_called()
        session.request.return_value = Response({"access_token": "synthetic-placeholder"})
        response = _TokenRequest(session)(TOKEN_URL, method="POST", body=b"synthetic")
        self.assertEqual(response.status, 200)
        self.assertFalse(session.request.call_args.kwargs["allow_redirects"])


class MessagePrivacyTests(unittest.TestCase):
    def test_routing_requires_exact_address_not_substring_or_from(self):
        self.assertFalse(_in_group({"to": ["not-" + GROUP]}, GROUP))
        self.assertFalse(_in_group({"from": [GROUP]}, GROUP))
        self.assertFalse(_in_group({"to": [GROUP + ".attacker.invalid"]}, GROUP))
        self.assertTrue(_in_group({"to": ["Permit Group <" + GROUP + ">"]}, GROUP))
        self.assertTrue(_in_group({"delivered-to": [GROUP.upper()]}, GROUP))
        self.assertTrue(_in_group({"list-id": ["Permit Group <permits.example.invalid>"]}, GROUP))
        self.assertFalse(_in_group({"list-id": ["<not-permits.example.invalid>"]}, GROUP))

    def test_provenance_distinguishes_from_and_receipt_time(self):
        item = sanitize_message(message(), "abc123", GROUP)
        self.assertTrue(item["review_required"])
        self.assertTrue(item["source"]["sender_is_unverified"])
        self.assertTrue(item["source"]["date_header_is_unverified"])
        self.assertEqual(item["source"]["timestamp_source"], "gmail_internalDate")
        self.assertEqual(item["source"]["received_at"], "2026-01-01T00:00:00+00:00")
        self.assertIn("Wed, 31 Dec", item["source"]["headers"]["date"][0])
        self.assertIn("no_event_inference", item["issues"])

    def test_normal_permit_login_guidance_is_retained(self):
        item = sanitize_message(message("Permit issued — log in to view", "Sign in to the permit portal to view your issued permit. Use your existing password."), "abc123", GROUP)
        self.assertTrue(item["review_required"])
        self.assertIn("permit portal", item["body"])

    def test_credential_body_is_excluded_without_content(self):
        for body in ("Your password is synthetic-only", "Password: synthetic-only",
                     "Verification code: 000000", "Click https://example.invalid/reset/start",
                     "Click https://example.invalid/view?token=synthetic-only",
                     "Use code 000000 to access your account"):
            with self.subTest(body=body):
                item = sanitize_message(message(body=body), "abc123", GROUP)
                self.assertEqual(item["reason"], "authentication_content")
                self.assertNotIn("synthetic-only", json.dumps(item))
                self.assertNotIn("source", item)

    def test_attachments_are_not_extracted(self):
        email = message()
        original = email["payload"]
        email["payload"] = {"mimeType": "multipart/mixed", "headers": original["headers"],
                            "parts": [original, {"mimeType": "text/plain", "filename": "attachment.txt",
                                                 "body": {"data": "not-valid-base64", "attachmentId": "synthetic"}}]}
        item = sanitize_message(email, "abc123", GROUP)
        self.assertEqual(item["body"], "Your permit is ready.")
        self.assertIn("attachments_not_fetched", item["issues"])

    def test_html_is_plaintext_and_entities_cannot_hide_auth_cues(self):
        email = message(body="<p>Permit <b>issued</b>.</p><script>not displayed</script>")
        email["payload"]["mimeType"] = "text/html"
        self.assertEqual(sanitize_message(email, "abc123", GROUP)["body"], "Permit issued.")
        email = message(body="<p>Your pass&#119;ord is synthetic-only</p>")
        email["payload"]["mimeType"] = "text/html"
        self.assertEqual(sanitize_message(email, "abc123", GROUP)["reason"], "authentication_content")

    def test_content_limit_handles_multibyte_and_json_escaping(self):
        item = sanitize_message(message(body=("\u2600\"\n" * 20_000)), "abc123", GROUP)
        self.assertLessEqual(len(json.dumps(item, ensure_ascii=False).encode()), MAX_ITEM_BYTES - 2000)
        self.assertIn("body_truncated", item["issues"])

    def test_bad_base64_or_missing_receipt_timestamp_fails_closed(self):
        email = message()
        email["payload"]["body"]["data"] = "!!"
        with self.assertRaises(CloudError):
            sanitize_message(email, "abc123", GROUP)
        email = message()
        email.pop("internalDate")
        with self.assertRaises(CloudError):
            sanitize_message(email, "abc123", GROUP)


class FakeSnapshot:
    def __init__(self, value):
        self.value, self.exists = copy.deepcopy(value), value is not None

    def to_dict(self):
        return copy.deepcopy(self.value)


class FakeRef:
    def __init__(self, database, path):
        self.database, self.path = database, path

    def collection(self, name):
        return FakeRef(self.database, self.path + "/" + name)

    def document(self, name):
        return FakeRef(self.database, self.path + "/" + name)

    def get(self, **kwargs):
        return FakeSnapshot(self.database.get(self.path))


class FakeTransaction:
    def __init__(self, database):
        self.database, self.writes = database, []

    def set(self, ref, value, merge):
        assert isinstance(merge, list), "Use exact field replacement, not recursive merge"
        self.writes.append((ref.path, copy.deepcopy(value), False))

    def create(self, ref, value):
        self.writes.append((ref.path, copy.deepcopy(value), True))

    def commit(self):
        for path, value, create in self.writes:
            if create and path in self.database:
                raise AssertionError("duplicate atomic create")
            self.database[path] = {**self.database.get(path, {}), **value}


class FirestoreLeaseTests(unittest.TestCase):
    def setUp(self):
        self.database = {}
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        client = SimpleNamespace(collection=lambda name: FakeRef(self.database, name))

        def run(callback):
            transaction = FakeTransaction(self.database)
            value = callback(transaction)
            transaction.commit()
            return value

        self.a = FirestoreStore(client, MAILBOX, clock=lambda: self.now, run_transaction=run)
        self.b = FirestoreStore(client, MAILBOX, clock=lambda: self.now, run_transaction=run)

    def test_message_insert_is_idempotent_and_preserves_original(self):
        with self.a.lease():
            item = sanitize_message(message(), "abc123", GROUP)
            self.assertTrue(self.a.put_message("abc123", item))
            self.assertFalse(self.a.put_message("abc123", {"status": "replacement"}))
        stored = self.database[self.a.ref.path + "/messages/abc123"]
        self.assertEqual(stored, item)
        self.assertNotIn(MAILBOX, self.a.ref.path)

    def test_operations_require_live_lease(self):
        for action in (self.a.load_state, lambda: self.a.save_state({}),
                       lambda: self.a.put_message("abc123", {}), self.a.renew):
            with self.assertRaises(Busy):
                action()

    def test_two_workers_cannot_own_same_live_lease(self):
        with self.a.lease():
            with self.assertRaises(Busy):
                with self.b.lease():
                    pass

    def test_expired_worker_cannot_overwrite_cursor_or_message(self):
        with self.a.lease():
            self.a.save_state({"processed_history_id": "10"})
            self.now += timedelta(seconds=121)
            with self.b.lease():
                self.b.save_state({"processed_history_id": "20"})
                for action in (self.a.assert_owned, self.a.renew,
                               lambda: self.a.save_state({"processed_history_id": "11"}),
                               lambda: self.a.put_message("abc123", {})):
                    with self.assertRaises(Busy):
                        action()
                self.assertEqual(self.b.load_state()["processed_history_id"], "20")
        self.assertNotIn(self.a.ref.path + "/messages/abc123", self.database)

    def test_renew_extends_lease_and_state_replaces_removed_fields(self):
        with self.a.lease():
            self.a.save_state({"processed_history_id": "10", "history_gap": {"reason": "demo"}})
            self.a.save_state({"processed_history_id": "20"})
            self.assertNotIn("history_gap", self.a.load_state())
            self.now += timedelta(seconds=100)
            self.a.renew()
            self.now += timedelta(seconds=100)
            self.a.assert_owned()

    def test_oversized_storage_item_is_refused(self):
        with self.a.lease():
            with self.assertRaises(CloudError):
                self.a.put_message("abc123", {"body": "x" * MAX_ITEM_BYTES})

    def test_poison_mail_is_quarantined_and_following_good_mail_advances_cursor(self):
        with self.a.lease():
            self.a.save_state({"processed_history_id": "10"})
        history = {"historyId": "20", "history": [{"id": "15", "messagesAdded": [
            {"message": {"id": "abc123"}}, {"message": {"id": "def456"}}]}]}
        gmail, _ = client_with(Response(history),
                               Response(message(subject="=?not-a-real-charset?b?SGVsbG8=?=")),
                               Response(message()), Response(message()))
        result = Listener(MAILBOX, gmail, self.a, clock=lambda: self.now).sync()
        self.assertEqual(result["messages_stored"], 2)
        self.assertEqual(self.database[self.a.ref.path]["state"]["processed_history_id"], "20")
        self.assertEqual(self.database[self.a.ref.path + "/messages/abc123"]["reason"], "malformed_message")
        self.assertTrue(self.database[self.a.ref.path + "/messages/def456"]["review_required"])

    def test_transient_error_preserves_cursor_and_does_not_skip_message(self):
        with self.a.lease():
            self.a.save_state({"processed_history_id": "10"})
        history = {"historyId": "20", "history": [{"id": "15", "messagesAdded": [{"message": {"id": "abc123"}}]}]}
        gmail, _ = client_with(Response(history), Response(b"x" * 70_000, status=500))
        with self.assertRaises(CloudError):
            Listener(MAILBOX, gmail, self.a, clock=lambda: self.now).sync()
        self.assertEqual(self.database[self.a.ref.path]["state"]["processed_history_id"], "10")
        self.assertNotIn(self.a.ref.path + "/messages/abc123", self.database)


class CredentialConfigurationTests(unittest.TestCase):
    def value(self):
        return {"type": "authorized_user", "token_uri": TOKEN_URL,
                "client_id": "synthetic-client", "client_secret": "synthetic-secret",
                "refresh_token": "synthetic-refresh", "scopes": [READONLY_SCOPE],
                "_sunbridge": {"project_id": "example-project", "mailbox": MAILBOX, "consent_mode": "internal"}}

    def test_bad_scopes_uri_and_provenance_fail_before_dependency_import(self):
        for field, bad in (("scopes", None), ("scopes", ["https://mail.google.com/"]),
                           ("token_uri", "https://other.example.invalid/token"),
                           ("type", "service_account"),
                           ("_sunbridge", {"project_id": "wrong-project", "mailbox": MAILBOX, "consent_mode": "internal"}),
                           ("_sunbridge", {"project_id": "example-project", "mailbox": "other@example.invalid", "consent_mode": "internal"})):
            value = self.value()
            value[field] = bad
            with self.subTest(field=field, bad=bad), patch("pathlib.Path.open", mock_open(read_data=json.dumps(value).encode())):
                with self.assertRaises(ConfigurationError) as caught:
                    load_credentials("/mounted/example", project="example-project", mailbox=MAILBOX)
                self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_exact_readonly_secret_constructs_only_fixed_google_credentials(self):
        constructor = Mock()
        module = ModuleType("google.oauth2.credentials")
        module.Credentials = constructor
        with patch.dict(sys.modules, {"google.oauth2.credentials": module}), patch("pathlib.Path.open", mock_open(read_data=json.dumps(self.value()).encode())):
            load_credentials("/mounted/example", project="example-project", mailbox=MAILBOX)
        self.assertEqual(constructor.call_args.kwargs["scopes"], [READONLY_SCOPE])
        self.assertEqual(constructor.call_args.kwargs["token_uri"], TOKEN_URL)
        self.assertIsNone(constructor.call_args.kwargs["token"])

    def test_runtime_uses_utc_datetime_clock_and_named_default_database(self):
        requests_module = ModuleType("requests")
        requests_module.Session = Mock()
        firestore = SimpleNamespace(Client=Mock())
        cloud = ModuleType("google.cloud")
        cloud.firestore = firestore
        environment = {"GOOGLE_CLOUD_PROJECT": "example-project", "GMAIL_MAILBOX": MAILBOX,
                       "GMAIL_TOPIC": TOPIC, "GMAIL_SUBSCRIPTION": SUBSCRIPTION,
                       "GMAIL_GROUP_ADDRESS": GROUP, "GMAIL_OAUTH_SECRET_JSON": "/mounted/example"}
        with patch.dict(sys.modules, {"requests": requests_module, "google.cloud": cloud}), patch.dict("os.environ", environment, clear=True), patch("sunbridge.gmail_cloud.load_credentials"), patch("sunbridge.gmail_cloud.FirestoreStore"):
            listener = _runtime_listener()
        self.assertIsNotNone(listener.clock().utcoffset())
        self.assertIsInstance(listener.clock(), datetime)
        firestore.Client.assert_called_once_with(project="example-project", database="(default)")
        self.assertFalse(requests_module.Session.return_value.trust_env)


@unittest.skipUnless(importlib.util.find_spec("flask"), "Optional Flask runtime is not installed")
class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.listener = Mock()
        self.app = create_app(lambda: self.listener, expected_subscription=SUBSCRIPTION)
        self.client = self.app.test_client()

    def test_routes_and_read_only_health(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.listener.assert_not_called()
        self.assertEqual(self.client.post("/renew").status_code, 200)
        self.listener.renew.assert_called_once_with()
        self.assertEqual(self.client.post("/catch-up").status_code, 200)
        self.listener.sync.assert_called_once_with()
        self.assertEqual(self.client.post("/push", json={"message": {}}).status_code, 200)
        self.listener.push.assert_called_once_with({"message": {}}, SUBSCRIPTION)
        self.assertEqual(self.client.get("/renew").status_code, 405)

    def test_invalid_push_acknowledged_without_processing(self):
        for payload in ("not JSON", "[]", "x" * 20_000):
            self.assertEqual(self.client.post("/push", data=payload, content_type="application/json").status_code, 204)
        self.listener.push.assert_not_called()
        self.listener.push.side_effect = InvalidNotification("sensitive-upstream-text")
        self.assertEqual(self.client.post("/push", json={}).status_code, 204)

    def test_retryable_and_operator_errors_are_not_acknowledged(self):
        for error in (Busy, NotInitialized, Incomplete, RecoveryRequired, MailboxMismatch, CloudError, RuntimeError):
            with self.subTest(error=error):
                self.listener.push.side_effect = error("sensitive-upstream-text")
                response = self.client.post("/push", json={})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("sensitive", response.get_data(as_text=True))
        self.listener.renew.side_effect = InvalidNotification("sensitive-upstream-text")
        self.assertEqual(self.client.post("/renew").status_code, 400)

    def test_notification_rejection_logs_only_fixed_reason_codes(self):
        reasons = {
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
        for message, reason in reasons.items():
            with self.subTest(reason=reason):
                self.listener.push.side_effect = InvalidNotification(message)
                with self.assertLogs(self.app.logger, level="WARNING") as logs:
                    response = self.client.post("/push", json={})
                self.assertEqual(response.status_code, 204)
                self.assertEqual(len(logs.records), 1)
                self.assertEqual(logs.records[0].getMessage(),
                                 "push_rejected_invalid_notification reason=" + reason)
                self.assertEqual(response.get_data(), b"")

    def test_unknown_notification_error_never_logs_exception_content(self):
        secret = "refresh_token=private-test-secret mailbox=private@example.test"

        class UnsafeArgument:
            def __str__(self):
                raise AssertionError("Exception argument must not be stringified")

        for arguments in ((secret,), ("Push message is invalid. " + secret,),
                          ("Push message is invalid.", secret), (),
                          ({"refresh_token": secret},), (UnsafeArgument(),)):
            with self.subTest(argument_types=tuple(type(value).__name__ for value in arguments)):
                self.listener.push.side_effect = InvalidNotification(*arguments)
                with self.assertLogs(self.app.logger, level="WARNING") as logs:
                    response = self.client.post("/push", json={"private_payload": secret})
                self.assertEqual(response.status_code, 204)
                self.assertEqual(len(logs.records), 1)
                self.assertEqual(logs.records[0].getMessage(),
                                 "push_rejected_invalid_notification reason=unknown")
                self.assertIsNone(logs.records[0].exc_info)
                self.assertNotIn(secret, " ".join(logs.output))
                self.assertEqual(response.get_data(), b"")


if __name__ == "__main__":
    unittest.main()
