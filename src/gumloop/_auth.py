"""Credential resolution shared by the sync and async transports."""

from __future__ import annotations

import os

from gumloop.errors import AuthenticationError


class EnvToken(str):
    """Access token sourced from ``GUMLOOP_ACCESS_TOKEN``.

    Stays live: ``current()`` returns the env var's present value, so
    platform-rotated tokens (e.g. per-call sandbox credentials) are picked up
    on every request. Explicit tokens are plain strings and never change.
    """

    @classmethod
    def from_env(cls) -> EnvToken | None:
        token = os.environ.get("GUMLOOP_ACCESS_TOKEN")
        return cls(token) if token else None

    def current(self) -> str:
        return os.environ.get("GUMLOOP_ACCESS_TOKEN") or str(self)


def auth_headers(access_token: str | None, user_id: str | None) -> dict[str, str]:
    if isinstance(access_token, EnvToken):
        access_token = access_token.current()
    if not access_token:
        raise AuthenticationError("access_token, api_key, or GUMLOOP_ACCESS_TOKEN is required")
    headers = {"Authorization": f"Bearer {access_token}"}
    if user_id:
        headers["x-auth-key"] = user_id
    return headers
