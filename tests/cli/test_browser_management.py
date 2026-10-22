from __future__ import annotations

import json

import pytest
import respx

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

PROFILE = {"profile_id": "profile-1", "owner_id": "actor", "owner_scope": "personal", "name": "Work"}
OPERATIONS = [
    (["create", "Work"], "POST", "browser-profiles", {"name": "Work"}),
    (["get", "profile-1"], "GET", "browser-profiles/profile-1", None),
    (["update", "profile-1", "--name", "Work", "--default"], "PATCH", "browser-profiles/profile-1",
     {"name": "Work", "is_default": True}),
    (["delete", "profile-1"], "DELETE", "browser-profiles/profile-1", None),
]


@pytest.mark.parametrize(("args", "method", "path", "body"), OPERATIONS)
@respx.mock
def test_personal_profile_commands(cli_runner, args, method, path, body):
    payload = {"status": "success"} if args[0] == "delete" else PROFILE
    route = respx.request(method, f"{API_BASE}/{path}").respond(200, json=payload)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["browser", "profiles", *args, "--json"])
    assert result.exit_code == 0, result.output
    actual = json.loads(result.output)
    assert all(actual[key] == value for key, value in payload.items())
    assert not route.calls[0].request.url.params
    assert (json.loads(route.calls[0].request.content) if route.calls[0].request.content else None) == body


@pytest.mark.parametrize(("args", "method", "path", "body"), OPERATIONS)
@respx.mock
def test_personal_profile_commands_reject_global_team(cli_runner, args, method, path, body):
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["--team-id", "team", "browser", "profiles", *args, "--json"])
    assert result.exit_code == 1
    assert "does not accept --team-id" in result.output
    assert not respx.calls


@pytest.mark.parametrize("args", [["create", "  "], ["update", "profile-1"], ["update", "profile-1", "--name", "  "]])
@respx.mock
def test_invalid_profile_arguments_fail_before_http(cli_runner, args):
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["browser", "profiles", *args, "--json"])
    assert result.exit_code == 1
    assert not respx.calls


@respx.mock
def test_session_browser_prints_authenticated_viewer_link(cli_runner):
    payload = {"session_id": "session-1", "viewer_url": "https://gumloop.com/agents/agent-1/chat/session-1"}
    respx.get(f"{API_BASE}/sessions/session-1/browser").respond(200, json=payload)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "browser", "session-1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload


@respx.mock
def test_session_browser_rejects_global_team(cli_runner):
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["--team-id", "team", "sessions", "browser", "session", "--json"])
    assert result.exit_code == 1
    assert "do not accept --team-id" in result.output
    assert not respx.calls
