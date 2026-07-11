"""Implementation tests for the isolated Skill Sync CLI test environment."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from tests.cli.sync_test_fakes import SyncCliTestEnvironment


def test_cli_tests_resolve_temporary_home(temporary_home: Path) -> None:
    """CLI tests resolve every home variable to the temporary test tree."""
    resolved_home = Path.home()

    assert resolved_home == temporary_home
    assert os.environ["HOME"] == str(temporary_home)
    assert os.environ["USERPROFILE"] == str(temporary_home)


def test_cli_tests_use_fake_executable_path(fake_executable_path: Path) -> None:
    """CLI tests search only the isolated fake executable directory."""
    configured_path = os.environ["PATH"]

    assert configured_path == str(fake_executable_path)


def test_cli_temporary_home_uses_mode_0700(temporary_home: Path) -> None:
    """The temporary CLI home grants access only to its current user."""
    home_mode = stat.S_IMODE(temporary_home.stat().st_mode)

    assert home_mode == 0o700


def test_temporary_home_has_no_real_target_signals(temporary_home: Path) -> None:
    """The isolated home starts without any coding-agent or Gumloop directory."""
    entries = list(temporary_home.iterdir())

    assert entries == [temporary_home / "bin"]


def test_sync_environment_creates_target_under_fake_root(
    sync_cli_environment: SyncCliTestEnvironment,
) -> None:
    """A requested target directory is created only under the fake target root."""
    target = sync_cli_environment.create_target("cursor")

    assert target == sync_cli_environment.target_root / "cursor"
    assert target.is_dir()
