from __future__ import annotations

from typing import Any

import httpx

_FLAT_RESERVED_KEYS = frozenset({"error", "message", "error_description", "trace_id", "metadata"})


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
            self.type = self.error.get("type")
            self.param = self.error.get("param")
            details = self.error.get("details")
        else:
            self.code = self.error if isinstance(self.error, str) else None
            self.type = None
            self.param = None
            details = _flat_details(body)
        self.details = details if isinstance(details, dict) else {}


def _flat_details(body: Any) -> dict[str, Any]:
    """Extract machine-readable context from a flat error body.

    Prefer PublicError ``metadata``. Otherwise keep legacy top-level fields
    such as ``minimum_tier`` / ``denied_keys`` (tier/policy denials).
    """
    if not isinstance(body, dict):
        return {}
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return {key: value for key, value in body.items() if key not in _FLAT_RESERVED_KEYS}


def to_api_error(response: httpx.Response) -> APIStatusError:
    """Translate a non-success ``httpx.Response`` into :class:`APIStatusError`.

    Supports:
    - Nested developer API: ``{"error": {"code", "message", "details", ...}}``
    - Flat PublicError: ``{"error": "code", "message": "...", "metadata": {...}}``
    - OAuth RFC: ``{"error": "code", "error_description": "..."}``
    - Legacy bare / enriched codes: ``{"error": "tier_required_pro", ...}``
    """
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    fallback = f"Gumloop API returned HTTP {response.status_code}"
    if not isinstance(body, dict):
        return APIStatusError(fallback, status_code=response.status_code, body=body)

    error = body.get("error")
    top_level_message = body.get("message")
    error_description = body.get("error_description")

    if isinstance(error, dict):
        message = str(error.get("message") or fallback)
    elif isinstance(top_level_message, str) and top_level_message:
        message = top_level_message
    elif isinstance(error_description, str) and error_description:
        message = error_description
    elif isinstance(error, str) and error:
        message = f"{fallback}: {error}"
    else:
        message = fallback

    return APIStatusError(message, status_code=response.status_code, body=body)
