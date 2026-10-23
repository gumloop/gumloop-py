from __future__ import annotations

from pathlib import Path

from gumloop import GumloopError


def validate_file(path: Path) -> Path:
    path = path.expanduser()
    try:
        if not path.is_file():
            raise GumloopError(f"Could not read {path}: expected a regular file.")
        with path.open("rb"):
            pass
    except OSError as error:
        raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error
    return path


def read_file(path: Path) -> bytes:
    try:
        with path.open("rb") as file:
            content = file.read()
    except OSError as error:
        raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error
    return content
