"""Unit tests for the macOS LaunchAgent Skill sync scheduler boundary."""

from __future__ import annotations

import plistlib
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from gumloop.sync.errors import SyncError
from gumloop.sync.scheduler import LaunchAgentScheduler
from gumloop.sync.scheduler import resolve_gumloop_executable
from gumloop.sync.scheduler import scheduler_for_current_platform

LABEL = "com.gumloop.sync"
SAFE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
UID = 501


class RecordingCommandRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._loaded = False
        self._gui_available = True
        self._bootstrap_error: str | None = None

    def set_loaded(self, loaded: bool) -> None:
        self._loaded = loaded

    def set_gui_available(self, available: bool) -> None:
        self._gui_available = available

    def fail_next_bootstrap(self, message: str = "bootstrap failed") -> None:
        self._bootstrap_error = message

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = list(args)
        self.calls.append(command)
        if command[:3] == ["launchctl", "print", f"gui/{UID}"]:
            if self._gui_available:
                return subprocess.CompletedProcess(command, 0, stdout="gui domain", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="domain unavailable")
        if command[:3] == ["launchctl", "print", f"gui/{UID}/{LABEL}"]:
            if self._loaded:
                return subprocess.CompletedProcess(command, 0, stdout="loaded", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="not loaded")
        if command[:2] == ["launchctl", "bootout"]:
            self._loaded = False
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["launchctl", "bootstrap"]:
            if self._bootstrap_error is not None:
                error = self._bootstrap_error
                self._bootstrap_error = None
                return subprocess.CompletedProcess(command, 1, stdout="", stderr=error)
            self._loaded = True
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=f"unexpected: {command}")


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _scheduler(home: Path, runner: RecordingCommandRunner) -> LaunchAgentScheduler:
    return LaunchAgentScheduler(
        home=home,
        run_command=runner,
        which=lambda name: "/bin/launchctl" if name == "launchctl" else None,
        get_uid=lambda: UID,
    )


def _read_plist(path: Path) -> dict[str, object]:
    return plistlib.loads(path.read_bytes())


