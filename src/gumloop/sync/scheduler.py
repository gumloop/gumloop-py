from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from gumloop.sync.errors import SyncError

_LAUNCH_AGENT_LABEL = "com.gumloop.sync"
SYNC_INTERVAL_SECONDS = 14400
_SAFE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
_ONCE_GUIDANCE = "Use `gumloop sync --once --non-interactive` for a one-shot sync."


class SyncScheduler(Protocol):
    def validate(self, executable_path: Path) -> None: ...

    def install(self, executable_path: Path) -> None: ...

    def is_current(self, executable_path: Path) -> bool: ...

    def remove(self) -> None: ...


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class LaunchAgentScheduler:
    """macOS LaunchAgent adapter for configured background Skill sync."""

    def __init__(
        self,
        *,
        home: Path,
        run_command: CommandRunner | None = None,
        which: Callable[[str], str | None] | None = None,
        get_uid: Callable[[], int] | None = None,
    ) -> None:
        self._home = home
        self._run_command = run_command or _run_command
        self._which = which or shutil.which
        self._get_uid = get_uid or os.getuid

    @property
    def label(self) -> str:
        return _LAUNCH_AGENT_LABEL

    @property
    def plist_path(self) -> Path:
        return self._home / "Library" / "LaunchAgents" / f"{_LAUNCH_AGENT_LABEL}.plist"

    def validate(self, executable_path: Path) -> None:
        _require_absolute_executable(executable_path)
        self._require_launchctl()
        self._require_gui_domain()

    def install(self, executable_path: Path) -> None:
        self.validate(executable_path)
        if self.is_current(executable_path):
            return

        destination = self.plist_path
        previous_bytes = destination.read_bytes() if destination.is_file() else None
        wrote_plist = False
        try:
            self._write_plist(executable_path)
            wrote_plist = True
            self._bootout_best_effort()
            self._bootstrap()
        except SyncError:
            if wrote_plist:
                self._restore_plist(previous_bytes)
                if previous_bytes is not None:
                    try:
                        self._bootstrap()
                    except SyncError:
                        pass
            raise

    def is_current(self, executable_path: Path) -> bool:
        destination = self.plist_path
        if not destination.is_file():
            return False
        try:
            current = plistlib.loads(destination.read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError):
            return False
        if current != self._plist_payload(executable_path):
            return False
        return self._job_is_loaded()

    def remove(self) -> None:
        self._bootout_best_effort()
        destination = self.plist_path
        try:
            destination.unlink(missing_ok=True)
        except OSError as error:
            raise SyncError(
                "scheduler_unavailable",
                f"Could not remove the Skill sync LaunchAgent: {destination}. {_ONCE_GUIDANCE}",
                details={"path": str(destination), "reason": str(error)},
            ) from error

    def _plist_payload(self, executable_path: Path) -> dict[str, object]:
        return {
            "EnvironmentVariables": {
                "GUMLOOP_ACCESS_TOKEN": "",
                "GUMLOOP_API_KEY": "",
                "GUMLOOP_BASE_URL": "",
                "GUMLOOP_TEAM_ID": "",
                "GUMLOOP_USER_ID": "",
                "HOME": str(self._home),
                "PATH": _SAFE_PATH,
            },
            "Label": _LAUNCH_AGENT_LABEL,
            "ProgramArguments": [str(executable_path), "sync", "--non-interactive"],
            "StartInterval": SYNC_INTERVAL_SECONDS,
        }

    def _write_plist(self, executable_path: Path) -> None:
        destination = self.plist_path
        payload = self._plist_payload(executable_path)
        temporary_path: Path | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary_path.chmod(0o600)
                temporary.write(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True))
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(destination)
            temporary_path = None
            try:
                destination.chmod(0o600)
            except OSError:
                pass
        except OSError as error:
            raise SyncError(
                "scheduler_unavailable",
                f"Could not write the Skill sync LaunchAgent: {destination}. {_ONCE_GUIDANCE}",
                details={"path": str(destination), "reason": str(error)},
            ) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _restore_plist(self, previous_bytes: bytes | None) -> None:
        destination = self.plist_path
        try:
            if previous_bytes is None:
                destination.unlink(missing_ok=True)
                return
            destination.write_bytes(previous_bytes)
            destination.chmod(0o600)
        except OSError:
            pass

    def _require_launchctl(self) -> None:
        if self._which("launchctl") is None:
            raise SyncError(
                "scheduler_unavailable",
                f"launchctl is unavailable, so background Skill sync cannot be installed. {_ONCE_GUIDANCE}",
            )

    def _require_gui_domain(self) -> None:
        try:
            result = self._run_command(["launchctl", "print", self._gui_domain()])
        except (OSError, subprocess.SubprocessError) as error:
            raise SyncError(
                "scheduler_unavailable",
                f"Could not inspect the macOS launchd domain. {_ONCE_GUIDANCE}",
                details={"reason": str(error)},
            ) from error
        if result.returncode != 0:
            raise SyncError(
                "scheduler_unavailable",
                (
                    "The macOS GUI launchd domain is unavailable, so background "
                    f"Skill sync cannot be installed. {_ONCE_GUIDANCE}"
                ),
                details={
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                },
            )

    def _job_is_loaded(self) -> bool:
        try:
            result = self._run_command(["launchctl", "print", self._job_target()])
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def _bootout_best_effort(self) -> None:
        try:
            self._run_command(["launchctl", "bootout", self._job_target()])
        except (OSError, subprocess.SubprocessError):
            pass

    def _bootstrap(self) -> None:
        try:
            result = self._run_command(["launchctl", "bootstrap", self._gui_domain(), str(self.plist_path)])
        except (OSError, subprocess.SubprocessError) as error:
            raise SyncError(
                "scheduler_unavailable",
                f"Could not load the Skill sync LaunchAgent. {_ONCE_GUIDANCE}",
                details={"reason": str(error), "path": str(self.plist_path)},
            ) from error
        if result.returncode != 0:
            raise SyncError(
                "scheduler_unavailable",
                f"Could not load the Skill sync LaunchAgent. {_ONCE_GUIDANCE}",
                details={
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                    "path": str(self.plist_path),
                },
            )

    def _gui_domain(self) -> str:
        return f"gui/{self._get_uid()}"

    def _job_target(self) -> str:
        return f"{self._gui_domain()}/{_LAUNCH_AGENT_LABEL}"


