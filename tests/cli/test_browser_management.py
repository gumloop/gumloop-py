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
    (
        ["update", "profile-1", "--name", "Work", "--default"],
        "PATCH",
        "browser-profiles/profile-1",
        {"name": "Work", "is_default": True},
    ),
    (["delete", "profile-1"], "DELETE", "browser-profiles/profile-1", None),
]


@pytest.mark.parametrize(("args", "method", "path", "body"), OPERATIONS)
@respx.mock
@pytest.mark.parametrize("team_source", ["unset", "explicit", "environment"])
def test_personal_profile_commands(cli_runner, args, method, path, body, team_source, monkeypatch):
    if team_source == "environment":
        monkeypatch.setenv("GUMLOOP_TEAM_ID", "team")
    options = ["--team-id", "team"] if team_source == "explicit" else []
    payload = {"status": "success"} if args[0] == "delete" else PROFILE
    route = respx.request(method, f"{API_BASE}/{path}").respond(200, json=payload)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, [*options, "browser", "profiles", *args, "--json"])
    assert result.exit_code == 0, result.output
    actual = json.loads(result.output)
    assert all(actual[key] == value for key, value in payload.items())
    assert not route.calls[0].request.url.params
    assert (json.loads(route.calls[0].request.content) if route.calls[0].request.content else None) == body


@pytest.mark.parametrize("args", [["create", "  "], ["update", "profile-1"], ["update", "profile-1", "--name", "  "]])
@respx.mock
def test_invalid_profile_arguments_fail_before_http(cli_runner, args):
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["browser", "profiles", *args, "--json"])
    assert result.exit_code == 1
    assert not respx.calls
