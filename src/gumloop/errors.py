from __future__ import annotations

from typing import Any


class GumloopError(Exception):
    """Base error for Gumloop SDK failures."""


class AuthenticationError(GumloopError):
    """Raised when an SDK method needs a missing credential."""


class APIStatusError(GumloopError):
    """Raised when Gumloop returns a non-success HTTP status."""

    def __init__(self, message: str, *, status_code: int, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.error = body.get("error") if isinstance(body, dict) else None
        self.code = self.error.get("code") if isinstance(self.error, dict) else None
        self.type = self.error.get("type") if isinstance(self.error, dict) else None
        self.param = self.error.get("param") if isinstance(self.error, dict) else None
        self.details = self.error.get("details", {}) if isinstance(self.error, dict) else {}
