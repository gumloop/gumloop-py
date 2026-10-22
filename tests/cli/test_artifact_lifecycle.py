from __future__ import annotations

import json

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_artifact_cli_rename_requires_choice_and_sends_null(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["artifacts", "rename", "file", "--json"])
    assert result.exit_code != 0
    route = respx.put(f"{API_BASE}/artifacts/file/name").respond(200, json={"name": None})
    result = cli_runner.invoke(app, ["artifacts", "rename", "file", "--reset", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"name": None}


@pytest.mark.parametrize(
    "command,method,path,response",
    [
        (["get", "file"], "GET", "/download", {"download_url": "https://download.invalid/file"}),
        (["rename", "file", "--name", "Renamed"], "PUT", "/name", {"name": "Renamed"}),
        (["delete", "file"], "DELETE", "", {"deleted": True}),
        (["versions", "file"], "GET", "/versions", {"versions": []}),
    ],
)
@respx.mock
def test_new_artifact_commands_forward_explicit_workspace(cli_runner, command, method, path, response):
    save_credentials(Credentials(access_token="personal"))
    route = respx.route(method=method, url=f"{API_BASE}/artifacts/file{path}").respond(
        204 if response is None else 200, json=response
    )
    result = cli_runner.invoke(app, ["--team-id", "selected", "artifacts", *command, "--json"])
    assert result.exit_code == 0, result.output
    assert route.calls[0].request.url.params["team_id"] == "selected"


@respx.mock
def test_existing_artifact_list_keeps_original_workspace_behavior(cli_runner):
    save_credentials(Credentials(access_token="personal"))
    route = respx.get(f"{API_BASE}/agents/agent_1/artifacts").respond(200, json={"artifacts": []})
    result = cli_runner.invoke(app, ["--team-id", "selected", "artifacts", "list", "agent_1", "--json"])
    assert result.exit_code == 0, result.output
    assert "team_id" not in route.calls[0].request.url.params
