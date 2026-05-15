from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode

import httpx

from gumloop.errors import to_api_error

DEFAULT_OAUTH_SCOPES = ("gumloop", "userinfo")


class OAuth:
    """OAuth 2.0 + PKCE helpers for the Gumloop developer API. Endpoints
    live at the root host (``/oauth/*``), not under ``/api/v1``, and don't
    consume a bearer token themselves."""

    def __init__(self, *, base_url: str, timeout: float) -> None:
        # OAuth endpoints sit at the root, so strip a trailing /api/v1 if the
        # caller reused the API base URL.
        self.base_url = base_url.rstrip("/").removesuffix("/api/v1")
        self.timeout = timeout

    @staticmethod
    def _scope_string(scopes: str | Sequence[str]) -> str:
        # Wire format is a single space-separated string per RFC 6749 §3.3.
        return scopes if isinstance(scopes, str) else " ".join(scopes)

    def register_client(
        self,
        redirect_uri: str,
        *,
        client_name: str = "Gumloop Python SDK",
        scopes: str | Sequence[str] = DEFAULT_OAUTH_SCOPES,
    ) -> dict[str, Any]:
        return self._post_json(
            "oauth/register",
            json={
                "client_name": client_name,
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": self._scope_string(scopes),
            },
        )

    def build_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        *,
        scopes: str | Sequence[str] = DEFAULT_OAUTH_SCOPES,
        resource: str | None = None,
        state: str | None = None,
    ) -> tuple[str, str, str]:
        code_verifier = secrets.token_urlsafe(64)
        state = state or secrets.token_urlsafe(24)
        # PKCE S256 challenge (RFC 7636 §4.2).
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        )
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": self._scope_string(scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if resource:
            params["resource"] = resource
        return f"{self.base_url}/oauth/authorize?{urlencode(params)}", code_verifier, state

    def exchange_code(
        self,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        return self._post_json(
            "oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )

    def refresh_token(self, client_id: str, refresh_token: str) -> dict[str, Any]:
        return self._post_json(
            "oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            },
        )

    def revoke(self, client_id: str, token: str) -> None:
        """Revoke an access or refresh token server-side (RFC 7009)."""
        self._post_json(
            "oauth/revoke",
            data={
                "client_id": client_id,
                "token": token,
            },
        )

    def _post_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = httpx.post(f"{self.base_url}/{path}", timeout=self.timeout, **kwargs)
        if response.status_code < 200 or response.status_code >= 300:
            raise to_api_error(response)
        # RFC 7009 /oauth/revoke returns 200 with an empty body on success.
        if not response.content:
            return {}
        return response.json()
