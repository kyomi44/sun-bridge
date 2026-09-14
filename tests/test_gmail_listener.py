"""Synthetic, network-free Gmail history and durable-cursor regression tests."""
import base64
import copy
import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from sunbridge.gmail_listener import (
    Busy, HistoryExpired, Incomplete, InvalidNotification, Listener,
    MailboxMismatch, NotInitialized, RecoveryRequired, validate_notification,
)

MAILBOX = "listener@example.invalid"
SUBSCRIPTION = "projects/example-project/subscriptions/example-push"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
EXPIRATION = "1767830400000"


def envelope(history_id="110", mailbox=MAILBOX):
    data = json.dumps({"emailAddress": mailbox, "historyId": history_id}).encode()
    return {"subscription": SUBSCRIPTION, "message": {
        "data": base64.b64encode(data).decode("ascii"), "messageId": "example-push-id",
        "publishTime": "2026-01-01T00:00:00Z",
    }}


def page(cursor="110", ids=("m1",), next_token=None):
    result = {"historyId": cursor, "history": [{"id": cursor,
        "messagesAdded": [{"message": {"id": item}} for item in ids]}] if ids else []}
    if next_token is not None:
        result["nextPageToken"] = next_token
    return result


class MemoryStore:
    def __init__(self, initialized=True):
        self.state = {"processed_history_id": "100"} if initialized else {}
        self.items = {}
        self.active = False
        self.save_calls = 0
        self.fail_put = None
        self.fail_save = False
        self.renew_calls = 0
        self.lost = False

    @contextmanager
    def lease(self):
        if self.active:
            raise Busy("Listener is busy.")
        self.active = True
        try:
            yield self
        finally:
            self.active = False

    def assert_owned(self):
        if not self.active or self.lost:
            raise Busy("Listener lease is no longer held.")

    def renew(self):
        self.assert_owned()
        self.renew_calls += 1

    def load_state(self):
        self.assert_owned()
        return copy.deepcopy(self.state)

    def save_state(self, state):
        self.assert_owned()
        if self.fail_save:
            raise OSError("Synthetic durable-state failure.")
        self.state = copy.deepcopy(state)
        self.save_calls += 1

    def put_message(self, message_id, item):
        self.assert_owned()
        if message_id == self.fail_put:
            raise OSError("Synthetic durable-item failure.")
        if message_id in self.items:
            return False
        self.items[message_id] = copy.deepcopy(item)
        return True


class FakeGmail:
    def __init__(self, store):
        self.store = store
        self.account = MAILBOX
        self.profile_cursor = "999"
        self.watch_result = {"historyId": "105", "expiration": EXPIRATION}
        self.pages = {None: page()}
        self.history_calls = []
        self.message_calls = []
        self.watch_hook = None
        self.message_hook = None
        self.fail_message = None
        self.watch_calls = 0
        self.profile_calls = 0

    def profile(self):
        self.store.assert_owned()
        self.profile_calls += 1
        return {"emailAddress": self.account, "historyId": self.profile_cursor}

    def watch(self):
        self.store.assert_owned()
        self.watch_calls += 1
        if self.watch_hook:
            self.watch_hook()
        return self.watch_result

    def history(self, start_history_id, page_token=None):
        self.store.assert_owned()
        self.history_calls.append((start_history_id, page_token))
        result = self.pages[page_token]
        if isinstance(result, Exception):
            raise result
        return result

    def message(self, message_id):
        self.store.assert_owned()
        self.message_calls.append(message_id)
        if self.message_hook:
            self.message_hook()
        if message_id == self.fail_message:
            raise OSError("Synthetic Gmail failure.")
        return {"status": "review_required", "review_required": True,
                "source": {"gmail_message_id": message_id}, "body": "Fictional review text."}


