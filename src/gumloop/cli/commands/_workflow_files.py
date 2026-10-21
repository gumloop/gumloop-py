from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gumloop import GumloopError

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def read_upload_files(paths: Mapping[str, Path]) -> dict[str, bytes]:
    resolved = {name: path.expanduser() for name, path in paths.items()}
    total_size = 0
    for path in resolved.values():
        if not path.is_file():
            raise GumloopError(f"Could not read {path}: expected a regular file.")
        with path.open("rb") as file:
            total_size += file.seek(0, 2)
        if total_size > MAX_UPLOAD_BYTES:
            raise GumloopError("Workflow uploads must total at most 200 MiB per command.")

    contents = {}
    remaining = MAX_UPLOAD_BYTES
    for name, path in resolved.items():
        with path.open("rb") as file:
            content = file.read(remaining + 1)
        if len(content) > remaining:
            raise GumloopError("Workflow uploads must total at most 200 MiB per command.")
        contents[name] = content
        remaining -= len(content)
    return contents
