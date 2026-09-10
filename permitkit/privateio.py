"""Local, private outputs with no symlink traversal or accidental setup overwrite."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from .validation import ROOT


def private_path(value: str | Path) -> Path:
    path = Path(value)
    path = path if path.is_absolute() else ROOT / path
    base = ROOT / "private"
    if base.is_symlink():
        raise ValueError("The private directory cannot be a symbolic link.")
    resolved = path.resolve()
    if resolved == base.resolve() or not resolved.is_relative_to(base.resolve()):
        raise ValueError("Choose a path below this clone's private/ directory.")
    # Reject symlink aliases even when their targets remain under private/.
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink():
            raise ValueError("Private output paths cannot contain symbolic links.")
    return resolved


def write_private(path: Path, text: str, *, overwrite: bool = False) -> Path:
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not overwrite:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            raise ValueError("Output already exists. Choose a new private directory; existing files were not replaced.") from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path
    if path.exists() and not path.is_file():
        raise ValueError("Private output must be a regular file.")
    fd, temporary = tempfile.mkstemp(prefix=".sunbridge-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return path


def write_private_json(path: Path, value, *, overwrite: bool = False) -> Path:
    return write_private(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n", overwrite=overwrite)


def preflight_private_targets(output: Path, names, *, sources=(), overwrite: bool = False) -> Path:
    """Reject unsafe leaves and input collisions before a remote read or model call."""
    output = private_path(output)
    for parent in [output, *output.parents]:
        if parent.exists() and not parent.is_dir():
            raise ValueError("Private output needs a directory, not an existing file.")
    inputs = [Path(path).resolve() for path in sources if path is not None]
    for name in names:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("Output filenames must be simple local names.")
        target = private_path(output / name)
        for source in inputs:
            if target == source or (source.is_dir() and target.is_relative_to(source)):
                raise ValueError("Output would overwrite an input or configuration. Choose a different private output directory.")
            if target.exists() and source.is_file() and target.samefile(source):
                raise ValueError("Output is linked to an input. Choose a different private output directory.")
        if target.exists() and (not overwrite or not target.is_file()):
            raise ValueError("Output already exists or is not a regular report file. Choose a new private output directory.")
    return output


def read_json_file(path: Path, *, max_bytes: int = 16_000_000):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Choose an existing regular JSON file, not a symbolic link.")
    if path.stat().st_size > max_bytes:
        raise ValueError("JSON input is too large; split it into a smaller review batch.")
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("JSON input is too large; split it into a smaller review batch.")
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Input must be valid UTF-8 JSON.") from None
