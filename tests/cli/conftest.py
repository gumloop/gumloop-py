from __future__ import annotations

from collections.abc import Generator

import keyring
import keyring.backend
import keyring.errors
import pytest
from typer.testing import CliRunner


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    """Process-local keyring backend so CLI tests never touch the real OS keychain."""

    priority = 1.0  # pyright: ignore[reportAssignmentType]  # keyring exposes this as a classproperty

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError as exc:
            raise keyring.errors.PasswordDeleteError("Not found") from exc


@pytest.fixture(autouse=True)
def _isolated_cli_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Sandbox every CLI test: no inherited env, in-memory keyring."""
    for var in (
        "GUMLOOP_ACCESS_TOKEN",
        "GUMLOOP_API_KEY",
        "GUMLOOP_USER_ID",
        "GUMLOOP_BASE_URL",
        "GUMLOOP_TEAM_ID",
    ):
        monkeypatch.delenv(var, raising=False)

    previous = keyring.get_keyring()
    keyring.set_keyring(_InMemoryKeyring())
    try:
        yield
    finally:
        keyring.set_keyring(previous)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
