from __future__ import annotations

from typing import Any

import httpx


class GumloopError(Exception):
    """Base error for Gumloop SDK failures."""


class AuthenticationError(GumloopError):
    """Raised when an SDK method needs a missing credential."""


# Top-level body keys that belong to the standard error envelope and should
# NOT be folded into the synthesized ``details`` dict for legacy responses.
_RESERVED_BODY_KEYS = frozenset({"error", "code", "message", "type", "param", "details"})


def _synthesize_error_type(status_code: int) -> str:
    """Mirror the backend's ``api_error_type()`` mapping so consumers see a
    consistent ``type`` value regardless of which response shape arrived."""
    if status_code == 401:
        return "authentication_error"
    if status_code == 403:
        return "permission_error"
    if status_code == 404:
        return "not_found_error"
    if status_code == 429:
        return "rate_limit_error"
    if status_code >= 500:
        return "api_error"
    return "invalid_request_error"


def _legacy_details_from_body(body: dict) -> dict[str, Any]:
    """Collect loose top-level fields from the legacy flat error shape into a
    ``details`` dict — e.g. ``denied_keys``, ``minimum_tier``, ``user_type``,
    ``limit_key``, ``current``, ``allowed``. Excludes envelope-reserved keys."""
    return {k: v for k, v in body.items() if k not in _RESERVED_BODY_KEYS}


def _legacy_message(code: str, details: dict[str, Any], status_code: int) -> str:
    """Build a meaningful exception message from a legacy flat-shape response.

    Combines the string ``code`` with whatever structured context is available
    (``denied_keys``, ``minimum_tier``, etc.) so renderings are informative
    instead of a generic ``"Gumloop API returned HTTP 403"`` fallback.

    Examples:
      - ``policy_denied (denied_keys=['apollo_organization_enrichment'])``
      - ``tier_required_enterprise (denied_keys=['organization:manage_sso'], minimum_tier='enterprise')``
    """
    if not code:
        return f"Gumloop API returned HTTP {status_code}"
    if not details:
        return code
    ctx = ", ".join(f"{k}={v!r}" for k, v in details.items())
    return f"{code} ({ctx})"


class APIStatusError(GumloopError):
    """Raised when Gumloop returns a non-success HTTP status.

    Handles both error envelope shapes returned by the backend:

    - **Canonical envelope** — emitted by ``api_error()`` and most public
      API routes::

          {"error": {"code": ..., "message": ..., "type": ...,
                     "param": ..., "details": {...}}}

    - **Legacy flat shape** — emitted by the permission decorator
      (``@require_permission``) and its enforcer helpers::

          {"error": "policy_denied", "denied_keys": [...]}
          {"error": "tier_required_enterprise", "minimum_tier": "enterprise",
           "denied_keys": [...]}
          {"error": "feature_restricted", "user_type": "feature-restricted",
           "denied_keys": [...]}

    For the legacy shape, the string ``error`` becomes ``self.code``, the
    other top-level fields become ``self.details``, and ``self.type`` is
    synthesized from the HTTP status code (mirroring the backend's
    ``api_error_type()`` mapping).
    """

    def __init__(self, message: str, *, status_code: int, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body

        raw_error = body.get("error") if isinstance(body, dict) else None
        self.error = raw_error
        if isinstance(raw_error, dict):
            # Canonical envelope — fields live inside body["error"].
            self.code = raw_error.get("code")
            self.type = raw_error.get("type")
            self.param = raw_error.get("param")
            self.details = raw_error.get("details", {})
        elif isinstance(raw_error, str) and isinstance(body, dict):
            # Legacy flat shape — error is the code string, other top-level
            # fields become details, type is synthesized from status.
            self.code = raw_error
            self.type = _synthesize_error_type(status_code)
            self.param = None
            self.details = _legacy_details_from_body(body)
        else:
            self.code = None
            self.type = None
            self.param = None
            self.details = {}


def to_api_error(response: httpx.Response) -> APIStatusError:
    """Translate a non-success ``httpx.Response`` into :class:`APIStatusError`,
    extracting the most informative message available from either error shape.

    Resolution order:
      1. Canonical envelope ``body["error"]["message"]`` — direct human string.
      2. Legacy flat shape — synthesize ``"<code> (<context>)"`` from the
         string code and loose top-level fields (``denied_keys``, etc.).
      3. Fallback — generic ``"Gumloop API returned HTTP <status>"``.
    """
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    fallback = f"Gumloop API returned HTTP {response.status_code}"
    error = body.get("error") if isinstance(body, dict) else None

    if isinstance(error, dict):
        message = str(error.get("message") or fallback)
    elif isinstance(error, str) and isinstance(body, dict):
        details = _legacy_details_from_body(body)
        message = _legacy_message(error, details, response.status_code)
    else:
        message = fallback

    return APIStatusError(message, status_code=response.status_code, body=body)
