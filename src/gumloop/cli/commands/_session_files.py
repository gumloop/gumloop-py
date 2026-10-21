from __future__ import annotations

from pathlib import Path

from gumloop import GumloopError

MAX_FILE_BYTES = 200 * 1024 * 1024


def validate_file(path: Path) -> Path:
    path = path.expanduser()
    try:
        if not path.is_file():
            raise GumloopError(f"Could not read {path}: expected a regular file.")
        with path.open("rb") as file:
            if file.seek(0, 2) > MAX_FILE_BYTES:
                raise GumloopError(f"File {path} exceeds the 200 MB session upload limit.")
    except OSError as error:
        raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error
    return path


def read_file(path: Path) -> bytes:
    try:
        with path.open("rb") as file:
            content = file.read(MAX_FILE_BYTES + 1)
    except OSError as error:
        raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error
    if len(content) > MAX_FILE_BYTES:
        raise GumloopError(f"File {path} exceeds the 200 MB session upload limit.")
    return content
