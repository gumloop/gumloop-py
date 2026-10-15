from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

_ACCESS = {
    "access": {
        "grants_visibility": "full",
        "people": [],
        "teams": [],
        "organization_access": None,
        "link": "none",
        "link_role": None,
        "password_protected": False,
        "hidden_by_role": None,
    },
    "notified": ["ada@example.com"],
}


def _save_key() -> None:
    save_credentials(Credentials(api_key="key"))


@respx.mock
def test_set_access_sends_people_teams_and_organization_none(cli_runner: CliRunner) -> None:
    route = respx.put(f"{API_BASE}/artifacts/artifact_abc/access").mock(return_value=httpx.Response(200, json=_ACCESS))
    _save_key()

    result = cli_runner.invoke(
        app,
        [
            "artifacts",
            "set-access",
            "artifact_abc",
            "--share",
            "ada@example.com:viewer",
            "--share-team",
            "team_abc:editor",
            "--organization",
            "none",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "share": [
            {"type": "person", "email": "ada@example.com", "role": "viewer"},
            {"type": "team", "team_id": "team_abc", "role": "editor"},
        ],
        "remove": [{"type": "organization"}],
    }


@respx.mock
def test_password_stdin_sets_the_password_before_the_access_change(cli_runner: CliRunner) -> None:
    password_route = respx.put(f"{API_BASE}/artifacts/artifact_abc/password").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    access_route = respx.put(f"{API_BASE}/artifacts/artifact_abc/access").mock(
        return_value=httpx.Response(200, json=_ACCESS)
    )
    _save_key()

    result = cli_runner.invoke(
        app,
        [
            "artifacts",
            "set-access",
            "artifact_abc",
            "--password-stdin",
            "--link",
            "password",
            "--json",
        ],
        input="secret\n",
    )

    assert result.exit_code == 0, result.output
    assert json.loads(password_route.calls[0].request.content) == {"password": "secret"}
    assert json.loads(access_route.calls[0].request.content) == {"link": {"mode": "password"}}
    assert password_route.calls[0].request.url.path.endswith("/password")
    assert respx.calls[0].request.url.path.endswith("/password")
    assert respx.calls[1].request.url.path.endswith("/access")


@respx.mock
def test_password_stdin_strips_a_windows_line_ending(cli_runner: CliRunner) -> None:
    route = respx.put(f"{API_BASE}/artifacts/artifact_abc/password").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    _save_key()

    result = cli_runner.invoke(
        app,
        ["artifacts", "set-access", "artifact_abc", "--password-stdin", "--json"],
        input="secret\r\n",
    )

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"password": "secret"}


@respx.mock
def test_password_only_prints_the_password_response(cli_runner: CliRunner) -> None:
    respx.put(f"{API_BASE}/artifacts/artifact_abc/password").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    _save_key()

    result = cli_runner.invoke(
        app,
        ["artifacts", "set-access", "artifact_abc", "--password-stdin", "--json"],
        input="secret",
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"success": True}


@respx.mock
def test_skill_and_session_access_use_their_own_paths(cli_runner: CliRunner) -> None:
    skill_route = respx.get(f"{API_BASE}/skills/skill_abc/access").mock(
        return_value=httpx.Response(200, json={"access": _ACCESS["access"]})
    )
    session_route = respx.put(f"{API_BASE}/sessions/session_abc/access").mock(
        return_value=httpx.Response(200, json=_ACCESS)
    )
    _save_key()

    skill = cli_runner.invoke(app, ["skills", "access", "skill_abc", "--json"])
    session = cli_runner.invoke(
        app,
        ["sessions", "set-access", "session_abc", "--remove", "ada@example.com", "--json"],
    )

    assert skill.exit_code == 0, skill.output
    assert session.exit_code == 0, session.output
    assert skill_route.called
    assert json.loads(session_route.calls[0].request.content) == {
        "remove": [{"type": "person", "email": "ada@example.com"}],
    }
