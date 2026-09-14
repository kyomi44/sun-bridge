"""Synthetic OAuth responses only; no credentials, browser, or network access."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import logging
from pathlib import Path
import stat
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/authorize_gmail_listener.py"
spec = importlib.util.spec_from_file_location("gmail_oauth_setup", SCRIPT)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

PROJECT = "example-listener-project"
MAILBOX = "listener@example.invalid"
CLIENT_ID = "1234567890-fictional.apps.googleusercontent.com"
CLIENT_SECRET = "fictional-client-secret"
REFRESH = "fictional-refresh-secret"
ACCESS = "fictional-access-secret"


class GmailOAuthSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.client_file = self.root / "desktop.json"
        self.output = self.root / "private/gmail/oauth.json"
        self.config = {"installed": {
            "project_id": PROJECT, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "auth_uri": setup.AUTH_URI, "token_uri": setup.TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }}
        self.write_client()
        self.root_patch = patch("sunbridge.privateio.ROOT", self.root)
        self.root_patch.start()
        self.network_patch = patch("socket.socket", side_effect=AssertionError("No network allowed"))
        self.network_patch.start()
        self.credentials = SimpleNamespace(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_uri=setup.TOKEN_URI,
            refresh_token=REFRESH, token=ACCESS, scopes=[setup.SCOPE], granted_scopes=[setup.SCOPE])
        self.response = Mock(status_code=200, content=b'{"emailAddress": "listener@example.invalid"}')
        self.response.json.return_value = {"emailAddress": MAILBOX}
        self.session = Mock()
        self.session.get.return_value = self.response
        self.flow = Mock()
        self.flow.credentials = self.credentials
        self.flow.oauth2session = SimpleNamespace(token={"scope": setup.SCOPE})
        self.flow.authorized_session.return_value = self.session
        self.factory = Mock()
        self.factory.from_client_config.return_value = self.flow
        package = ModuleType("google_auth_oauthlib")
        module = ModuleType("google_auth_oauthlib.flow")
        module.InstalledAppFlow = self.factory
        package.flow = module
        self.modules_patch = patch.dict(sys.modules, {"google_auth_oauthlib": package, "google_auth_oauthlib.flow": module})
        self.modules_patch.start()

    def tearDown(self):
        self.modules_patch.stop()
        self.network_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def write_client(self):
        self.client_file.write_text(json.dumps(self.config), encoding="utf-8")

    def authorize(self, **kwargs):
        args = {"client_file": self.client_file, "mailbox": MAILBOX, "project": PROJECT,
                "output": self.output, "consent_mode": "internal"}
        args.update(kwargs)
        return setup.authorize(**args)

    def assert_not_saved(self):
        self.assertFalse(self.output.exists())

    def test_success_readonly_pkce_loopback_offline_and_primary_profile(self):
        self.assertEqual(self.authorize(), self.output)
        configuration, = self.factory.from_client_config.call_args.args
        self.assertNotIn("redirect_uris", configuration["installed"])
        self.assertEqual(self.factory.from_client_config.call_args.kwargs,
                         {"scopes": [setup.SCOPE], "autogenerate_code_verifier": True})
        call = self.flow.run_local_server.call_args.kwargs
        for key, value in {"host": "127.0.0.1", "port": 0, "access_type": "offline", "prompt": "consent",
                           "include_granted_scopes": "false", "login_hint": MAILBOX,
                           "open_browser": True, "authorization_prompt_message": "", "timeout_seconds": 300}.items():
            self.assertEqual(call[key], value)
        self.session.get.assert_called_once_with(setup.PROFILE_URI, timeout=20, allow_redirects=False)
        self.session.close.assert_called_once()
        payload = json.loads(self.output.read_text())
        self.assertEqual(set(payload), {"type", "client_id", "client_secret", "refresh_token", "token_uri", "scopes", "_sunbridge"})
        self.assertEqual(payload["refresh_token"], REFRESH)
        self.assertNotIn(ACCESS, self.output.read_text())
        self.assertEqual(payload["_sunbridge"], {"project_id": PROJECT, "mailbox": MAILBOX, "consent_mode": "internal"})
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.output.parent.parent.stat().st_mode), 0o700)

    def test_wrong_project_rejected_before_library_or_browser(self):
        with self.assertRaisesRegex(setup.SetupError, "same project"):
            self.authorize(project="another-listener-project")
        self.factory.from_client_config.assert_not_called()
        self.assert_not_saved()

    def test_web_wrong_endpoints_and_malformed_client_rejected(self):
        cases = [
            {"web": self.config["installed"]},
            {"installed": dict(self.config["installed"], auth_uri="https://example.invalid/auth")},
            {"installed": dict(self.config["installed"], token_uri="http://oauth2.googleapis.com/token")},
            {"installed": dict(self.config["installed"], client_id="wrong")},
            {"installed": dict(self.config["installed"], client_secret="secret\n")},
            [],
        ]
        for data in cases:
            with self.subTest(data=data):
                self.config = data
                self.write_client()
                with self.assertRaises(setup.SetupError):
                    self.authorize()
        self.factory.from_client_config.assert_not_called()

    def test_client_symlink_linked_parent_directory_and_size_rejected(self):
        link = self.root / "client-link.json"
        link.symlink_to(self.client_file)
        with self.assertRaisesRegex(setup.SetupError, "symbolic"):
            self.authorize(client_file=link)
        directory_link = self.root / "linked-directory"
        directory_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(setup.SetupError, "symbolic"):
            self.authorize(client_file=directory_link / "desktop.json")
        with self.assertRaises(setup.SetupError):
            self.authorize(client_file=self.root)
        self.client_file.write_bytes(b" " * (setup.MAX_CLIENT_BYTES + 1))
        with self.assertRaisesRegex(setup.SetupError, "64 KiB"):
            self.authorize()
        self.factory.from_client_config.assert_not_called()

    def test_malformed_or_missing_json_sanitized(self):
        for raw in (b"\xff", b"{" + CLIENT_SECRET.encode()):
            self.client_file.write_bytes(raw)
            with self.assertRaises(setup.SetupError) as caught:
                self.authorize()
            self.assertNotIn(CLIENT_SECRET, str(caught.exception))
        with self.assertRaises(setup.SetupError):
            self.authorize(client_file=self.root / "missing.json")

    def test_scope_grant_missing_broad_or_disagreeing_is_rejected(self):
        for granted, returned in [
            (None, None), ([], ""),
            ([setup.SCOPE, "https://mail.google.com/"], setup.SCOPE),
            ([setup.SCOPE], setup.SCOPE + " https://www.googleapis.com/auth/gmail.modify"),
            ([setup.SCOPE], "openid"),
            ([setup.SCOPE], {"invalid": "scope"}),
        ]:
            with self.subTest(granted=granted, returned=returned):
                self.credentials.granted_scopes = granted
                self.flow.oauth2session.token = {} if returned is None else {"scope": returned}
                with self.assertRaises(setup.SetupError):
                    self.authorize()
                self.assert_not_saved()
        self.session.get.assert_not_called()

    def test_one_authoritative_scope_source_is_sufficient(self):
        self.credentials.granted_scopes = None
        self.authorize()

    def test_requested_extra_scopes_and_missing_refresh_rejected(self):
        self.credentials.scopes.append("openid")
        with self.assertRaisesRegex(setup.SetupError, "Only Gmail"):
            self.authorize()
        self.credentials.scopes = [setup.SCOPE]
        for refresh in (None, "", "bad\nsecret"):
            self.credentials.refresh_token = refresh
            with self.assertRaisesRegex(setup.SetupError, "refresh token"):
                self.authorize()
        self.assert_not_saved()

    def test_wrong_authorized_client_rejected(self):
        self.credentials.client_id = "another-client"
        with self.assertRaisesRegex(setup.SetupError, "do not match"):
            self.authorize()
        self.assert_not_saved()

    def test_profile_mismatch_alias_http_redirect_and_failure_do_not_save(self):
        for code, payload in [(200, {"emailAddress": "other@example.invalid"}),
                              (200, {"emailAddress": MAILBOX}), (403, {"error": REFRESH}),
                              (302, {"emailAddress": MAILBOX}), (200, {}), (200, [])]:
            with self.subTest(code=code, payload=payload):
                self.response.status_code = code
                self.response.json.return_value = payload
                mailbox = "alias@example.invalid" if code == 200 and payload == {"emailAddress": MAILBOX} else MAILBOX
                with self.assertRaises(setup.SetupError):
                    self.authorize(mailbox=mailbox)
                self.assert_not_saved()
        self.assertEqual(self.session.close.call_count, 6)

    def test_profile_case_insensitive_and_bounded(self):
        self.response.content = b" " * (setup.MAX_CLIENT_BYTES + 1)
        with self.assertRaises(setup.SetupError):
            self.authorize()
        self.response.content = b"{}"
        self.response.json.return_value = {"emailAddress": MAILBOX.upper()}
        self.authorize(mailbox=MAILBOX.upper())

    def test_output_outside_private_symlink_existing_and_permissive_directory_rejected_before_browser(self):
        with self.assertRaises(setup.SetupError):
            self.authorize(output=self.root / "public.json")
        private = self.root / "private"
        private.mkdir(mode=0o700)
        (private / "alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(setup.SetupError):
            self.authorize(output=private / "alias/oauth.json")
        self.output.parent.mkdir(mode=0o700)
        self.output.write_text("existing credential")
        with self.assertRaises(setup.SetupError):
            self.authorize()
        self.assertEqual(self.output.read_text(), "existing credential")
        self.output.parent.chmod(0o755)
        with self.assertRaisesRegex(setup.SetupError, "mode 700"):
            self.authorize(output=self.output.parent / "new.json")
        self.factory.from_client_config.assert_not_called()

    def test_file_created_during_consent_not_overwritten(self):
        def create_during_consent(**kwargs):
            (self.root / "private").mkdir(mode=0o700)
            self.output.parent.mkdir(mode=0o700)
            self.output.write_text("keep existing")
        self.flow.run_local_server.side_effect = create_during_consent
        with self.assertRaisesRegex(setup.SetupError, "safely"):
            self.authorize()
        self.assertEqual(self.output.read_text(), "keep existing")

    def test_root_private_output_supported(self):
        self.authorize(output=self.root / "private/oauth.json")
        self.assertTrue((self.root / "private/oauth.json").is_file())

    def test_consent_mode_required_and_invalid_mailboxes_rejected(self):
        for mode in (None, "testing", "", "external"):
            with self.assertRaisesRegex(setup.SetupError, "consent mode"):
                self.authorize(consent_mode=mode)
        for mailbox in ("Name <listener@example.invalid>", "listener@example.invalid\n", "not-mail", None):
            with self.assertRaises(setup.SetupError):
                self.authorize(mailbox=mailbox)
        self.factory.from_client_config.assert_not_called()

    def test_provider_output_callback_logs_and_errors_are_not_printed(self):
        secret = "callback-code-state-access-refresh-private-secret"
        def noisy_provider(**kwargs):
            print(secret)
            print(secret, file=sys.stderr)
            logging.getLogger("google_auth_oauthlib.flow").critical(secret)
            raise RuntimeError(secret)
        self.flow.run_local_server.side_effect = noisy_provider
        output, errors = io.StringIO(), io.StringIO()
        original_level = logging.root.manager.disable
        with redirect_stdout(output), redirect_stderr(errors):
            result = setup.main(["--client-file", str(self.client_file), "--mailbox", MAILBOX,
                                 "--project", PROJECT, "--output", str(self.output), "--consent-mode", "production"])
        self.assertEqual(result, 1)
        combined = output.getvalue() + errors.getvalue()
        for value in (secret, ACCESS, REFRESH, CLIENT_SECRET, "Traceback"):
            self.assertNotIn(value, combined)
        self.assertIn("7 days", combined)
        self.assertIn("attestation", combined)
        self.assertEqual(logging.root.manager.disable, original_level)
        self.assert_not_saved()

    def test_import_optional_and_cli_missing_dependency_is_safe(self):
        with patch.dict(sys.modules, {"google_auth_oauthlib": None, "google_auth_oauthlib.flow": None}):
            spec.loader.exec_module(setup)
            with self.assertRaisesRegex(setup.SetupError, "Install google-auth-oauthlib"):
                self.authorize()


if __name__ == "__main__":
    unittest.main()
