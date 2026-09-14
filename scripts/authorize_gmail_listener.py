"""Create a private, read-only Gmail refresh credential after local consent.

The browser flow is the only interactive step. Authorization URLs, callback
codes, tokens, provider errors, and mailbox contents are never printed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sunbridge.privateio import private_path, write_private_json


SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
PROFILE_URI = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
MAX_CLIENT_BYTES = 65_536
_PROJECT = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]\Z")
_CLIENT_ID = re.compile(r"[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com\Z")
_MAILBOX = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
                      r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                      r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\Z")


class SetupError(ValueError):
    """An operator-safe error containing no provider response or secrets."""


class _DiscardOutput:
    def write(self, value):
        return len(value)

    def flush(self):
        pass


@contextmanager
def _quiet_oauth():
    """Suppress library diagnostics, including callback query-string logs."""
    previous = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        with redirect_stdout(_DiscardOutput()), redirect_stderr(_DiscardOutput()):
            yield
    finally:
        logging.disable(previous)


def _secret_string(value, *, limit=16_384):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and value == value.strip() and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _mailbox(value):
    if not isinstance(value, str) or len(value) > 254 or not _MAILBOX.fullmatch(value):
        raise SetupError("Provide the primary Gmail or Workspace mailbox address, not a display name.")
    return value.lower()


def load_client(path: Path, project: str) -> dict:
    """Read a small Desktop client file without following symbolic links."""
    if not isinstance(project, str) or not _PROJECT.fullmatch(project):
        raise SetupError("Provide a valid Google Cloud project ID.")
    path = Path(path).absolute()
    try:
        if any(item.is_symlink() for item in (path, *path.parents)):
            raise SetupError("OAuth client input must be a regular file without symbolic links.")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CLIENT_BYTES:
                raise SetupError("OAuth client input must be a regular JSON file of at most 64 KiB.")
            raw = handle.read(MAX_CLIENT_BYTES + 1)
        if len(raw) > MAX_CLIENT_BYTES:
            raise SetupError("OAuth client input must be a regular JSON file of at most 64 KiB.")
        data = json.loads(raw.decode("utf-8"))
    except SetupError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise SetupError("Could not read the Desktop OAuth client JSON file.") from None
    if not isinstance(data, dict) or "web" in data or not isinstance(data.get("installed"), dict):
        raise SetupError("Download an OAuth client of application type Desktop app.")
    client = data["installed"]
    if client.get("project_id") != project:
        raise SetupError("The Desktop OAuth client must belong to the same project as the Gmail Pub/Sub topic.")
    if client.get("auth_uri") != AUTH_URI or client.get("token_uri") != TOKEN_URI:
        raise SetupError("OAuth client endpoints must be Google's standard authorization and token endpoints.")
    if (not isinstance(client.get("client_id"), str) or not _CLIENT_ID.fullmatch(client["client_id"])
            or not _secret_string(client.get("client_secret"), limit=4096)):
        raise SetupError("The Desktop OAuth client has invalid or missing client credentials.")
    # Only validated fields reach the OAuth library. The loopback redirect is
    # set dynamically by run_local_server, not read from an untrusted JSON key.
    return {"installed": {name: client[name] for name in
            ("client_id", "client_secret", "project_id", "auth_uri", "token_uri")}}


def _output_target(output: Path, source: Path) -> Path:
    try:
        target = private_path(output)
        if target.exists() or target == source.resolve():
            raise SetupError("Output already exists or is the client input. Choose a new private output file.")
        base = private_path("private/.oauth-path-check").parent
        parent = target.parent
        while parent == base or parent.is_relative_to(base):
            if parent.exists():
                info = parent.stat()
                if not stat.S_ISDIR(info.st_mode):
                    raise SetupError("Private credential output requires directories, not existing files.")
                if info.st_mode & 0o077 or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
                    raise SetupError("Credential directories must be owned by you and accessible only to you (mode 700).")
            if parent == base:
                break
            parent = parent.parent
        return target
    except SetupError:
        raise
    except (OSError, ValueError):
        raise SetupError("Choose an unused file below this clone's private directory, without symbolic links.") from None


def _scope_set(value):
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, (list, tuple, set)) and all(isinstance(item, str) for item in value):
        return set(value)
    raise SetupError("Google did not confirm a valid read-only Gmail scope grant.")


def _validate_grant(flow, client):
    credentials = flow.credentials
    if (credentials.client_id != client["client_id"]
            or credentials.client_secret != client["client_secret"]
            or credentials.token_uri != TOKEN_URI):
        raise SetupError("The returned credentials do not match the validated Desktop OAuth client.")
    evidence = []
    granted = getattr(credentials, "granted_scopes", None)
    if granted is not None:
        evidence.append(granted)
    token = getattr(flow.oauth2session, "token", {})
    if isinstance(token, dict) and "scope" in token:
        evidence.append(token["scope"])
    if not evidence or any(_scope_set(scopes) != {SCOPE} for scopes in evidence):
        raise SetupError("Grant exactly Gmail read-only access; revoke an existing broader app grant and try again.")
    requested = getattr(credentials, "scopes", None)
    if requested is not None and _scope_set(requested) != {SCOPE}:
        raise SetupError("Only Gmail read-only access is permitted for this listener.")
    if not _secret_string(credentials.refresh_token):
        raise SetupError("Google did not issue a refresh token. Revoke this app's existing grant and authorize again.")
    return credentials


def _verify_mailbox(flow, mailbox):
    session = flow.authorized_session()
    try:
        response = session.get(PROFILE_URI, timeout=20, allow_redirects=False)
        if response.status_code != 200 or len(response.content) > MAX_CLIENT_BYTES:
            raise SetupError("Could not verify the authorized Gmail mailbox. No credential was saved.")
        profile = response.json()
        if not isinstance(profile, dict) or _mailbox(profile.get("emailAddress")) != mailbox:
            raise SetupError("The authorized account is not the requested primary mailbox. No credential was saved.")
    finally:
        session.close()


def authorize(client_file: Path, mailbox: str, project: str, output: Path, consent_mode: str) -> Path:
    """Authorize once; the consent-mode argument is an operator attestation."""
    if consent_mode not in {"internal", "production"}:
        raise SetupError("Confirm consent mode explicitly as internal or production; external Testing is not supported.")
    mailbox = _mailbox(mailbox)
    client_config = load_client(client_file, project)
    target = _output_target(output, client_file)
    try:
        # The public project stays dependency-free. This import is needed only
        # when an operator actually runs the browser authorization helper.
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise SetupError("Install google-auth-oauthlib in your private listener environment before authorizing.") from None
    try:
        with _quiet_oauth():
            flow = InstalledAppFlow.from_client_config(
                client_config, scopes=[SCOPE], autogenerate_code_verifier=True)
            flow.run_local_server(
                host="127.0.0.1", port=0, open_browser=True,
                authorization_prompt_message="",
                success_message="Sun Bridge received the authorization response. You may close this tab.",
                timeout_seconds=300, access_type="offline", prompt="consent",
                include_granted_scopes="false", login_hint=mailbox,
            )
            credentials = _validate_grant(flow, client_config["installed"])
            _verify_mailbox(flow, mailbox)
    except SetupError:
        raise
    except Exception:
        raise SetupError("Gmail authorization or mailbox verification failed. No credential was saved; retry locally.") from None
    payload = {
        "type": "authorized_user",
        "client_id": client_config["installed"]["client_id"],
        "client_secret": client_config["installed"]["client_secret"],
        "refresh_token": credentials.refresh_token,
        "token_uri": TOKEN_URI,
        "scopes": [SCOPE],
        "_sunbridge": {"project_id": project, "mailbox": mailbox, "consent_mode": consent_mode},
    }
    try:
        # Recheck after the browser step; never overwrite a file created while
        # consent was open. Create every missing private directory with 0700.
        target = _output_target(target, client_file)
        missing = []
        parent = target.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for parent in reversed(missing):
            parent.mkdir(mode=0o700)
        return write_private_json(target, payload, overwrite=False)
    except (OSError, ValueError):
        raise SetupError("Could not save the private credential safely. Existing files were not replaced.") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Invalid setup arguments. Use --help for the required options.\n")


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("--client-file", type=Path, required=True)
    parser.add_argument("--mailbox", required=True, help="Primary mailbox receiving each group email; not a group or alias")
    parser.add_argument("--project", required=True, help="Google Cloud project containing both OAuth client and Pub/Sub topic")
    parser.add_argument("--output", type=Path, default=Path("private/gmail/oauth.json"))
    parser.add_argument("--consent-mode", choices=("internal", "production"), required=True,
                        help="Operator confirms actual Google consent configuration; this helper cannot verify it")
    args = parser.parse_args(argv)
    print("Confirm the consent screen configuration before continuing: external Testing Gmail refresh tokens expire")
    print("after 7 days; renewing the Gmail watch does not fix this. Consent mode is your attestation, not a verified check.")
    print("Opening local browser consent for Gmail read-only access. No authorization URL or credentials will be printed.")
    try:
        authorize(args.client_file, args.mailbox, args.project, args.output, args.consent_mode)
    except SetupError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Authorization cancelled. No credential was intentionally replaced.", file=sys.stderr)
        return 1
    except Exception:
        print("Gmail setup failed safely. Check the local configuration; provider details were not printed.", file=sys.stderr)
        return 1
    print("Saved owner-only Gmail read-only refresh credentials in the requested private file. The listener is not started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
