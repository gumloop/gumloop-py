from __future__ import annotations

import sys

from gumloop import GumloopError


def resolve_text_input(
    text: str | None,
    stdin_marker: str | None,
    *,
    text_option: str = "--input",
    stdin_option: str = "--input-stdin",
) -> str | None:
    """Resolve a CLI text source; each command owns whether text is required."""
    if text is not None and stdin_marker is not None:
        raise GumloopError(f"Pass at most one of {text_option} or {stdin_option}.")
    if stdin_marker is not None and stdin_marker != "-":
        raise GumloopError(f"{stdin_option} only accepts '-' (reads from stdin).")
    return sys.stdin.read() if stdin_marker == "-" else text
