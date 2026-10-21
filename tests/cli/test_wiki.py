from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_wiki_query_filters_and_json(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{API_BASE}/wiki/query").mock(return_value=httpx.Response(200, json={"cards": []}))
    result = cli_runner.invoke(app, ["wiki", "query", "--type", "project", "--entity-key", "launch", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"type": "project", "entity_key": "launch"}
    assert json.loads(result.output) == {"cards": []}


@respx.mock
def test_wiki_human_output(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.post(f"{API_BASE}/wiki/query").mock(return_value=httpx.Response(200, json={"cards": [
        {"type": "profile", "summary": "Prefers short replies", "facts": []}
    ]}))
    result = cli_runner.invoke(app, ["wiki", "query"])
    assert result.exit_code == 0, result.output
    assert "Prefers short replies" in result.output


def test_wiki_key_requires_type(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["wiki", "query", "--entity-key", "launch"])
    assert result.exit_code != 0
    assert "Pass --type" in result.output