class TestLaunchAgentPlistContract:
    def test_plist_path_and_label_are_deterministic(self, tmp_path: Path) -> None:
        """The owned LaunchAgent uses a fixed label under ~/Library/LaunchAgents."""
        home = tmp_path / "home"
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)

        assert scheduler.label == LABEL
        assert scheduler.plist_path == home / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    def test_install_writes_exact_command_interval_and_minimal_environment(
        self,
        tmp_path: Path,
    ) -> None:
        """Installed plist runs configured non-interactive sync with a fixed safe environment."""
        home = tmp_path / "home"
        executable = _make_executable(tmp_path / "bin" / "gumloop")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)

        scheduler.install(executable)

        payload = _read_plist(scheduler.plist_path)
        environment = cast(dict[str, str], payload["EnvironmentVariables"])
        program_arguments = cast(list[str], payload["ProgramArguments"])
        assert payload == {
            "EnvironmentVariables": {
                "GUMLOOP_ACCESS_TOKEN": "",
                "GUMLOOP_API_KEY": "",
                "GUMLOOP_BASE_URL": "",
                "GUMLOOP_TEAM_ID": "",
                "GUMLOOP_USER_ID": "",
                "HOME": str(home),
                "PATH": SAFE_PATH,
            },
            "Label": LABEL,
            "ProgramArguments": [str(executable), "sync", "--non-interactive"],
            "StartInterval": 14400,
        }
        assert scheduler.plist_path.stat().st_mode & 0o777 == 0o600
        assert environment["GUMLOOP_API_KEY"] == ""
        assert environment["GUMLOOP_ACCESS_TOKEN"] == ""
        assert environment["GUMLOOP_USER_ID"] == ""
        assert "--once" not in program_arguments

    def test_install_rejects_relative_executable_without_writing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A relative executable path is rejected before any LaunchAgent write."""
        home = tmp_path / "home"
        relative = Path("relative-gumloop")
        _make_executable(tmp_path / relative)
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SyncError) as raised:
            scheduler.install(relative)

        assert raised.value.code == "scheduler_unavailable"
        assert not scheduler.plist_path.exists()
        assert runner.calls == []


class TestLaunchAgentInstallAndRepair:
    def test_install_is_idempotent_when_plist_and_job_are_current(
        self,
        tmp_path: Path,
    ) -> None:
        """A current plist and loaded job skip bootout/bootstrap repair."""
        home = tmp_path / "home"
        executable = _make_executable(tmp_path / "bin" / "gumloop")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)
        scheduler.install(executable)
        before = scheduler.plist_path.read_bytes()
        runner.calls.clear()

        scheduler.install(executable)

        assert scheduler.plist_path.read_bytes() == before
        assert all(call[:2] == ["launchctl", "print"] for call in runner.calls)
        assert not any(call[:2] == ["launchctl", "bootout"] for call in runner.calls)
        assert not any(call[:2] == ["launchctl", "bootstrap"] for call in runner.calls)

    def test_install_repairs_stale_plist_and_reloads_job(
        self,
        tmp_path: Path,
    ) -> None:
        """A stale executable path is rewritten and the LaunchAgent job is reloaded."""
        home = tmp_path / "home"
        stale = _make_executable(tmp_path / "bin" / "old-gumloop")
        current = _make_executable(tmp_path / "bin" / "gumloop")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)
        scheduler.install(stale)
        runner.calls.clear()

        scheduler.install(current)

        payload = _read_plist(scheduler.plist_path)
        assert payload["ProgramArguments"] == [str(current), "sync", "--non-interactive"]
        assert ["launchctl", "bootout", f"gui/{UID}/{LABEL}"] in runner.calls
        assert ["launchctl", "bootstrap", f"gui/{UID}", str(scheduler.plist_path)] in runner.calls
        assert scheduler.is_current(current)

    def test_bootstrap_failure_restores_previous_plist(
        self,
        tmp_path: Path,
    ) -> None:
        """A failed reload restores the previous owned plist instead of leaving a partial install."""
        home = tmp_path / "home"
        previous = _make_executable(tmp_path / "bin" / "previous-gumloop")
        next_executable = _make_executable(tmp_path / "bin" / "next-gumloop")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)
        scheduler.install(previous)
        previous_bytes = scheduler.plist_path.read_bytes()
        runner.fail_next_bootstrap("cannot bootstrap")

        with pytest.raises(SyncError) as raised:
            scheduler.install(next_executable)

        assert raised.value.code == "scheduler_unavailable"
        assert scheduler.plist_path.read_bytes() == previous_bytes
        restored_arguments = cast(list[str], _read_plist(scheduler.plist_path)["ProgramArguments"])
        assert restored_arguments[0] == str(previous)
        assert scheduler.is_current(previous)

    def test_bootstrap_failure_removes_newly_written_plist(
        self,
        tmp_path: Path,
    ) -> None:
        """A first-install bootstrap failure removes the newly written owned plist."""
        home = tmp_path / "home"
        executable = _make_executable(tmp_path / "bin" / "gumloop")
        runner = RecordingCommandRunner()
        runner.fail_next_bootstrap("cannot bootstrap")
        scheduler = _scheduler(home, runner)

        with pytest.raises(SyncError) as raised:
            scheduler.install(executable)

        assert raised.value.code == "scheduler_unavailable"
        assert not scheduler.plist_path.exists()


class TestLaunchAgentCurrentAndRemove:
    def test_is_current_requires_matching_plist_and_loaded_job(
        self,
        tmp_path: Path,
    ) -> None:
        """Current status requires both the expected plist contents and a loaded job."""
        home = tmp_path / "home"
        executable = _make_executable(tmp_path / "bin" / "gumloop")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)
        scheduler.install(executable)
        assert scheduler.is_current(executable)

        runner.set_loaded(False)

        assert not scheduler.is_current(executable)

    def test_remove_unloads_job_and_deletes_owned_plist(
        self,
        tmp_path: Path,
    ) -> None:
        """Remove unloads the owned job and deletes only this LaunchAgent plist."""
        home = tmp_path / "home"
        executable = _make_executable(tmp_path / "bin" / "gumloop")
        other = home / "Library" / "LaunchAgents" / "com.example.other.plist"
        other.parent.mkdir(parents=True)
        other.write_text("other", encoding="utf-8")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)
        scheduler.install(executable)

        scheduler.remove()

        assert ["launchctl", "bootout", f"gui/{UID}/{LABEL}"] in runner.calls
        assert not scheduler.plist_path.exists()
        assert other.exists()


class TestLaunchAgentValidateAndPlatform:
    def test_validate_is_read_only(self, tmp_path: Path) -> None:
        """Validate proves launchctl readiness without writing a LaunchAgent."""
        home = tmp_path / "home"
        executable = _make_executable(tmp_path / "bin" / "gumloop")
        runner = RecordingCommandRunner()
        scheduler = _scheduler(home, runner)

        scheduler.validate(executable)

        assert not scheduler.plist_path.exists()
        assert runner.calls == [["launchctl", "print", f"gui/{UID}"]]

    def test_validate_translates_launchctl_execution_failure(
        self,
        tmp_path: Path,
    ) -> None:
        """A launchctl process failure remains a stable scheduler_unavailable error."""
        executable = _make_executable(tmp_path / "bin" / "gumloop")

        def fail_launchctl(_args: Sequence[str]) -> subprocess.CompletedProcess[str]:
            raise OSError("launchctl could not execute")

        scheduler = LaunchAgentScheduler(
            home=tmp_path / "home",
            run_command=fail_launchctl,
            which=lambda name: "/bin/launchctl" if name == "launchctl" else None,
            get_uid=lambda: UID,
        )

        with pytest.raises(SyncError) as raised:
            scheduler.validate(executable)

        assert raised.value.code == "scheduler_unavailable"
        assert not scheduler.plist_path.exists()

    def test_scheduler_for_current_platform_returns_launch_agent_on_macos(
        self,
        tmp_path: Path,
    ) -> None:
        """macOS selects the LaunchAgent scheduler adapter."""
        home = tmp_path / "home"

        scheduler = scheduler_for_current_platform(home=home, platform="darwin")

        assert isinstance(scheduler, LaunchAgentScheduler)
        assert scheduler.plist_path == home / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    def test_scheduler_for_current_platform_rejects_unsupported_platforms(
        self,
        tmp_path: Path,
    ) -> None:
        """Unsupported platforms fail closed with one-shot sync guidance."""
        with pytest.raises(SyncError) as raised:
            scheduler_for_current_platform(home=tmp_path, platform="linux")

        assert raised.value.code == "scheduler_unavailable"
        assert "gumloop sync --once --non-interactive" in str(raised.value)


class TestResolveGumloopExecutable:
    def test_resolve_preserves_stable_absolute_shim_path(self, tmp_path: Path) -> None:
        """Resolution keeps the PATH shim path instead of following a versioned symlink target."""
        real = _make_executable(tmp_path / "versions" / "1.2.3" / "gumloop")
        shim = tmp_path / "shims" / "gumloop"
        shim.parent.mkdir(parents=True)
        shim.symlink_to(real)

        resolved = resolve_gumloop_executable(which=lambda name: str(shim) if name == "gumloop" else None)

        assert resolved == shim
        assert resolved.is_symlink()

    def test_resolve_rejects_missing_command(self) -> None:
        """A missing gumloop command fails with scheduler_unavailable guidance."""
        with pytest.raises(SyncError) as raised:
            resolve_gumloop_executable(which=lambda _name: None)

        assert raised.value.code == "scheduler_unavailable"
        assert "gumloop sync --once --non-interactive" in str(raised.value)
