"""Only inline fictional email data; no network or checked-in mail archives."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunbridge.mail import MailImportError, load_mail

BASE = b"From: Example Office <notifications@example.invalid>\nSubject: Application DEMO-001 received\nMessage-ID: <demo@example.invalid>\nDate: Tue, 06 Jan 2026 09:00:00 -0500\n\nFictional receipt.\n"


class MailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def read(self, raw, name="sample.eml", **kwargs):
        path = self.root / name
        path.write_bytes(raw)
        return load_mail(path, "example-training-county", **kwargs)

    def test_headers_date_and_explicit_ahj(self):
        row = self.read(BASE.replace(b"Application DEMO-001 received", b"=?utf-8?b?Q2Fmw6kgcmVjZWl2ZWQ=?="))[0]
        self.assertEqual(row["subject"], "Café received")
        self.assertEqual(row["ahj_id"], "example-training-county")
        self.assertEqual(row["received_at"], "")
        self.assertEqual(row["date_header_at"], "2026-01-06T14:00:00+00:00")
        self.assertEqual(row["timestamp_source"], "date_header_unverified")
        self.assertIn("date_header_is_not_receipt_time", row["import_issues"])

    def test_missing_headers_have_stable_synthetic_id(self):
        first = self.read(b"Content-Type: text/plain\n\nFictional body.")[0]
        second = self.read(b"Content-Type: text/plain\n\nFictional body.")[0]
        self.assertEqual(first["message_id"], second["message_id"])
        self.assertTrue(first["message_id"].startswith("synthetic-sha256-"))
        self.assertIn("missing_sender", first["import_issues"])
        self.assertIn("missing_subject", first["import_issues"])
        self.assertIn("missing_date_header", first["import_issues"])

    def test_plain_preferred_and_attachments_ignored(self):
        raw = b"MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=xyz\n\n--xyz\nContent-Type: text/html\n\n<b>Rich body</b>\n--xyz\nContent-Type: text/plain\n\nPlain body\n--xyz\nContent-Type: text/plain\nContent-Disposition: attachment; filename=private.txt\n\nAttachment must not be read into body\n--xyz--\n"
        row = self.read(raw)[0]
        self.assertEqual(row["body"], "Plain body")
        self.assertEqual(row["ignored_attachment_count"], 1)

    def test_mime_transfer_encoding_and_forwarded_attachment(self):
        row = self.read(b"Content-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: base64\n\nUGVybWl0IHJlY2VpdmVkLg==\n")[0]
        self.assertEqual(row["body"], "Permit received.")
        raw = b"MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=xyz\n\n--xyz\nContent-Type: text/plain\n\nCurrent text\n--xyz\nContent-Type: message/rfc822\n\n" + BASE + b"\n--xyz--\n"
        row = self.read(raw)[0]
        self.assertEqual(row["body"], "Current text")
        self.assertEqual(row["ignored_attachment_count"], 1)

    def test_html_tracking_and_active_content_not_loaded(self):
        raw = b'Content-Type: text/html; charset=utf-8\n\n<p>Permit received &amp; logged</p><img src="https://example.invalid/pixel"><script>steal()</script><style>secret{}</style><iframe src="https://example.invalid/">hidden</iframe><a href="https://example.invalid/">Visible text</a>'
        with patch("urllib.request.urlopen", side_effect=AssertionError("No fetching")), patch("socket.socket", side_effect=AssertionError("No network")):
            row = self.read(raw)[0]
        self.assertIn("Permit received & logged", row["body"])
        self.assertIn("Visible text", row["body"])
        for hidden in ("steal", "secret", "hidden", "https://", "<img"):
            self.assertNotIn(hidden, row["body"])

    def test_folder_order_and_duplicates_preserved(self):
        (self.root / "b.eml").write_bytes(BASE)
        (self.root / "a.eml").write_bytes(BASE.replace(b"received", b"accepted"))
        rows = load_mail(self.root, "example-training-county")
        self.assertEqual(len(rows), 2)
        self.assertIn("accepted", rows[0]["subject"])
        self.assertEqual(rows[0]["message_id"], rows[1]["message_id"])

    def test_mbox_boundaries_and_limit(self):
        envelope = b"From notifications@example.invalid Tue Jan 6 14:00:00 2026\n"
        raw = envelope + BASE + b"\n" + envelope + BASE
        self.assertEqual(len(self.read(raw, "sample.mbox")), 2)
        with self.assertRaisesRegex(MailImportError, "count"):
            self.read(raw, "sample.mbox", limit=1)
        with self.assertRaisesRegex(MailImportError, "envelope"):
            self.read(BASE, "broken.mbox")

    def test_limits_and_symlinks_fail(self):
        self.read(BASE)
        (self.root / "second.eml").write_bytes(BASE)
        with self.assertRaisesRegex(MailImportError, "count"):
            load_mail(self.root, "example-training-county", 1)
        with patch("sunbridge.mail.MAX_INPUT_BYTES", 10), self.assertRaisesRegex(MailImportError, "total limit"):
            load_mail(self.root / "sample.eml", "example-training-county")
        with patch("sunbridge.mail.MAX_MESSAGE_BYTES", 10), self.assertRaisesRegex(MailImportError, "message exceeds"):
            load_mail(self.root / "sample.eml", "example-training-county")
        (self.root / "link.eml").symlink_to(self.root / "sample.eml")
        with self.assertRaisesRegex(MailImportError, "symbolic"):
            load_mail(self.root / "link.eml", "example-training-county")
        with self.assertRaisesRegex(MailImportError, "symbolic"):
            load_mail(self.root, "example-training-county")
        with self.assertRaises(MailImportError):
            load_mail(self.root / "sample.eml", "")
        with self.assertRaises(MailImportError):
            load_mail(self.root / "sample.eml", "example-training-county", 0)

    def test_bad_charsets_dates_and_mime_are_flagged(self):
        row = self.read(b"Date: not-a-date\nContent-Type: text/plain; charset=madeup-encoding\n\nBad byte: \xff")[0]
        self.assertIn("unknown_charset_utf8_replacement", row["import_issues"])
        self.assertIn("invalid_or_unzoned_date_header", row["import_issues"])
        self.assertIn("\ufffd", row["body"])
        row = self.read(b"Content-Type: text/plain; charset=utf-8\n\nBad byte: \xff")[0]
        self.assertIn("body_decode_replacement", row["import_issues"])
        row = self.read(b"MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=missing\n\nNo boundary")[0]
        self.assertIn("malformed_mime", row["import_issues"])
        row = self.read(BASE.replace(b" -0500", b" -0000"))[0]
        self.assertIsNone(row["date_header_at"])
        self.assertIn("invalid_or_unzoned_date_header", row["import_issues"])
        with self.assertRaises(MailImportError):
            self.read(b"")

    def test_mime_part_limit_and_linked_parent(self):
        raw = b"MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x\nContent-Type: text/plain\n\nOne\n--x\nContent-Type: text/plain\n\nTwo\n--x--\n"
        with patch("sunbridge.mail.MAX_MIME_PARTS", 2), self.assertRaisesRegex(MailImportError, "MIME parts"):
            self.read(raw)
        regular = self.root / "regular"
        regular.mkdir()
        (regular / "message.eml").write_bytes(BASE)
        (self.root / "linked").symlink_to(regular, target_is_directory=True)
        with self.assertRaisesRegex(MailImportError, "symbolic"):
            load_mail(self.root / "linked/message.eml", "example-training-county")


if __name__ == "__main__":
    unittest.main()
