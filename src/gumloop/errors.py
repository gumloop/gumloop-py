from __future__ import annotations

from typing import Any

import httpx


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
        if isinstance(self.error, dict):
            self.code = self.error.get("code")
        else:
            self.code = self.error if isinstance(self.error, str) and self.error else None
        self.type = self.error.get("type") if isinstance(self.error, dict) else None
        self.param = self.error.get("param") if isinstance(self.error, dict) else None
        self.details = self.error.get("details", {}) if isinstance(self.error, dict) else {}


def to_api_error(response: httpx.Response) -> APIStatusError:
    """Translate a non-success ``httpx.Response`` into :class:`APIStatusError`,
    extracting the backend error envelope's ``message`` when present."""
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    error = body.get("error") if isinstance(body, dict) else None
    generic = f"Gumloop API returned HTTP {response.status_code}"
    if isinstance(error, dict):
        message = str(error.get("message") or generic)
    elif isinstance(error, str) and error:
        # Backend also returns a flat {"error": "tier_required_pro"} shape;
        # without this the code is dropped and the user only sees the status.
        # Having the message include the error code to help the user understand what went wrong, 
        # even if they don't know the code.
        message = f"{generic}: {error}"
    else:
        message = generic
    return APIStatusError(message, status_code=response.status_code, body=body)
