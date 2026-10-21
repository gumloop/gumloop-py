from __future__ import annotations

import json

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@pytest.mark.parametrize(
    "command,method,path,args,body,response",
    [
        ("list", "GET", "", [], None, {"agent_id": "agent_1", "app_rules": []}),
        (
            "create", "POST", "", ["--args", "-"], {"name": "Disposable", "conditions": "true"},
            {"agent_id": "agent_1", "app_rule": {"id": "rule_1", "name": "Disposable"}},
        ),
        (
            "update", "PATCH", "/rule_1", ["rule_1", "--args", "-"], {"status": "disabled"},
            {"agent_id": "agent_1", "app_rule": {"id": "rule_1", "status": "disabled"}},
        ),
        (
            "delete", "DELETE", "/rule_1", ["rule_1"], None,
            {"agent_id": "agent_1", "rule_id": "rule_1", "deleted": True},
        ),
    ],
)
@respx.mock
def test_rule_commands(cli_runner: CliRunner, command: str, method: str, path: str, args: list[str], body: dict | None, response: dict) -> None:
    route = respx.route(method=method, url=f"{API_BASE}/agents/agent_1/app-rules{path}").respond(200, json=response)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["agents", "rules", command, "agent_1", *args, "--json"], input=json.dumps(body) if body else None)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["agent_id"] == "agent_1"
    if body:
        assert request_json(route.calls[0].request) == body
    else:
        assert route.call_count == 1


@respx.mock
def test_rule_empty_update_is_structured_error(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["agents", "rules", "update", "agent_1", "rule_1", "--args-json", "{}", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["code"] == "invalid_request"
    assert respx.calls.call_count == 0
