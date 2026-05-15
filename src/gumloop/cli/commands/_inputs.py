"""Shared input/file resolution helpers for command modules."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gumloop import GumloopError
from gumloop.resources.skills import SkillFile


def read_text_arg(value: str | None, file_path: str | None, field_name: str) -> str | None:
    """Resolve a text argument from either an inline value or a file path."""
    if value is not None and file_path is not None:
        raise GumloopError(f"Pass at most one of --{field_name} or --{field_name}-file.")
    if file_path is not None:
        try:
            return Path(file_path).expanduser().read_text(encoding="utf-8")
        except OSError as error:
            raise GumloopError(f"Could not read {file_path}: {error.strerror or error}") from error
    return value


def parse_tools_json(tools_json: str | None, tools_file: str | None) -> list[dict[str, Any]] | None:
    """Parse a top-level JSON array of tool config objects."""
    if tools_json is None and tools_file is None:
        return None
    if tools_json is not None and tools_file is not None:
        raise GumloopError("Pass at most one of --tools-json or --tools-file.")

    if tools_file is not None:
        try:
            raw = Path(tools_file).expanduser().read_text(encoding="utf-8")
        except OSError as error:
            raise GumloopError(f"Could not read {tools_file}: {error.strerror or error}") from error
    else:
        raw = tools_json or ""

    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GumloopError(f"Could not parse tools JSON: {error.msg} at line {error.lineno}.") from error
    if not isinstance(parsed, list):
        raise GumloopError("Tools JSON must be an array at the top level.")
    return parsed


def resolve_text_input(inline: str | None, stdin_marker: str | None) -> str | None:
    """Mirror the args-input pattern: inline or '-' for stdin, never both."""
    if inline is not None and stdin_marker is not None:
        raise GumloopError("Pass at most one of --input or --input-stdin.")
    if stdin_marker is not None:
        if stdin_marker != "-":
            raise GumloopError("--input-stdin only accepts '-' (reads from stdin).")
        return sys.stdin.read()
    return inline


def read_skill_files(paths: Sequence[Path]) -> list[SkillFile]:
    """Read on-disk skill files into the (name, bytes) tuples the SDK expects."""
    contents: list[SkillFile] = []
    for path in paths:
        resolved = path.expanduser()
        if not resolved.exists():
            raise GumloopError(f"File not found: {path}")
        if not resolved.is_file():
            raise GumloopError(f"Not a regular file: {path}")
        try:
            contents.append((resolved.name, resolved.read_bytes()))
        except OSError as error:
            raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error
    return contents
