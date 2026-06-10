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
        self.code = self.error.get("code") if isinstance(self.error, dict) else None
        self.type = self.error.get("type") if isinstance(self.error, dict) else None
        self.param = self.error.get("param") if isinstance(self.error, dict) else None
        self.details = self.error.get("details", {}) if isinstance(self.error, dict) else {}


class BadRequestError(APIStatusError):
    """HTTP 400 — the request was malformed or contained invalid parameters."""


class PermissionDeniedError(APIStatusError):
    """HTTP 403 — the caller does not have permission to perform this action."""


class NotFoundError(APIStatusError):
    """HTTP 404 — the requested resource does not exist."""


class UnprocessableEntityError(APIStatusError):
    """HTTP 422 — the request was well-formed but semantically invalid."""


class RateLimitError(APIStatusError):
    """HTTP 429 — too many requests; back off and retry."""


class ServerError(APIStatusError):
    """HTTP 5xx — an unexpected error occurred on the Gumloop server."""


_STATUS_MAP: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    403: PermissionDeniedError,
    404: NotFoundError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}


def to_api_error(response: httpx.Response) -> APIStatusError:
    """Translate a non-success ``httpx.Response`` into the most specific
    :class:`APIStatusError` subclass available, extracting the backend error
    envelope's ``message`` when present."""
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    error = body.get("error") if isinstance(body, dict) else None
    message = (
        str(error.get("message") or f"Gumloop API returned HTTP {response.status_code}")
        if isinstance(error, dict)
        else f"Gumloop API returned HTTP {response.status_code}"
    )
    cls: type[APIStatusError]
    if response.status_code in _STATUS_MAP:
        cls = _STATUS_MAP[response.status_code]
    elif response.status_code >= 500:
        cls = ServerError
    else:
        cls = APIStatusError
    return cls(message, status_code=response.status_code, body=body)