def scheduler_for_current_platform(
    *,
    home: Path,
    platform: str | None = None,
) -> SyncScheduler:
    current_platform = sys.platform if platform is None else platform
    if current_platform == "darwin":
        return LaunchAgentScheduler(home=home)
    raise SyncError(
        "scheduler_unavailable",
        f"Background Skill sync scheduling is unavailable on this platform. {_ONCE_GUIDANCE}",
        details={"platform": current_platform},
    )


def resolve_gumloop_executable(
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> Path:
    found = which("gumloop")
    if found is None:
        raise SyncError(
            "scheduler_unavailable",
            f"Could not find an absolute `gumloop` executable on PATH. {_ONCE_GUIDANCE}",
        )
    path = Path(found)
    if not path.is_absolute():
        path = path.absolute()
    _require_absolute_executable(path)
    return path


def _require_absolute_executable(executable_path: Path) -> None:
    if not executable_path.is_absolute():
        raise SyncError(
            "scheduler_unavailable",
            f"The Skill sync scheduler requires an absolute `gumloop` executable path. {_ONCE_GUIDANCE}",
            details={"path": str(executable_path)},
        )
    if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
        raise SyncError(
            "scheduler_unavailable",
            f"The Skill sync scheduler executable is missing or not executable: {executable_path}. {_ONCE_GUIDANCE}",
            details={"path": str(executable_path)},
        )


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
