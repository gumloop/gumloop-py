from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_team_discovery_forwards_required_auth_scope(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="dummy-team-key", user_id="actor"))

    def authenticate(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team_id") != "team-1":
            return httpx.Response(403, json={"error": "team_id required for team key"})
        return httpx.Response(200, json={"teams": [{"id": "team-1", "name": "Selected team"}]})

    route = respx.get(f"{API_BASE}/teams").mock(side_effect=authenticate)

    result = cli_runner.invoke(app, ["--team-id", "team-1", "teams", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["teams"][0]["id"] == "team-1"
    request = route.calls[0].request
    assert request.url.params["team_id"] == "team-1"
    assert request.headers["Authorization"] == "Bearer dummy-team-key"
    assert request.headers["x-auth-key"] == "actor"


@pytest.mark.parametrize("oauth", [False, True])
@respx.mock
def test_unselected_team_discovery_keeps_personal_and_oauth_requests_unscoped(
    cli_runner: CliRunner, oauth: bool
) -> None:
    credentials = (
        Credentials(access_token="dummy-oauth") if oauth else Credentials(api_key="dummy-personal-key", user_id="actor")
    )
    save_credentials(credentials)
    route = respx.get(f"{API_BASE}/teams").respond(200, json={"teams": []})

    result = cli_runner.invoke(app, ["teams", "list", "--json"])

    assert result.exit_code == 0, result.output
    request = route.calls[0].request
    assert not request.url.params
    assert request.headers["Authorization"] == f"Bearer {'dummy-oauth' if oauth else 'dummy-personal-key'}"
    assert request.headers.get("x-auth-key") == (None if oauth else "actor")


@respx.mock
def test_organization_discovery_does_not_retry_or_broaden_team_key_auth(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="dummy-team-key", user_id="actor"))
    route = respx.get(f"{API_BASE}/organizations").respond(
        403, json={"error": {"code": "unauthorized", "message": "Personal API key or OAuth required"}}
    )

    result = cli_runner.invoke(app, ["--team-id", "team-1", "organizations", "list", "--json"])

    assert result.exit_code != 0
    assert "Personal API key or OAuth required" in result.output
    assert route.call_count == 1
    assert not route.calls[0].request.url.params