class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.gmail = FakeGmail(self.store)
        self.listener = Listener(MAILBOX, self.gmail, self.store, clock=lambda: NOW)

    def test_bootstrap_uses_watch_anchor_not_profile_and_does_not_import_old_mail(self):
        self.store.state = {}
        result = self.listener.renew()
        self.assertEqual(result["status"], "initialized")
        self.assertEqual(self.store.state["processed_history_id"], "105")
        self.assertEqual(self.store.state["watch_history_id"], "105")
        self.assertEqual(self.store.state["last_renewal"], NOW.isoformat())
        self.assertFalse(self.store.state["resync_required"])
        self.assertEqual(self.gmail.history_calls, [])
        self.assertEqual(self.gmail.message_calls, [])

    def test_renewal_preserves_cursor_across_all_watch_results(self):
        for cursor in ("150", "200", "100", "99"):
            self.gmail.watch_result["historyId"] = cursor
            self.assertEqual(self.listener.renew()["status"], "renewed")
            self.assertEqual(self.store.state["processed_history_id"], "100")
            self.assertEqual(self.store.state["watch_history_id"], cursor)
        self.assertEqual(self.gmail.history_calls, [])

    def test_push_racing_bootstrap_is_retryable_then_reads_from_anchor(self):
        self.store.state = {}
        def racing_push():
            with self.assertRaises(Busy):
                self.listener.push(envelope(), SUBSCRIPTION)
        self.gmail.watch_hook = racing_push
        self.listener.renew()
        self.listener.push(envelope(), SUBSCRIPTION)
        self.assertEqual(self.gmail.history_calls, [("105", None)])
        self.assertEqual(self.store.state["processed_history_id"], "110")

    def test_push_before_bootstrap_does_not_initialize_from_notification(self):
        self.store.state = {}
        with self.assertRaises(NotInitialized):
            self.listener.push(envelope("999999"), SUBSCRIPTION)
        self.assertEqual(self.store.state, {})
        self.assertEqual(self.gmail.history_calls, [])

    def test_sync_multiple_pages_only_messages_added_and_one_fetch_per_unique_id(self):
        first = page("110", ("m1", "m1"), "next")
        first["history"][0].update(messages=[{"id": "not-added"}],
            labelsAdded=[{"message": {"id": "label-only"}}])
        self.gmail.pages = {None: first, "next": page("120", ("m1", "m2"))}
        result = self.listener.sync()
        self.assertEqual(self.gmail.history_calls, [("100", None), ("100", "next")])
        self.assertEqual(self.gmail.message_calls, ["m1", "m2"])
        self.assertEqual(self.store.state["processed_history_id"], "120")
        self.assertEqual(self.store.save_calls, 1)
        self.assertEqual(result, {"status": "synced", "pages": 2, "messages_seen": 2,
                                  "messages_stored": 2, "messages_duplicate": 0})
        self.assertNotIn(MAILBOX, json.dumps(result))
        self.assertNotIn("Fictional review text", json.dumps(result))

    def test_partial_message_failure_keeps_cursor_and_retry_deduplicates(self):
        self.gmail.pages = {None: page(ids=("m1", "m2"))}
        self.gmail.fail_message = "m2"
        with self.assertRaises(OSError):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(set(self.store.items), {"m1"})
        self.gmail.fail_message = None
        result = self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "110")
        self.assertEqual(set(self.store.items), {"m1", "m2"})
        self.assertEqual(result["messages_stored"], 1)
        self.assertEqual(result["messages_duplicate"], 1)

    def test_store_failure_does_not_advance_cursor(self):
        self.store.fail_put = "m1"
        with self.assertRaises(OSError):
            self.listener.sync()
        self.assertEqual(self.store.state, {"processed_history_id": "100"})
        self.assertEqual(self.store.save_calls, 0)

    def test_final_state_failure_keeps_durable_items_and_retry_is_idempotent(self):
        self.store.fail_save = True
        with self.assertRaises(OSError):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(set(self.store.items), {"m1"})
        self.store.fail_save = False
        self.assertEqual(self.listener.sync()["messages_duplicate"], 1)
        self.assertEqual(self.store.state["processed_history_id"], "110")

    def test_page_failure_does_not_advance_partially_processed_cursor(self):
        self.gmail.pages = {None: page(next_token="next"), "next": OSError("Synthetic failure.")}
        with self.assertRaises(OSError):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(set(self.store.items), {"m1"})

    def test_old_duplicate_and_future_notification_ids_are_only_wakeup_hints(self):
        self.listener.push(envelope("50000"), SUBSCRIPTION)
        self.gmail.pages = {None: page("110", ())}
        for cursor in ("1", "110", "1"):
            self.listener.push(envelope(cursor), SUBSCRIPTION)
        self.assertEqual(self.store.state["processed_history_id"], "110")
        self.assertEqual(self.gmail.history_calls,
                         [("100", None), ("110", None), ("110", None), ("110", None)])
        self.assertEqual(len(self.store.items), 1)

    def test_history_404_marks_persistent_visible_gap_without_reset(self):
        self.gmail.pages = {None: HistoryExpired("Synthetic expired history.")}
        with self.assertRaises(RecoveryRequired):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertTrue(self.store.state["resync_required"])
        self.assertEqual(self.store.state["history_gap"], {
            "detected_at": NOW.isoformat(), "start_history_id": "100",
            "reason": "gmail_history_expired", "recovery": "operator_authorized_backfill_required",
        })
        self.gmail.pages = {None: page("200", ())}
        with self.assertRaises(RecoveryRequired):
            self.listener.push(envelope("200"), SUBSCRIPTION)
        self.assertEqual(len(self.gmail.history_calls), 1)
        self.gmail.watch_result["historyId"] = "200"
        self.assertTrue(self.listener.renew()["resync_required"])
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(self.store.state["history_gap"]["start_history_id"], "100")

    def test_expiry_after_partial_pages_preserves_items_and_original_cursor(self):
        self.gmail.pages = {None: page(next_token="next"), "next": HistoryExpired()}
        with self.assertRaises(RecoveryRequired):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(set(self.store.items), {"m1"})
        self.assertTrue(self.store.state["resync_required"])

    def test_page_bound_keeps_cursor_even_with_durable_first_page(self):
        listener = Listener(MAILBOX, self.gmail, self.store, clock=lambda: NOW, max_pages=1)
        self.gmail.pages = {None: page(next_token="next"), "next": page("120", ("m2",))}
        with self.assertRaisesRegex(Incomplete, "page limit"):
            listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(self.gmail.history_calls, [("100", None)])
        self.assertEqual(set(self.store.items), {"m1"})

    def test_message_bound_counts_all_added_entries_even_duplicates(self):
        listener = Listener(MAILBOX, self.gmail, self.store, clock=lambda: NOW, max_messages=1)
        self.gmail.pages = {None: page(ids=("m1", "m1"))}
        with self.assertRaisesRegex(Incomplete, "message limit"):
            listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(self.gmail.message_calls, [])

    def test_message_bound_is_cumulative_across_pages(self):
        listener = Listener(MAILBOX, self.gmail, self.store, clock=lambda: NOW, max_messages=1)
        self.gmail.pages = {None: page(next_token="next"), "next": page("120", ("m2",))}
        with self.assertRaises(Incomplete):
            listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")
        self.assertEqual(set(self.store.items), {"m1"})

    def test_repeated_page_token_fails_without_advancing(self):
        self.gmail.pages = {None: page(next_token="loop"), "loop": page("120", (), "loop")}
        with self.assertRaisesRegex(Incomplete, "pagination"):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")

    def test_bad_history_responses_fail_closed(self):
        invalid = [None, {}, {"historyId": 110}, page("99"),
                   {"historyId": "110", "history": None},
                   {"historyId": "110", "history": [None]},
                   {"historyId": "110", "history": [{"messagesAdded": None}]},
                   {"historyId": "110", "history": [{"messagesAdded": [{}]}]},
                   page(ids=("../unsafe",)), page(next_token="")]
        for response in invalid:
            with self.subTest(response=response):
                self.gmail.pages = {None: response}
                with self.assertRaises(Incomplete):
                    self.listener.sync()
                self.assertEqual(self.store.state["processed_history_id"], "100")

    def test_history_record_cannot_be_outside_requested_range(self):
        for cursor in ("100", "111", "bad"):
            with self.subTest(cursor=cursor):
                response = page()
                response["history"][0]["id"] = cursor
                self.gmail.pages = {None: response}
                with self.assertRaises(Incomplete):
                    self.listener.sync()
                self.assertEqual(self.store.state["processed_history_id"], "100")

    def test_lost_lease_after_fetch_blocks_storage_and_cursor(self):
        self.gmail.message_hook = lambda: setattr(self.store, "lost", True)
        with self.assertRaises(Busy):
            self.listener.sync()
        self.assertEqual(self.store.items, {})
        self.assertEqual(self.store.state["processed_history_id"], "100")

    def test_wrong_authenticated_mailbox_cannot_watch_or_read_history(self):
        self.gmail.account = "different@example.invalid"
        for operation in (self.listener.renew, self.listener.sync):
            with self.assertRaises(MailboxMismatch):
                operation()
        self.assertEqual(self.gmail.watch_calls, 0)
        self.assertEqual(self.gmail.history_calls, [])
        self.assertEqual(self.store.state["processed_history_id"], "100")

    def test_invalid_existing_cursor_cannot_silently_reinitialize(self):
        for value in (None, "", "-1", "invalid", 100, True):
            with self.subTest(cursor=value):
                self.store.state = {"processed_history_id": value}
                with self.assertRaises(Incomplete):
                    self.listener.renew()
                self.assertEqual(self.store.state["processed_history_id"], value)
        self.assertEqual(self.gmail.watch_calls, 0)

    def test_missing_cursor_or_invalid_recovery_flag_cannot_silently_reinitialize(self):
        for state in ({"watch_history_id": "150"}, {"resync_required": True},
                      {"history_gap": {}}, {"processed_history_id": "100", "resync_required": "false"}):
            with self.subTest(state=state):
                self.store.state = copy.deepcopy(state)
                with self.assertRaises(Incomplete):
                    self.listener.renew()
                self.assertEqual(self.store.state, state)
        self.assertEqual(self.gmail.watch_calls, 0)

    def test_renewal_cannot_race_active_sync(self):
        def racing_renewal():
            with self.assertRaises(Busy):
                self.listener.renew()
        self.gmail.message_hook = racing_renewal
        self.listener.sync()
        self.assertEqual(self.gmail.watch_calls, 0)
        self.assertEqual(self.store.state["processed_history_id"], "110")

    def test_context_manager_without_optional_guard_is_supported(self):
        original_lease = self.store.lease
        @contextmanager
        def plain_lease():
            with original_lease():
                yield None
        self.store.lease = plain_lease
        self.listener.renew()
        self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "110")
        self.assertEqual(set(self.store.items), {"m1"})

    def test_invalid_or_expired_watch_does_not_initialize(self):
        self.store.state = {}
        for response in ({}, {"historyId": "100", "expiration": "1"},
                         {"historyId": 100, "expiration": EXPIRATION},
                         {"historyId": "100", "expiration": "bad"}):
            with self.subTest(response=response):
                self.gmail.watch_result = response
                with self.assertRaises(Incomplete):
                    self.listener.renew()
                self.assertEqual(self.store.state, {})

    def test_skip_item_is_durable_before_advancing(self):
        self.gmail.message = lambda message_id: {"status": "excluded", "reason": "filtered",
                                                 "review_required": False}
        self.listener.sync()
        self.assertEqual(self.store.items["m1"]["status"], "excluded")
        self.assertEqual(self.store.state["processed_history_id"], "110")

    def test_missing_item_or_nonboolean_storage_result_fails_closed(self):
        for item in (None, {}, "not-a-review-item"):
            with self.subTest(item=item):
                self.gmail.message = lambda message_id: item
                with self.assertRaises(Incomplete):
                    self.listener.sync()
                self.assertEqual(self.store.state["processed_history_id"], "100")
        self.gmail.message = lambda message_id: {"status": "excluded"}
        self.store.put_message = lambda message_id, item: None
        with self.assertRaises(Incomplete):
            self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "100")

    def test_empty_history_advances_to_returned_api_cursor(self):
        self.gmail.pages = {None: {"historyId": "125"}}
        result = self.listener.sync()
        self.assertEqual(self.store.state["processed_history_id"], "125")
        self.assertEqual(result["messages_seen"], 0)

    def test_constructor_and_clock_validation(self):
        for mailbox in (None, "", "no-domain", "a@", "@example.invalid", "a b@example.invalid"):
            with self.subTest(mailbox=mailbox), self.assertRaises(ValueError):
                Listener(mailbox, self.gmail, self.store)
        for value in (0, -1, True, 1.5):
            with self.subTest(limit=value), self.assertRaises(ValueError):
                Listener(MAILBOX, self.gmail, self.store, max_pages=value)
        self.listener.clock = lambda: datetime(2026, 1, 1)
        with self.assertRaises(ValueError):
            self.listener.renew()
        self.assertEqual(self.store.state["processed_history_id"], "100")


