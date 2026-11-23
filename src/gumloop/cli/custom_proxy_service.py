"""Runs ``gumloop browser proxy connect`` in the background: a LaunchAgent on
macOS, a systemd user unit on Linux. Both start it at login and restart it
after a failure, but not after a clean exit, which is how it stops once the
user logs out or Gumloop refuses the personal proxy."""

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

from gumloop import GumloopError

LAUNCH_AGENT_LABEL = "com.gumloop.custom-proxy"
SYSTEMD_UNIT = "gumloop-custom-proxy.service"
_CONNECT_ARGUMENTS = ("browser", "proxy", "connect")
_RESTART_SECONDS = 30
# Present only when systemd is the running init system.
_SYSTEMD_BOOTED_DIR = Path("/run/systemd/system")
_SAFE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# Credentials come from the keychain, never from the shell that ran `add`.
_CLEARED_ENVIRONMENT = (
    "GUMLOOP_ACCESS_TOKEN",
    "GUMLOOP_API_KEY",
    "GUMLOOP_BASE_URL",
    "GUMLOOP_TEAM_ID",
    "GUMLOOP_USER_ID",
)

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class NoBackgroundService(GumloopError):
    """This computer can't keep the personal proxy running in the background, such
    as a Linux container or SSH session without a systemd user session."""


class CustomProxyService(Protocol):
    def install(self, executable_path: Path) -> None:
        """Writes the service and (re)starts it."""
        ...

    def remove(self) -> None: ...

    def is_installed(self) -> bool: ...


class LaunchAgentService:
    def __init__(
        self,
        *,
        home: Path,
        run_command: CommandRunner | None = None,
        get_uid: Callable[[], int] | None = None,
    ) -> None:
        self._home = home
        self._run_command = run_command or _run_command
        self._get_uid = get_uid or os.getuid

    @property
    def plist_path(self) -> Path:
        return self._home / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"

    def install(self, executable_path: Path) -> None:
        log_path = self._home / ".gumloop" / "custom-proxy" / "service.log"
        try:
            log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise GumloopError(f"Could not create {log_path.parent}: {error}") from error
        payload = {
            "EnvironmentVariables": {
                **dict.fromkeys(_CLEARED_ENVIRONMENT, ""),
                "HOME": str(self._home),
                "PATH": _SAFE_PATH,
            },
            "KeepAlive": {"SuccessfulExit": False},
            "Label": LAUNCH_AGENT_LABEL,
            "ProgramArguments": [str(executable_path), *_CONNECT_ARGUMENTS],
            "RunAtLoad": True,
            "StandardErrorPath": str(log_path),
            "ThrottleInterval": _RESTART_SECONDS,
        }
        _write_private(self.plist_path, plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True))
        self._run_command(["launchctl", "bootout", self._job_target()])
        _check(self._run_command(["launchctl", "bootstrap", f"gui/{self._get_uid()}", str(self.plist_path)]))

    def remove(self) -> None:
        self._run_command(["launchctl", "bootout", self._job_target()])
        _unlink(self.plist_path)

    def is_installed(self) -> bool:
        return self.plist_path.is_file()

    def _job_target(self) -> str:
        return f"gui/{self._get_uid()}/{LAUNCH_AGENT_LABEL}"


class SystemdUserService:
    def __init__(self, *, config_home: Path, run_command: CommandRunner | None = None) -> None:
        self._config_home = config_home
        self._run_command = run_command or _run_command

    @property
    def unit_path(self) -> Path:
        return self._config_home / "systemd" / "user" / SYSTEMD_UNIT

    def install(self, executable_path: Path) -> None:
        command = " ".join(_systemd_quote(part) for part in [str(executable_path), *_CONNECT_ARGUMENTS])
        unit = (
            "[Unit]\n"
            "Description=Gumloop personal proxy\n"
            "After=network-online.target\n"
            "\n"
            "[Service]\n"
            f"ExecStart={command}\n"
            f"UnsetEnvironment={' '.join(_CLEARED_ENVIRONMENT)}\n"
            "Restart=on-failure\n"
            f"RestartSec={_RESTART_SECONDS}\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        _write_private(self.unit_path, unit.encode())
        _check(self._systemctl("daemon-reload"))
        _check(self._systemctl("enable", SYSTEMD_UNIT))
        _check(self._systemctl("restart", SYSTEMD_UNIT))

    def remove(self) -> None:
        self._systemctl("disable", "--now", SYSTEMD_UNIT)
        _unlink(self.unit_path)
        self._systemctl("daemon-reload")

    def is_installed(self) -> bool:
        return self.unit_path.is_file()

    def _systemctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run_command(["systemctl", "--user", *args])


def service_for_current_platform(*, home: Path | None = None) -> CustomProxyService:
    home = home or Path.home()
    if sys.platform == "darwin":
        return LaunchAgentService(home=home)
    if sys.platform.startswith("linux"):
        if not _SYSTEMD_BOOTED_DIR.is_dir() or not os.environ.get("XDG_RUNTIME_DIR"):
            raise NoBackgroundService("This computer has no systemd user session to run the personal proxy in.")
        return SystemdUserService(config_home=Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config"))
    raise GumloopError("`gumloop browser proxy` runs on macOS and Linux only.")


def gumloop_executable() -> Path:
    found = shutil.which("gumloop")
    if found is None:
        raise GumloopError(
            "Could not find the `gumloop` command on PATH, so this computer can't stay connected in the background."
        )
    return Path(found).absolute()


def _systemd_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return f'"{escaped}"'


def _write_private(destination: Path, content: bytes) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as file:
            staging = Path(file.name)
            staging.chmod(0o600)
            file.write(content)
        staging.replace(destination)
    except OSError as error:
        raise GumloopError(f"Could not write {destination}: {error}") from error


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise GumloopError(f"Could not remove {path}: {error}") from error


def _check(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        command = " ".join(str(part) for part in result.args)
        raise GumloopError(f"`{command}` failed: {result.stderr.strip() or result.returncode}")


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(args), check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise GumloopError(f"Could not run `{args[0]}`: {error}") from error
