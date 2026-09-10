"""Bounded local mail import. No network, attachment extraction, or AHJ inference."""
from __future__ import annotations

import hashlib
import os
import re
import stat
from datetime import timezone
from email import policy
from email.errors import MessageError
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_MESSAGE_BYTES = 5 * 1024 * 1024
MAX_MESSAGES = 1000
MAX_MIME_PARTS = 200


class MailImportError(ValueError):
    """Actionable import failure without echoing message content."""


class _PlainHTML(HTMLParser):
    blocked = {"script", "style", "iframe", "object", "template", "svg", "math"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.hidden.append(tag)
        if not self.hidden and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.text.append("\n")

    def handle_startendtag(self, tag, attrs):
        if not self.hidden and tag == "br":
            self.text.append("\n")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in {"p", "div", "li", "tr"}:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def _read_file(path: Path, remaining: int) -> bytes:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise MailImportError("Mail input cannot use symbolic links. Copy the export to a regular private path.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise MailImportError("Mail input must be a regular file.")
            raw = source.read(remaining + 1)
    except OSError:
        raise MailImportError("Could not read mail input. Check that the local file exists and is readable.") from None
    if len(raw) > remaining:
        raise MailImportError("Mail input exceeds the 25 MiB total limit. Export a smaller batch.")
    return raw


def _parse(raw: bytes, ahj_id: str) -> dict:
    if not raw.strip():
        raise MailImportError("An empty message was found. Remove empty files or repair the export.")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise MailImportError("A message exceeds the 5 MiB limit. Export a smaller message without large attachments.")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except (ValueError, RecursionError):
        raise MailImportError("A message could not be parsed. Re-export it as a standard EML file.") from None
    issues = ["ahj_assigned_by_operator_not_verified", "date_header_is_not_receipt_time"]

    def header(name: str) -> str:
        values = message.get_all(name, [])
        if len(values) > 1:
            issues.append("duplicate_" + name.lower().replace("-", "_") + "_header")
        if not values:
            return ""
        item = values[0]
        if getattr(item, "defects", ()):
            issues.append("malformed_header")
        value = str(item)
        if "\ufffd" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            issues.append("header_decode_replacement")
            value = value.encode("utf-8", "replace").decode("utf-8")
        return re.sub(r"[\r\n]+\s*", " ", value).strip()

    sender, subject, message_id, date_header = (header(name) for name in ("From", "Subject", "Message-ID", "Date"))
    if not sender:
        issues.append("missing_sender")
    if not subject:
        issues.append("missing_subject")
    if not message_id:
        message_id = "synthetic-sha256-" + hashlib.sha256(raw).hexdigest() + "@example.invalid"
        issues.append("synthetic_message_id_from_bytes")
    date_header_at = None
    if date_header:
        try:
            date = parsedate_to_datetime(date_header)
            if date.tzinfo is None:
                raise ValueError()
            date_header_at = date.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            issues.append("invalid_or_unzoned_date_header")
    else:
        issues.append("missing_date_header")

    plain, rich = [], []
    ignored = 0
    stack = [message]
    part_count = 0
    while stack:
        part = stack.pop()
        part_count += 1
        if part_count > MAX_MIME_PARTS:
            raise MailImportError("A message contains too many MIME parts. Re-export a simpler message.")
        if part.defects:
            issues.append("malformed_mime")
        if part.get_content_disposition() == "attachment" or part.get_filename() or part.get_content_maintype() == "message":
            ignored += 1
            continue
        if part.is_multipart():
            stack.extend(reversed(part.get_payload()))
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            ignored += 1
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="strict")
        except LookupError:
            issues.append("unknown_charset_utf8_replacement")
            text = payload.decode("utf-8", errors="replace")
        except UnicodeError:
            issues.append("body_decode_replacement")
            text = payload.decode(charset, errors="replace")
        if part.defects:
            issues.append("malformed_mime")
        (plain if content_type == "text/plain" else rich).append(text)
    if plain:
        body = "\n".join(plain).strip()
    elif rich:
        converter = _PlainHTML()
        converter.feed("\n".join(rich))
        converter.close()
        body = "\n".join(line.strip() for line in "".join(converter.text).splitlines() if line.strip())
        issues.append("html_converted_to_plaintext")
    else:
        body = ""
        issues.append("no_supported_text_body")
    if ignored:
        issues.append("attachments_ignored")
    return {"message_id": message_id, "ahj_id": ahj_id, "sender": sender,
            "subject": subject, "body": body, "received_at": "",
            "date_header": date_header, "date_header_at": date_header_at,
            "timestamp_source": "date_header_unverified" if date_header_at else "unavailable",
            "ignored_attachment_count": ignored, "import_issues": list(dict.fromkeys(issues))}


def load_mail(path: Path, ahj_id: str, limit: int = 100) -> list[dict]:
    """Read one EML, a folder's top-level EMLs, or an mbox without dropping rows.

    All messages receive the one explicitly supplied AHJ ID, which remains an
    operator assertion. Dates are retained separately, never as receipt times.
    Directory order is lexical. Mbox envelope order and duplicates are retained.
    """
    if not isinstance(ahj_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ahj_id):
        raise MailImportError("Choose one explicit AHJ profile ID for this batch, using lowercase letters, numbers and hyphens.")
    if type(limit) is not int or not 1 <= limit <= MAX_MESSAGES:
        raise MailImportError("Message limit must be an integer from 1 to 1000. Split larger exports into batches.")
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise MailImportError("Mail input cannot use symbolic links. Copy the export to a regular private path.")
    if path.is_dir():
        files = []
        for child in path.iterdir():
            if child.is_symlink():
                raise MailImportError("The mail folder contains a symbolic link. Use a folder containing regular EML files.")
            if child.suffix.lower() == ".eml":
                files.append(child)
                if len(files) > limit:
                    raise MailImportError("Message count exceeds the selected limit. Raise --limit (up to 1000) or split the batch.")
        files.sort()
    elif path.suffix.lower() in {".eml", ".mbox"}:
        files = [path]
    else:
        raise MailImportError("Choose an .eml file, an .mbox file, or a folder of top-level .eml files.")
    if not files:
        raise MailImportError("No EML messages were found. Choose a folder containing top-level .eml files.")
    result = []
    used = 0
    for file in files:
        raw = _read_file(file, MAX_INPUT_BYTES - used)
        used += len(raw)
        if file.suffix.lower() == ".mbox":
            # Standard mbox uses an unescaped envelope line at each boundary.
            boundaries = []
            for boundary in re.finditer(rb"(?m)^From [^\r\n]*(?:\r?\n|$)", raw):
                boundaries.append(boundary)
                if len(result) + len(boundaries) > limit:
                    raise MailImportError("Message count exceeds the selected limit. Raise --limit (up to 1000) or split the batch.")
            if not boundaries or boundaries[0].start() != 0:
                raise MailImportError("The MBOX envelope is missing or malformed. Re-export as MBOX or individual EML files.")
            if len(result) + len(boundaries) > limit:
                raise MailImportError("Message count exceeds the selected limit. Raise --limit (up to 1000) or split the batch.")
            chunks = [raw[b.end():boundaries[i + 1].start() if i + 1 < len(boundaries) else len(raw)] for i, b in enumerate(boundaries)]
        else:
            chunks = [raw]
        for chunk in chunks:
            if len(result) >= limit:
                raise MailImportError("Message count exceeds the selected limit. Raise --limit (up to 1000) or split the batch.")
            try:
                result.append(_parse(chunk, ahj_id))
            except MailImportError:
                raise
            except (MessageError, ValueError, LookupError, UnicodeError, RecursionError):
                raise MailImportError("A message has malformed MIME content or headers. Re-export it as a standard EML file.") from None
    return result
