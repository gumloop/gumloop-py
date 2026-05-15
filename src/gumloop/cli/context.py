"""CLI invocation state: stored credentials + per-invocation overrides."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

from gumloop import APIStatusError
from gumloop import AuthenticationError
from gumloop import Gumloop
from gumloop._client import DEFAULT_BASE_URL
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import clear_credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.oauth import refresh_oauth_tokens

T = TypeVar("T")


@dataclass
class CliContext:
    credentials: Credentials
    # ``None`` for any override = fall back to credentials or SDK default.
    base_url_override: str | None = None
    team_id_override: str | None = None
    user_id_override: str | None = None

    @property
    def effective_base_url(self) -> str:
        return self.base_url_override or self.credentials.base_url or DEFAULT_BASE_URL

    @property
    def effective_team_id(self) -> str | None:
        return self.team_id_override

    @property
    def effective_user_id(self) -> str | None:
        return self.user_id_override or self.credentials.user_id

    @property
    def effective_auth_method(self) -> str | None:
        return self.credentials.auth_method

    def build_client(self) -> Gumloop:
        # x-auth-key (user_id header) is API-key auth only; OAuth omits it.
        using_api_key = self.effective_auth_method == "api_key"
        return Gumloop(
            access_token=self.credentials.bearer_token,
            user_id=self.effective_user_id if using_api_key else None,
            base_url=self.effective_base_url,
        )

    def refresh_if_possible(self) -> bool:
        if self.effective_auth_method != "oauth" or not self.credentials.refresh_token:
            return False
        tokens = refresh_oauth_tokens(
            base_url=self.effective_base_url,
            refresh_token=self.credentials.refresh_token,
        )
        # 2xx with no access_token = broken server response; treat as a hard
        # auth failure so we don't overwrite the stored token with ``None``
        # and then retry the original call unauthenticated.
        new_access = tokens.get("access_token")
        if not new_access:
            raise AuthenticationError(
                "Refresh response did not include an access_token. Run `gumloop login` to sign in again."
            )
        self.credentials.access_token = new_access
        if tokens.get("refresh_token"):
            self.credentials.refresh_token = tokens["refresh_token"]
        save_credentials(self.credentials)
        return True

    def call_with_refresh(self, fn: Callable[[Gumloop], T]) -> T:
        client = self.build_client()
        try:
            return fn(client)
        except APIStatusError as error:
            if error.status_code != 401:
                raise
            try:
                refreshed = self.refresh_if_possible()
            except APIStatusError as refresh_error:
                # Only a 4xx from the token endpoint means the refresh token
                # itself is dead. 5xx / network errors are transient and must
                # NOT wipe the keychain - otherwise a flaky connection forces
                # a re-login even though the credentials are still valid.
                if 400 <= refresh_error.status_code < 500:
                    clear_credentials()
                    raise AuthenticationError(
                        "Session expired or revoked. Run `gumloop login` to sign in again."
                    ) from refresh_error
                raise
            except AuthenticationError:
                # refresh_if_possible already classified this as terminal.
                clear_credentials()
                raise
            except httpx.HTTPError:
                # Transport-layer failure (timeout, DNS, conn reset). Surface
                # untouched so the user can retry with creds intact.
                raise
            if not refreshed:
                raise
            return fn(self.build_client())
