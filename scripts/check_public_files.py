"""Preflight tracked public files. This is a guardrail, not anonymization.

Maintainers still review every fixture for private and identifying information.
No matched secret values are printed by this checker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DIRS = {"private", "data", "outputs", ".git", ".venv", "__pycache__"}
ARCHIVES = {".mbox", ".eml", ".msg", ".zip", ".pem", ".key"}
PATTERNS = [
    ("local user path", re.compile(r"/Users/[A-Za-z0-9_-]+/|C:\\\\Users\\\\[A-Za-z0-9_-]+", re.I)),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential assignment", re.compile(r"(?i)(?:api[_-]?token|api[_-]?key|password)\s*[=:]\s*[\"']?[a-zA-Z0-9_-]{32,}")),
]
MAX_FILE_BYTES = 500_000
# The only reviewed public binary. This pin is independent of its manifest:
# editing a manifest must not make arbitrary compressed/private data publishable.
PUBLIC_ASSETS = {
    "catalog/solartrace/rows.json.gz": (677916, "e08bb523511a27509c2940f6786e5ecdfb7aa9c502f9d01e719da177d10f946c"),
}


def _size_limit(name: str) -> int:
    return PUBLIC_ASSETS.get(name, (MAX_FILE_BYTES, ""))[0]


def _path_problem(name: str) -> str | None:
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        return "invalid public file path"
    if set(rel.parts) & PRIVATE_DIRS or rel.suffix.lower() in ARCHIVES or (rel.name.startswith(".env") and rel.name != ".env.example"):
        return "private data / archive / credential path"
    return None


def _content_problems(raw: bytes, name: str = "") -> list[str]:
    if name in PUBLIC_ASSETS:
        size, digest = PUBLIC_ASSETS[name]
        return [] if len(raw) == size and hashlib.sha256(raw).hexdigest() == digest else ["public source asset differs from its reviewed checksum"]
    if len(raw) > MAX_FILE_BYTES:
        return ["unexpectedly large file; manually review before release"]
    try:
        content = raw.decode("utf-8")
    except UnicodeError:
        return ["unexpected binary file"]
    if "\x00" in content:
        return ["unexpected binary file"]
    return [label for label, pattern in PATTERNS if pattern.search(content)]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # Do not use check=True: Git error messages may contain sensitive filenames.
    # Local replace refs must not substitute clean bytes for a staged object.
    return subprocess.run(["git", "--no-replace-objects", *args], cwd=root, capture_output=True, check=False)


def check_index(root: Path) -> tuple[int, list[tuple[str, str]]]:
    """Check the exact staged snapshot, even when working copies have changed."""
    errors: list[tuple[str, str]] = []
    try:
        top = _git(root, "rev-parse", "--show-toplevel")
        if top.returncode or Path(os.fsdecode(top.stdout).strip()).resolve() != root.resolve():
            return 0, [("<git index>", "Git root must equal this project root; use an isolated repository")]
        result = _git(root, "ls-files", "--stage", "-z")
    except OSError:
        return 0, [("<git index>", "could not inspect the Git index")]
    if result.returncode:
        return 0, [("<git index>", "could not inspect the Git index")]
    entries: dict[str, list[tuple[str, str, str]]] = {}
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        try:
            header, raw_name = item.split(b"\t", 1)
            mode, object_id, stage = header.decode("ascii").split()
            name = os.fsdecode(raw_name)
            if not name or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", object_id):
                raise ValueError
        except (ValueError, UnicodeError):
            errors.append(("<git index>", "invalid Git index entry"))
            continue
        entries.setdefault(name, []).append((mode, object_id, stage))

    for name, versions in entries.items():
        problem = _path_problem(name)
        if problem:
            errors.append((name, problem))
            continue
        if len(versions) != 1 or versions[0][2] != "0":
            errors.append((name, "unmerged Git index entry"))
            continue
        mode, object_id, _ = versions[0]
        if mode not in {"100644", "100755"}:
            label = {"120000": "symbolic link", "160000": "gitlink / submodule"}.get(mode, "unsupported index mode")
            errors.append((name, f"{label} is not allowed in public files"))
            continue
        try:
            kind = _git(root, "cat-file", "-t", object_id)
            size = _git(root, "cat-file", "-s", object_id)
            if kind.returncode or size.returncode or kind.stdout.strip() != b"blob":
                errors.append((name, "missing or invalid staged blob"))
                continue
            size_value = int(size.stdout.strip())
            if size_value < 0:
                raise ValueError
            if size_value > _size_limit(name):
                errors.append((name, "unexpectedly large file; manually review before release"))
                continue
            blob = _git(root, "cat-file", "blob", object_id)
            if blob.returncode or len(blob.stdout) != size_value:
                errors.append((name, "missing or invalid staged blob"))
                continue
        except (OSError, ValueError):
            errors.append((name, "could not read staged blob"))
            continue
        errors.extend((name, label) for label in _content_problems(blob.stdout, name))
    return len(entries), errors


def check_worktree(root: Path) -> tuple[int, list[tuple[str, str]]]:
    names = [str(p.relative_to(root)) for p in root.rglob("*") if (p.is_file() or p.is_symlink()) and not (set(p.relative_to(root).parts) & PRIVATE_DIRS)]
    errors = []
    for name in names:
        path = root / name
        problem = _path_problem(name)
        if problem:
            errors.append((name, problem))
            continue
        if path.is_symlink():
            errors.append((name, "symbolic link is not allowed in public files"))
            continue
        try:
            if path.stat().st_size > _size_limit(name):
                errors.append((name, "unexpectedly large file; manually review before release"))
                continue
            raw = path.read_bytes()
        except OSError:
            errors.append((name, "could not read public file"))
            continue
        errors.extend((name, label) for label in _content_problems(raw, name))
    return len(names), errors


def _safe_name(name: str) -> str:
    if any(pattern.search(name) for _, pattern in PATTERNS):
        return "<redacted filename>"
    # Escape terminal controls and line breaks so a filename cannot inject output.
    return json.dumps(name, ensure_ascii=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracked", action="store_true", help="Inspect only Git's index; use before commit/push")
    args = parser.parse_args()
    if args.tracked:
        count, errors = check_index(ROOT)
    else:
        count, errors = check_worktree(ROOT)
    for name, label in errors:
        print(f"REVIEW {_safe_name(name)}: {label}", file=sys.stderr)
    print(f"Checked {count} public files; {len(errors)} findings. Manual privacy review is still required.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
