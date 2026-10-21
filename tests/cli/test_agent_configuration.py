from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

AGENT = {"id": "agent_1", "name": "Configured agent"}
TRIGGER = {"id": "trigger_1", "agent_id": "agent_1", "type": "webhook", "enabled": False}


@pytest.mark.parametrize(
    "command,method,path,options,response,body",
    [
        (["delete"], "DELETE", "", [], {"agent_id": "agent_1", "deleted": True}, None),
        (
            ["set-abilities"],
            "PATCH",
            "/abilities",
            ["--args-json", '{"ask_question":{"enabled":false}}'],
            {"agent_id": "agent_1", "abilities": {"ask_question": {"enabled": False}}},
            {"ask_question": {"enabled": False}},
        ),
        (["app-rules"], "GET", "/app-rules", [], {"agent_id": "agent_1", "app_rules": []}, None),
        (
            ["knowledge-sources", "list"],
            "GET",
            "/knowledge-sources",
            [],
            {"agent_id": "agent_1", "knowledge_sources": []},
            None,
        ),
        (
            ["knowledge-sources", "attach"],
            "PUT",
            "/knowledge-sources/source_1",
            ["source_1"],
            {"agent_id": "agent_1", "knowledge_source": {"connector_id": "source_1"}, "outcome": "attached"},
            {"config": None},
        ),
        (
            ["knowledge-sources", "detach"],
            "DELETE",
            "/knowledge-sources/source_1",
            ["source_1"],
            {"agent_id": "agent_1", "connector_id": "source_1", "detached": True},
            None,
        ),
        (
            ["subagents", "attach"],
            "PUT",
            "/subagents/sub_1",
            ["sub_1"],
            {"agent_id": "agent_1", "subagent_ids": ["sub_1"], "changed": True},
            None,
        ),
        (
            ["subagents", "detach"],
            "DELETE",
            "/subagents/sub_1",
            ["sub_1"],
            {"agent_id": "agent_1", "subagent_ids": [], "changed": True},
            None,
        ),
        (["triggers", "list"], "GET", "/triggers", [], {"agent_id": "agent_1", "triggers": [TRIGGER]}, None),
        (
            ["triggers", "create"],
            "POST",
            "/triggers",
            ["--args-json", '{"type":"webhook","prompt":"Hello","enabled":false}'],
            {"trigger": TRIGGER},
            {"type": "webhook", "prompt": "Hello", "enabled": False},
        ),
        (
            ["triggers", "update"],
            "PATCH",
            "/triggers/trigger_1",
            ["trigger_1", "--args-json", '{"enabled":false}'],
            {"trigger": TRIGGER},
            {"enabled": False},
        ),
        (
            ["triggers", "delete"],
            "DELETE",
            "/triggers/trigger_1",
            ["trigger_1"],
            {"agent_id": "agent_1", "trigger_id": "trigger_1", "deleted": True},
            None,
        ),
        (
            ["triggers", "webhook-url"],
            "GET",
            "/triggers/trigger_1/webhook-url",
            ["trigger_1"],
            {"agent_id": "agent_1", "trigger_id": "trigger_1", "webhook_url": "https://example.test/secret"},
            None,
        ),
        (["eval-config"], "GET", "/evaluation-config", [], {"config": {"agent_id": "agent_1", "enabled": False}}, None),
        (
            ["set-eval-config"],
            "PATCH",
            "/evaluation-config",
            ["--args-json", '{"enabled":false}'],
            {"config": {"agent_id": "agent_1", "enabled": False}},
            {"enabled": False},
        ),
        (["eval-results"], "GET", "/evaluations", [], {"evaluations": []}, None),
        (
            ["eval-result"],
            "GET",
            "/evaluations/eval_1",
            ["eval_1"],
            {
                "evaluation": {
                    "id": "eval_1",
                    "evaluation_id": "eval_1",
                    "session_id": "session_1",
                    "agent_id": "agent_1",
                }
            },
            None,
        ),
    ],
)
@respx.mock
def test_agent_configuration_commands(
    cli_runner: CliRunner,
    command: list[str],
    method: str,
    path: str,
    options: list[str],
    response: dict,
    body: dict | None,
) -> None:
    route = respx.route(method=method, url=f"{API_BASE}/agents/agent_1{path}").respond(200, json=response)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["agents", *command, "agent_1", *options, "--json"])
    assert result.exit_code == 0, result.output
    assert set(response).issubset(json.loads(result.output))
    assert route.called
    if body is not None:
        assert json.loads(route.calls[0].request.content) == body


@pytest.mark.parametrize(
    "operation,method,path,payload",
    [
        ("create", "POST", "agents", {"name": "From JSON", "metadata": {"voice": {"enabled": False}, "max_steps": 5}}),
        (
            "update",
            "PATCH",
            "agents/agent_1",
            {"name": "From JSON", "metadata": {"voice": {"enabled": False}, "max_steps": 5}},
        ),
        (
            "attach-mcp-server",
            "PUT",
            "agents/agent_1/mcp-servers/gmail",
            {
                "credential_mode": "end_user",
                "restricted_tools": ["send_email"],
                "tool_approval_modes": {"send_email": "all"},
            },
        ),
    ],
)
@respx.mock
def test_agent_full_requests_from_file(
    cli_runner: CliRunner, tmp_path: Path, operation: str, method: str, path: str, payload: dict
) -> None:
    response = (
        {"agent": AGENT}
        if operation != "attach-mcp-server"
        else {"agent_id": "agent_1", "server_id": "gmail", "created": True}
    )
    route = respx.route(method=method, url=f"{API_BASE}/{path}").respond(200, json=response)
    save_credentials(Credentials(api_key="key"))
    request = tmp_path / "agent.json"
    request.write_text(json.dumps(payload))
    positional = [] if operation == "create" else ["agent_1"]
    if operation == "attach-mcp-server":
        positional.append("gmail")
    result = cli_runner.invoke(app, ["agents", operation, *positional, "--args-file", str(request), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == payload


@respx.mock
def test_agent_update_flags_override_json_and_keep_other_settings(cli_runner: CliRunner) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_1").respond(200, json={"agent": AGENT})
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app,
        ["agents", "update", "agent_1", "--args", "-", "--name", "Override", "--json"],
        input='{"name":"Old","metadata":{"max_steps":5},"version":4}',
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "name": "Override",
        "metadata": {"max_steps": 5},
        "version": 4,
    }


@respx.mock
def test_agent_evaluation_filters(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_1/evaluations").respond(200, json={"evaluations": []})
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app,
        [
            "agents",
            "eval-results",
            "agent_1",
            "--grade",
            "pass",
            "--created-after",
            "2026-10-01T00:00:00",
            "--session-id",
            "session_1",
            "--limit",
            "5",
            "--cursor",
            "next",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert dict(route.calls[0].request.url.params) == {
        "grade": "pass",
        "created_after": "2026-10-01T00:00:00",
        "session_id": "session_1",
        "page_size": "5",
        "cursor": "next",
    }


@respx.mock
def test_trigger_invalid_request_is_structured_error(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["agents", "triggers", "create", "agent_1", "--args-json", "{}", "--json"])
    assert result.exit_code == 1
    assert "error" in json.loads(result.output)
    assert not respx.calls
