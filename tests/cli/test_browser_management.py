from __future__ import annotations

import json

import httpx
import pytest
import respx

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

PROFILE = {
    "profile_id": "profile-1",
    "owner_id": "team-1",
    "owner_scope": "team",
    "name": "Work",
    "is_default": False,
    "version": 0,
    "sites": [],
    "size_bytes": 0,
    "has_storage": False,
    "created_by_user_id": None,
    "created_ts": None,
    "updated_ts": None,
    "last_used_ts": None,
}


@pytest.mark.parametrize(
    ("args", "method", "path", "body"),
    [
        (["create", "Work"], "POST", "browser-profiles", {"name": "Work", "team_id": "team-1"}),
        (["get", "profile-1"], "GET", "browser-profiles/profile-1", None),
        (
            ["update", "profile-1", "--name", "Work", "--default"],
            "PATCH",
            "browser-profiles/profile-1",
            {"name": "Work", "is_default": True, "team_id": "team-1"},
        ),
        (["delete", "profile-1"], "DELETE", "browser-profiles/profile-1", None),
        (["remove-site", "profile-1", "example.com"], "DELETE", "browser-profiles/profile-1/sites/example.com", None),
    ],
)
@respx.mock
def test_profile_commands_use_the_scoped_developer_api(cli_runner, args, method, path, body):
    payload = {"status": "success"} if args[0] == "delete" else PROFILE
    route = respx.request(method, f"{API_BASE}/{path}").mock(return_value=httpx.Response(200, json=payload))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["browser", "profiles", *args, "--team", "team-1", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload
    request = route.calls[0].request
    assert (json.loads(request.content) if request.content else None) == body
    assert dict(request.url.params) == ({} if body else {"team_id": "team-1"})


@pytest.mark.parametrize(
    "args",
    [
        ["create", "  "],
        ["update", "profile-1"],
        ["update", "profile-1", "--name", "  "],
        ["remove-site", "profile-1", "  "],
    ],
)
@respx.mock
def test_invalid_profile_arguments_fail_before_http(cli_runner, args):
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["browser", "profiles", *args, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["type"] == "gumloop_error"
    assert list(respx.calls) == []


@respx.mock
def test_session_browser_prints_authenticated_links_as_data(cli_runner):
    payload = {
        "session_id": "session-1",
        "available": False,
        "viewer_url": "https://gumloop.com/agents/agent-1/chat/session-1",
        "handoffs": [
            {
                "action_request_id": "ask-1",
                "title": "Sign in",
                "manage_url": "https://gumloop.com/requests/ask-1/manage",
            }
        ],
    }
    route = respx.get(f"{API_BASE}/sessions/session-1/browser").mock(return_value=httpx.Response(200, json=payload))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["sessions", "browser", "session-1", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["viewer_url"] == "https://gumloop.com/agents/agent-1/chat/session-1"
    assert data["handoffs"][0]["manage_url"] == "https://gumloop.com/requests/ask-1/manage"
    assert route.calls[0].request.method == "GET"
