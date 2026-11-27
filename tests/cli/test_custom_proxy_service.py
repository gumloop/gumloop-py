from __future__ import annotations

import plistlib
import subprocess
from collections.abc import Sequence
from pathlib import Path

from gumloop.cli.custom_proxy_service import LaunchAgentService
from gumloop.cli.custom_proxy_service import SystemdUserService

EXECUTABLE = Path("/opt/gumloop bin/gumloop")
CLEARED_ENVIRONMENT = [
    "GUMLOOP_ACCESS_TOKEN",
    "GUMLOOP_API_KEY",
    "GUMLOOP_BASE_URL",
    "GUMLOOP_TEAM_ID",
    "GUMLOOP_USER_ID",
]


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")


def test_launch_agent_runs_the_custom_proxy_at_login_and_after_failures(tmp_path):
    runner = RecordingRunner()
    service = LaunchAgentService(home=tmp_path, run_command=runner, get_uid=lambda: 501)

    service.install(EXECUTABLE)

    assert plistlib.loads(service.plist_path.read_bytes()) == {
        "EnvironmentVariables": {
            **dict.fromkeys(CLEARED_ENVIRONMENT, ""),
            "HOME": str(tmp_path),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        "KeepAlive": {"SuccessfulExit": False},
        "Label": "com.gumloop.custom-proxy",
        "ProgramArguments": [str(EXECUTABLE), "browser", "proxy", "connect"],
        "RunAtLoad": True,
        "StandardErrorPath": str(tmp_path / ".gumloop" / "custom-proxy" / "service.log"),
        "ThrottleInterval": 30,
    }
    assert runner.calls == [
        ["launchctl", "bootout", "gui/501/com.gumloop.custom-proxy"],
        ["launchctl", "bootstrap", "gui/501", str(service.plist_path)],
    ]


def test_systemd_unit_runs_the_custom_proxy_as_written_at_login_and_after_failures(tmp_path):
    runner = RecordingRunner()
    service = SystemdUserService(config_home=tmp_path, run_command=runner)

    service.install(Path('/home/a$b/100%/"q"\\gumloop'))

    assert service.unit_path.read_text() == (
        "[Unit]\n"
        "Description=Gumloop personal proxy\n"
        "After=network-online.target\n"
        "\n"
        "[Service]\n"
        'ExecStart="/home/a$$b/100%%/\\"q\\"\\\\gumloop" "browser" "proxy" "connect"\n'
        f"UnsetEnvironment={' '.join(CLEARED_ENVIRONMENT)}\n"
        "Restart=on-failure\n"
        "RestartSec=30\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    assert runner.calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "gumloop-custom-proxy.service"],
        ["systemctl", "--user", "restart", "gumloop-custom-proxy.service"],
    ]
