"""CLI invocation state: stored credentials + per-invocation overrides."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from gumloop import APIStatusError
from gumloop import AuthenticationError
from gumloop import Gumloop
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import clear_credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.oauth import refresh_oauth_tokens
from gumloop.sdk import DEFAULT_BASE_URL

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
        self.credentials.access_token = tokens.get("access_token")
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
            except Exception as refresh_error:
                clear_credentials()
                raise AuthenticationError(
                    "Session expired or revoked. Run `gumloop login` to sign in again."
                ) from refresh_error
            if not refreshed:
                raise
            return fn(self.build_client())
