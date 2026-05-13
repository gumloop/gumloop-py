"""Resolve flexible structured-args input for commands like `gumloop mcp call`."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gumloop import GumloopError


def resolve_json_args(
    *,
    inline: str | None,
    file_path: str | None,
    stdin_marker: str | None,
) -> dict[str, Any]:
    """Return a parsed JSON object from at most one of inline/file/stdin.

    All three may be ``None`` (returns an empty dict). Combining more than one
    is an error to keep precedence unambiguous.
    """
    provided = [
        name
        for name, value in (("--args-json", inline), ("--args-file", file_path), ("--args", stdin_marker))
        if value is not None
    ]
    if len(provided) > 1:
        raise GumloopError(f"Pass at most one of {', '.join(provided)}.")

    raw: str
    if inline is not None:
        raw = inline
    elif file_path is not None:
        # OSError covers FileNotFoundError, PermissionError, IsADirectoryError,
        # etc. Wrap so callers' `except GumloopError` catches it cleanly
        # instead of leaking a Python traceback.
        try:
            raw = Path(file_path).expanduser().read_text(encoding="utf-8")
        except OSError as error:
            raise GumloopError(f"Could not read {file_path}: {error.strerror or error}") from error
    elif stdin_marker is not None:
        if stdin_marker != "-":
            raise GumloopError(
                "--args only accepts '-' (read JSON from stdin). For other input, use --args-json or --args-file."
            )
        raw = sys.stdin.read()
    else:
        return {}

    if not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GumloopError(f"Could not parse JSON args: {error.msg} at line {error.lineno}.") from error

    if not isinstance(parsed, dict):
        raise GumloopError("JSON args must be an object at the top level.")
    return parsed
