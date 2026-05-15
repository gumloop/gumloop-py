from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console

console = Console()
error_console = Console(stderr=True)


def _to_plain(data: Any) -> Any:
    # ``mode="json"`` so datetime/UUID land as JSON-safe primitives.
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json")
    return data


def _serialize(data: Any) -> str:
    return json.dumps(_to_plain(data), sort_keys=True, default=str)


def print_json(data: Any) -> None:
    """Raw JSON to stdout. Bypasses Rich so ``--json | jq`` is byte-deterministic."""
    sys.stdout.write(_serialize(data))
    sys.stdout.write("\n")
    sys.stdout.flush()


def print_json_error(data: Any) -> None:
    """Same as :func:`print_json` but writes to stderr."""
    sys.stderr.write(_serialize(data))
    sys.stderr.write("\n")
    sys.stderr.flush()
