from __future__ import annotations

from typing import Any

from gumloop.errors import GumloopError


class SyncError(GumloopError):
    """A stable one-shot sync failure suitable for CLI output."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
