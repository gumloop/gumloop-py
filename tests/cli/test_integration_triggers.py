from __future__ import annotations

import json

import pytest
import respx

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE
from tests.sdk.test_integration_triggers import CONFIG
from tests.sdk.test_integration_triggers import PAYLOAD


@pytest.mark.parametrize(
    ("args", "method", "suffix", "payload"),
    [
        (["catalog"], "GET", "trigger-operators", {"operators": []}),
        (["get", "trigger"], "GET", "triggers/trigger", {"trigger": PAYLOAD}),
        (
            ["runs", "trigger", "--limit", "2", "--cursor", "cursor", "--state", "COMPLETED", "--state", "FAILED"],
            "GET",
            "triggers/trigger/runs",
            {"items": [], "next_cursor": None},
        ),
        (
            ["stats", "trigger"],
            "GET",
            "triggers/trigger/stats",
            {"run_count": 0, "run_credits": 0.0, "poll_credits": 0.0, "total_credits": 0.0},
        ),
    ],
)
@respx.mock
def test_trigger_inspection_commands_print_typed_json(cli_runner, args, method, suffix, payload):
    save_credentials(Credentials(api_key="key"))
    route = respx.request(method, f"{API_BASE}/agents/agent/{suffix}").respond(200, json=payload)
    result = cli_runner.invoke(app, ["agents", "triggers", args[0], "agent", *args[1:], "--json"])
    assert result.exit_code == 0, result.output
    actual = json.loads(result.output)
    assert all(actual[key] == value for key, value in payload.items())
    assert dict(route.calls[0].request.url.params) == (
        {"page_size": "2", "cursor": "cursor", "state": "COMPLETED,FAILED"} if args[0] == "runs" else {}
    )


@respx.mock
def test_trigger_create_uses_structured_integration_request(cli_runner):
    save_credentials(Credentials(api_key="key"))
    body = {"type": "integration", "prompt": "Mail", "enabled": False, "integration": CONFIG}
    route = respx.post(f"{API_BASE}/agents/agent/triggers").respond(201, json={"trigger": PAYLOAD})
    result = cli_runner.invoke(
        app, ["agents", "triggers", "create", "agent", "--args-json", json.dumps(body), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == body
    assert json.loads(result.output)["trigger"]["type"] == "integration"