class NotificationTests(unittest.TestCase):
    def test_standard_metadata_is_accepted(self):
        value = envelope()
        value["deliveryAttempt"] = 1
        value["message"]["attributes"] = {"example": ""}
        value["message"]["orderingKey"] = ""
        self.assertIsNone(validate_notification(value, MAILBOX, SUBSCRIPTION))

    def test_delivery_attempt_zero_without_dead_letter_policy_is_accepted(self):
        value = envelope()
        value["deliveryAttempt"] = 0
        self.assertIsNone(validate_notification(value, MAILBOX, SUBSCRIPTION))

    def test_official_gmail_push_example_is_accepted(self):
        # https://developers.google.com/workspace/gmail/api/guides/push
        value = envelope(mailbox="user@example.com")
        value["message"]["data"] = (
            "eyJlbWFpbEFkZHJlc3MiOiAidXNlckBleGFtcGxlLmNvbSIsICJoaXN0b3J5SWQi"
            "OiAiMTIzNDU2Nzg5MCJ9"
        )
        self.assertIsNone(validate_notification(value, "user@example.com", SUBSCRIPTION))

    def test_standard_and_urlsafe_encoding_with_and_without_padding(self):
        # This synthetic local part ensures the standard encoding has both
        # alphabet-specific characters; each history length changes padding.
        mailbox = "a??~~~@example.invalid"
        for history in ("1", "11", "111"):
            raw = json.dumps({"emailAddress": mailbox, "historyId": history}).encode()
            self.assertIn(b"+", base64.b64encode(raw))
            self.assertIn(b"/", base64.b64encode(raw))
            for encode in (base64.b64encode, base64.urlsafe_b64encode):
                for padded in (True, False):
                    data = encode(raw).decode("ascii")
                    if not padded:
                        data = data.rstrip("=")
                    value = envelope(mailbox=mailbox)
                    value["message"]["data"] = data
                    with self.subTest(history=history, encoder=encode.__name__, padded=padded):
                        self.assertIsNone(validate_notification(value, mailbox, SUBSCRIPTION))

    def test_mixed_alphabets_and_noncanonical_padding_or_bits_are_rejected(self):
        mailbox = "a??~~~@example.invalid"
        raw = json.dumps({"emailAddress": mailbox, "historyId": "111"}).encode()
        standard = base64.b64encode(raw).decode("ascii")
        self.assertTrue(standard.endswith("="))
        invalid_data = [standard.replace("+", "-"), standard.replace("/", "_"),
                        standard + "=", standard + "\n", " " + standard,
                        standard.rstrip("=") + "===", "A", "===="]
        for encode in (base64.b64encode, base64.urlsafe_b64encode):
            # Two padding characters are required for this payload. Changing
            # the low bits still decodes to the same bytes, but is noncanonical.
            canonical = encode(raw + b"  ").decode("ascii")
            self.assertTrue(canonical.endswith("=="))
            alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            index = alphabet.index(canonical[-3])
            noncanonical = canonical[:-3] + alphabet[index + 1] + "=="
            invalid_data.extend((canonical[:-1], noncanonical, noncanonical.rstrip("=")))
        for data in invalid_data:
            value = envelope(mailbox=mailbox)
            value["message"]["data"] = data
            with self.subTest(data=data), self.assertRaises(InvalidNotification):
                validate_notification(value, mailbox, SUBSCRIPTION)

    def test_decoded_size_limit_is_enforced_with_optional_padding(self):
        raw = json.dumps({"emailAddress": MAILBOX, "historyId": "110"}).encode()
        for length in (4096, 4097, 4098):
            # All three lengths fit the encoded-character limit, so the
            # decoded bound must still reject the latter two independently.
            padded_json = raw + b" " * (length - len(raw))
            for encode in (base64.b64encode, base64.urlsafe_b64encode):
                for padded in (True, False):
                    data = encode(padded_json).decode("ascii")
                    if not padded:
                        data = data.rstrip("=")
                    value = envelope()
                    value["message"]["data"] = data
                    with self.subTest(length=length, encoder=encode.__name__, padded=padded):
                        if length == 4096:
                            self.assertIsNone(validate_notification(value, MAILBOX, SUBSCRIPTION))
                        else:
                            with self.assertRaises(InvalidNotification):
                                validate_notification(value, MAILBOX, SUBSCRIPTION)

    def test_wrong_subscription_and_mailbox_and_invalid_history_rejected(self):
        invalid = [envelope(mailbox="other@example.invalid"), envelope(mailbox=MAILBOX.upper())]
        for history in (110, True, None, "", "-1", "1.1", "1e2", "١١٠", "1" * 33):
            invalid.append(envelope(history))
        value = envelope()
        value["subscription"] = SUBSCRIPTION + "-other"
        invalid.append(value)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(InvalidNotification):
                validate_notification(value, MAILBOX, SUBSCRIPTION)

    def test_bad_base64_json_duplicate_keys_and_extra_fields_rejected(self):
        invalid_data = ["not base64!", "", "a" * 6000,
                        base64.b64encode(b"not-json").decode(),
                        base64.b64encode(b"\xff").decode(),
                        base64.b64encode(b"[]").decode(),
                        base64.b64encode(b'{"emailAddress":"listener@example.invalid","historyId":"110","historyId":"111"}').decode(),
                        base64.b64encode(b'{"emailAddress":"listener@example.invalid","historyId":"110","extra":1}').decode()]
        for data in invalid_data:
            value = envelope()
            value["message"]["data"] = data
            with self.subTest(data=data[:20]), self.assertRaises(InvalidNotification):
                validate_notification(value, MAILBOX, SUBSCRIPTION)

    def test_invalid_envelope_metadata_and_oversize_rejected(self):
        invalid = [None, [], {}, {"subscription": SUBSCRIPTION, "message": []}]
        for key, item in (("messageId", 123), ("attributes", []),
                          ("attributes", {"x": {"nested": "invalid"}}),
                          ("publishTime", "invalid\nmetadata"), ("unknown", "value"),
                          ("attributes", {str(i): "x" * 1024 for i in range(20)})):
            value = envelope()
            value["message"][key] = item
            invalid.append(value)
        for attempt in (True, -1, "1", 2147483648):
            value = envelope()
            value["deliveryAttempt"] = attempt
            invalid.append(value)
        for value in invalid:
            with self.subTest(value=type(value)), self.assertRaises(InvalidNotification):
                validate_notification(value, MAILBOX, SUBSCRIPTION)

    def test_invalid_notification_never_reaches_lease_or_gmail(self):
        store = MemoryStore()
        gmail = FakeGmail(store)
        listener = Listener(MAILBOX, gmail, store, clock=lambda: NOW)
        store.active = True
        with self.assertRaises(InvalidNotification):
            listener.push(envelope(mailbox="wrong@example.invalid"), SUBSCRIPTION)
        self.assertEqual(gmail.profile_calls, 0)
        self.assertEqual(gmail.history_calls, [])


if __name__ == "__main__":
    unittest.main()
