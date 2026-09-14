"""Leased, new-mail-only Gmail history coordination; no transport or credentials.

Push payloads are wake-up hints, never processed cursors. A cursor is committed
only after every listed message has a durable, idempotent review/skip record.
History gaps deliberately require a separately authorized recovery workflow.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime, timezone

MAX_ENVELOPE_BYTES = 16 * 1024
MAX_NOTIFICATION_BYTES = 4096
MAX_PAGES = 100
MAX_MESSAGES = 10000
_HISTORY_ID = re.compile(r"[0-9]{1,32}\Z")
_MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SUBSCRIPTION = re.compile(r"projects/[^/\s]{1,128}/subscriptions/[^/\s]{1,255}\Z")
_NOTIFICATION_ENCODING = re.compile(r"(?:[A-Za-z0-9+/]+|[A-Za-z0-9_-]+)={0,2}\Z")


class ListenerError(RuntimeError):
    """Content-free, actionable listener failure."""


class InvalidNotification(ListenerError):
    """The push envelope is invalid or does not match its configuration."""


class MailboxMismatch(ListenerError):
    """The authenticated account is not the configured mailbox."""


class Busy(ListenerError):
    """Another worker holds the lease; redelivery must retry."""


class NotInitialized(ListenerError):
    """A successful initial watch is required before processing pushes."""


class HistoryExpired(ListenerError):
    """Transport signals Gmail's history-list HTTP 404 with this exception."""


class RecoveryRequired(ListenerError):
    """A visible history gap needs operator-authorized backfill."""


class Incomplete(ListenerError):
    """Processing stopped without advancing the durable cursor."""


def _history_id(value) -> bool:
    return isinstance(value, str) and _HISTORY_ID.fullmatch(value) is not None


def _plain_text(value, limit: int, *, empty: bool = False) -> bool:
    return (isinstance(value, str) and (empty or bool(value)) and len(value) <= limit
            and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value))


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise InvalidNotification("Notification JSON contains duplicate fields.")
        value[key] = item
    return value


def validate_notification(envelope, mailbox: str, expected_subscription: str) -> None:
    """Validate already-decoded Pub/Sub JSON, including a bounded inner payload.

    The HTTP boundary must independently bound its raw request body and verify
    the caller's identity. This validates message data, not authentication.
    """
    if (not isinstance(expected_subscription, str)
            or _SUBSCRIPTION.fullmatch(expected_subscription) is None):
        raise InvalidNotification("A valid expected subscription is required.")
    if (not isinstance(envelope, dict)
            or not set(envelope) <= {"message", "subscription", "deliveryAttempt"}
            or envelope.get("subscription") != expected_subscription):
        raise InvalidNotification("Push subscription or envelope is invalid.")
    # Pub/Sub uses zero when delivery counting has no dead-letter policy.
    if "deliveryAttempt" in envelope and (
            type(envelope["deliveryAttempt"]) is not int
            or not 0 <= envelope["deliveryAttempt"] <= 2147483647):
        raise InvalidNotification("Push delivery metadata is invalid.")
    message = envelope.get("message")
    allowed = {"data", "messageId", "message_id", "publishTime", "publish_time",
               "attributes", "orderingKey"}
    if not isinstance(message, dict) or not set(message) <= allowed:
        raise InvalidNotification("Push message is invalid.")
    for key in ("messageId", "message_id", "publishTime", "publish_time", "orderingKey"):
        if key in message and not _plain_text(message[key], 256, empty=key == "orderingKey"):
            raise InvalidNotification("Push message metadata is invalid.")
    attributes = message.get("attributes", {})
    if (not isinstance(attributes, dict) or len(attributes) > 100
            or any(not _plain_text(key, 256) or not _plain_text(value, 1024, empty=True)
                   for key, value in attributes.items())):
        raise InvalidNotification("Push attributes are invalid.")
    data = message.get("data")
    if not isinstance(data, str) or not 1 <= len(data) <= 4 * ((MAX_NOTIFICATION_BYTES + 2) // 3):
        raise InvalidNotification("Notification data is missing or exceeds its size limit.")
    try:
        encoded_envelope = json.dumps(envelope, ensure_ascii=True, allow_nan=False).encode("utf-8")
        if len(encoded_envelope) > MAX_ENVELOPE_BYTES:
            raise InvalidNotification("Push envelope exceeds its size limit.")
        # Gmail documents Base64URL; Pub/Sub also uses standard base64. Accept
        # either alphabet with full padding or none, never mixed alphabets,
        # partial/excess padding, whitespace, or noncanonical trailing bits.
        if _NOTIFICATION_ENCODING.fullmatch(data) is None:
            raise InvalidNotification("Notification encoding is invalid or too large.")
        urlsafe = "-" in data or "_" in data
        raw = base64.b64decode(data + "=" * (-len(data) % 4),
                               altchars=b"-_" if urlsafe else None, validate=True)
        canonical = (base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)).decode("ascii")
        if not data.endswith("="):
            canonical = canonical.rstrip("=")
        if len(raw) > MAX_NOTIFICATION_BYTES or canonical != data:
            raise InvalidNotification("Notification encoding is invalid or too large.")
        notification = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object)
    except (ValueError, TypeError, UnicodeError, binascii.Error, RecursionError):
        raise InvalidNotification("Notification must contain valid base64-encoded JSON.") from None
    if (not isinstance(notification, dict)
            or set(notification) != {"emailAddress", "historyId"}
            or notification.get("emailAddress") != mailbox
            or not _history_id(notification.get("historyId"))):
        raise InvalidNotification("Notification mailbox or history identifier is invalid.")


