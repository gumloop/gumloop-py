from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from datetime import timezone
from pathlib import Path

import keyring
import keyring.backend
import keyring.errors
import pytest
import respx
from typer.testing import CliRunner

from tests.cli.sync_test_fakes import DeterministicClock
from tests.cli.sync_test_fakes import FakeAdvisoryLock
from tests.cli.sync_test_fakes import FakeScheduler
from tests.cli.sync_test_fakes import SyncCliTestEnvironment


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
def _isolated_cli_env(
    monkeypatch: pytest.MonkeyPatch,
    fake_executable_path: Path,
) -> Generator[None, None, None]:
    """Sandbox every CLI test: temporary home, no inherited env, in-memory keyring."""
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
def temporary_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def fake_executable_path(temporary_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    executable_path = temporary_home / "bin"
    executable_path.mkdir()
    monkeypatch.setenv("PATH", str(executable_path))
    return executable_path


@pytest.fixture
def sync_cli_environment(
    temporary_home: Path,
    fake_executable_path: Path,
    tmp_path: Path,
    respx_mock: respx.MockRouter,
) -> SyncCliTestEnvironment:
    target_root = tmp_path / "targets"
    target_root.mkdir()
    return SyncCliTestEnvironment(
        home=temporary_home,
        executable_path=fake_executable_path,
        target_root=target_root,
        scheduler=FakeScheduler(),
        clock=DeterministicClock(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
        lock=FakeAdvisoryLock(),
        http=respx_mock,
    )


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
