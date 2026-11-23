from __future__ import annotations

import plistlib
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from gumloop.cli.linked_proxy_service import LaunchAgentService
from gumloop.cli.linked_proxy_service import SystemdUserService
from gumloop.cli.linked_proxy_service import service_for_current_platform

EXECUTABLE = Path("/opt/gumloop bin/gumloop")


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")


def test_launch_agent_runs_the_linked_proxy_at_login_and_after_failures(tmp_path):
    runner = RecordingRunner()
    service = LaunchAgentService(home=tmp_path, run_command=runner, get_uid=lambda: 501)

    service.install(EXECUTABLE)

    plist = plistlib.loads(service.plist_path.read_bytes())
    assert plist["ProgramArguments"] == [str(EXECUTABLE), "browser", "proxy", "run"]
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert ["launchctl", "bootstrap", "gui/501", str(service.plist_path)] in runner.calls

    service.remove()

    assert not service.is_installed()
    assert runner.calls[-1] == ["launchctl", "bootout", "gui/501/com.gumloop.linked-proxy"]


def test_systemd_unit_runs_the_linked_proxy_at_login_and_after_failures(tmp_path):
    runner = RecordingRunner()
    service = SystemdUserService(config_home=tmp_path, run_command=runner)

    service.install(EXECUTABLE)

    unit = service.unit_path.read_text()
    assert 'ExecStart="/opt/gumloop bin/gumloop" "browser" "proxy" "run"\n' in unit
    assert "Restart=on-failure\n" in unit
    assert "WantedBy=default.target\n" in unit
    assert runner.calls[-2:] == [
        ["systemctl", "--user", "enable", "gumloop-linked-proxy.service"],
        ["systemctl", "--user", "restart", "gumloop-linked-proxy.service"],
    ]

    service.remove()

    assert not service.is_installed()
    assert ["systemctl", "--user", "disable", "--now", "gumloop-linked-proxy.service"] in runner.calls


def test_systemd_unit_runs_an_executable_path_with_special_characters_as_written(tmp_path):
    service = SystemdUserService(config_home=tmp_path, run_command=RecordingRunner())

    service.install(Path('/home/a$b/100%/"q"\\gumloop'))

    unit = service.unit_path.read_text()
    assert 'ExecStart="/home/a$$b/100%%/\\"q\\"\\\\gumloop" "browser" "proxy" "connect"\n' in unit


def test_systemd_unit_goes_where_systemd_looks_for_user_units(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    service = service_for_current_platform(home=tmp_path)

    assert isinstance(service, SystemdUserService)
    assert service.unit_path == tmp_path / "config" / "systemd" / "user" / "gumloop-linked-proxy.service"
