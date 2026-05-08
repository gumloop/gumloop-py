from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode

import httpx

from gumloop.errors import APIStatusError

DEFAULT_OAUTH_SCOPES = ("gumloop", "userinfo")


def _scope_string(scopes: str | Sequence[str]) -> str:
    return scopes if isinstance(scopes, str) else " ".join(scopes)


def _oauth_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized[:-7] if normalized.endswith("/api/v1") else normalized


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class Auth:
    def __init__(self, *, base_url: str, timeout: float) -> None:
        self.base_url = _oauth_base_url(base_url)
        self.timeout = timeout

    def register_client(
        self,
        redirect_uri: str,
        client_name: str = "Gumloop Python SDK",
        *,
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
                "scope": _scope_string(scopes),
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
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": _scope_string(scopes),
            "state": state,
            "code_challenge": _code_challenge(code_verifier),
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

    def _post_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = httpx.post(f"{self.base_url}/{path}", timeout=self.timeout, **kwargs)
        if response.status_code < 200 or response.status_code >= 300:
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
            raise APIStatusError(
                message,
                status_code=response.status_code,
                body=body,
            )
        return response.json()
