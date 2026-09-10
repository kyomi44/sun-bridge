"""Reproduce the public email coverage documentation from its public registry.

No mailbox, credentials, private analysis, or arbitrary input path is accepted.
Use --check in CI to verify that checked-in documentation is up to date.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sunbridge.coverage import load_registry, render_candidate_svg, render_markdown, render_pilot_svg


REGISTRY_PATH = ROOT / "coverage/ahj-email-signals.json"
OUTPUT_PATHS = {
    "markdown": ROOT / "docs/email-coverage.md",
    "pilot": ROOT / "docs/assets/email-pilot-milestones.svg",
    "candidate": ROOT / "docs/assets/email-candidate-signals.svg",
}


def _require_public_path(path: Path) -> None:
    if not path.is_absolute() or path == ROOT or not path.is_relative_to(ROOT):
        raise ValueError("Coverage paths must stay within the public project.")
    if ".." in path.relative_to(ROOT).parts:
        raise ValueError("Coverage paths must not traverse parent directories.")
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(ROOT)):
        raise ValueError("Coverage paths must not contain symbolic links.")


def _write_atomic(path: Path, content: bytes) -> None:
    _require_public_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".coverage-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify generated files without writing them")
    args = parser.parse_args(argv)
    try:
        _require_public_path(REGISTRY_PATH)
        for path in OUTPUT_PATHS.values():
            _require_public_path(path)
        data = load_registry(REGISTRY_PATH)
        documents = {
            "markdown": render_markdown(data),
            "pilot": render_pilot_svg(data),
            "candidate": render_candidate_svg(data),
        }
        stale = []
        for key, document in documents.items():
            path = OUTPUT_PATHS[key]
            _require_public_path(path)
            content = document.encode("utf-8")
            if args.check:
                if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                    stale.append(str(path.relative_to(ROOT)))
            else:
                _write_atomic(path, content)
        if stale:
            print("Public email coverage artifacts are missing or stale: " + ", ".join(stale), file=sys.stderr)
            print("Run python3 scripts/render_email_coverage.py to regenerate them.", file=sys.stderr)
            return 1
    except (OSError, ValueError):
        print("Could not render public email coverage. Check the registry and fixed output paths.", file=sys.stderr)
        return 1
    print("Public email coverage artifacts are current." if args.check else "Generated public email coverage documentation and charts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