class Listener:
    """Coordinate a Gmail client and a mailbox-specific durable store.

    Store.lease() is a context manager and may raise Busy. The store must enforce
    ownership/fencing on writes. A yielded guard may implement renew() and
    assert_owned() for longer runs; a None guard is also supported. Client
    methods are profile(), watch(), history(start, page_token=None), and
    message(id). Returned message dictionaries are passed to storage unchanged.
    """

    def __init__(self, mailbox, gmail, store, clock=None, *, max_pages=MAX_PAGES,
                 max_messages=MAX_MESSAGES):
        if (not _plain_text(mailbox, 320) or mailbox.count("@") != 1
                or any(char.isspace() for char in mailbox)
                or any(not part for part in mailbox.split("@"))):
            raise ValueError("A configured mailbox is required.")
        for value in (max_pages, max_messages):
            if type(value) is not int or value < 1:
                raise ValueError("Processing limits must be positive integers.")
        self.mailbox = mailbox
        self.gmail = gmail
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_pages = max_pages
        self.max_messages = max_messages

    def _now(self):
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("The listener clock must return a timezone-aware datetime.")
        return now.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _assert_lease(guard):
        if guard is not None and callable(getattr(guard, "assert_owned", None)):
            guard.assert_owned()

    @classmethod
    def _keep_lease(cls, guard):
        cls._assert_lease(guard)
        if guard is not None and callable(getattr(guard, "renew", None)):
            guard.renew()
        cls._assert_lease(guard)

    def _state(self):
        state = self.store.load_state()
        if not isinstance(state, dict):
            raise Incomplete("Stored listener state is invalid; no cursor was changed.")
        state = dict(state)
        if "processed_history_id" in state and not _history_id(state["processed_history_id"]):
            raise Incomplete("Stored cursor is invalid; operator review is required.")
        if "resync_required" in state and type(state["resync_required"]) is not bool:
            raise Incomplete("Stored recovery flag is invalid; operator review is required.")
        if "processed_history_id" not in state and (
                state.get("resync_required") or any(key in state for key in (
                    "initialized_at", "watch_history_id", "watch_expiration",
                    "last_renewal", "last_sync", "history_gap"))):
            raise Incomplete("An initialized listener is missing its cursor; operator review is required.")
        return state

    def _check_mailbox(self, guard):
        self._keep_lease(guard)
        profile = self.gmail.profile()
        self._assert_lease(guard)
        if not isinstance(profile, dict) or profile.get("emailAddress") != self.mailbox:
            raise MailboxMismatch("Authenticated mailbox does not match listener configuration.")

    def renew(self):
        """Renew the watch; only the first successful watch establishes a cursor."""
        with self.store.lease() as guard:
            state = self._state()
            self._check_mailbox(guard)
            self._keep_lease(guard)
            watch = self.gmail.watch()
            self._assert_lease(guard)
            if (not isinstance(watch, dict) or not _history_id(watch.get("historyId"))
                    or not _history_id(watch.get("expiration"))):
                raise Incomplete("Watch response is invalid; no cursor was changed.")
            now = self._now()
            if int(watch["expiration"]) <= int(datetime.fromisoformat(now).timestamp() * 1000):
                raise Incomplete("Watch is already expired; no cursor was changed.")
            initialized = "processed_history_id" not in state
            if initialized:
                state["processed_history_id"] = watch["historyId"]
                state["initialized_at"] = now
                state.setdefault("resync_required", False)
            state.update(watch_history_id=watch["historyId"],
                         watch_expiration=watch["expiration"], last_renewal=now)
            self._keep_lease(guard)
            self.store.save_state(state)
            return {"status": "initialized" if initialized else "renewed",
                    "initialized": initialized,
                    "resync_required": bool(state.get("resync_required"))}

    def push(self, envelope, expected_subscription):
        """Validate a wake-up hint and synchronize from the durable cursor."""
        validate_notification(envelope, self.mailbox, expected_subscription)
        return self.sync()

    def sync(self):
        """Fully drain bounded messagesAdded history, or preserve the old cursor."""
        with self.store.lease() as guard:
            state = self._state()
            if state.get("resync_required"):
                raise RecoveryRequired("History gap requires operator-authorized backfill.")
            if "processed_history_id" not in state:
                raise NotInitialized("Initialize the watch before processing notifications.")
            self._check_mailbox(guard)
            start = state["processed_history_id"]
            page_token = None
            tokens, seen = set(), set()
            pages = additions = stored = duplicates = 0
            final_cursor = start
            while True:
                if pages >= self.max_pages:
                    raise Incomplete("History page limit reached; cursor was not advanced.")
                self._keep_lease(guard)
                try:
                    page = self.gmail.history(start, page_token=page_token)
                except HistoryExpired:
                    self._keep_lease(guard)
                    state["resync_required"] = True
                    state["history_gap"] = {
                        "detected_at": self._now(), "start_history_id": start,
                        "reason": "gmail_history_expired",
                        "recovery": "operator_authorized_backfill_required",
                    }
                    self.store.save_state(state)
                    raise RecoveryRequired("History expired; operator-authorized backfill is required.") from None
                self._assert_lease(guard)
                pages += 1
                if (not isinstance(page, dict) or not _history_id(page.get("historyId"))
                        or int(page["historyId"]) < int(final_cursor)):
                    raise Incomplete("History page cursor is invalid; cursor was not advanced.")
                final_cursor = page["historyId"]
                history = page.get("history", [])
                if not isinstance(history, list):
                    raise Incomplete("History page is invalid; cursor was not advanced.")
                if len(history) > self.max_messages:
                    raise Incomplete("History record limit reached; cursor was not advanced.")
                for record in history:
                    if not isinstance(record, dict):
                        raise Incomplete("History record is invalid; cursor was not advanced.")
                    if "id" in record and (not _history_id(record["id"])
                            or not int(start) < int(record["id"]) <= int(final_cursor)):
                        raise Incomplete("History record cursor is invalid; cursor was not advanced.")
                    added = record.get("messagesAdded", [])
                    if not isinstance(added, list):
                        raise Incomplete("Added-message history is invalid; cursor was not advanced.")
                    additions += len(added)
                    if additions > self.max_messages:
                        raise Incomplete("History message limit reached; cursor was not advanced.")
                    for entry in added:
                        message = entry.get("message") if isinstance(entry, dict) else None
                        message_id = message.get("id") if isinstance(message, dict) else None
                        if not isinstance(message_id, str) or _MESSAGE_ID.fullmatch(message_id) is None:
                            raise Incomplete("History message identifier is invalid; cursor was not advanced.")
                        if message_id in seen:
                            continue
                        seen.add(message_id)
                        self._keep_lease(guard)
                        item = self.gmail.message(message_id)
                        self._assert_lease(guard)
                        if not isinstance(item, dict) or not item:
                            raise Incomplete("A durable review or skip item is required; cursor was not advanced.")
                        self._keep_lease(guard)
                        inserted = self.store.put_message(message_id, item)
                        if type(inserted) is not bool:
                            raise Incomplete("Message storage did not confirm durability; cursor was not advanced.")
                        stored += int(inserted)
                        duplicates += int(not inserted)
                next_token = page.get("nextPageToken")
                if next_token is None:
                    break
                if not _plain_text(next_token, 2048) or next_token in tokens:
                    raise Incomplete("History pagination is invalid; cursor was not advanced.")
                tokens.add(next_token)
                page_token = next_token
            state.update(processed_history_id=final_cursor, last_sync=self._now())
            result = {"status": "synced", "pages": pages, "messages_seen": len(seen),
                      "messages_stored": stored, "messages_duplicate": duplicates}
            state["last_sync_result"] = dict(result)
            self._keep_lease(guard)
            self.store.save_state(state)
            return result
