from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_agents_list_passes_search_and_pagination(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(200, json={"agents": [], "next_cursor": None})
    )
    save_credentials(Credentials(api_key="key"))

    cli_runner.invoke(app, ["agents", "list", "--search", "support", "--limit", "25", "--json"])

    params = route.calls[0].request.url.params
    assert params["search"] == "support"
    assert params["page_size"] == "25"


@respx.mock
def test_agents_get_calls_per_agent_endpoint(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/agents/agent_abc").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_abc", "name": "Bot"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "get", "agent_abc", "--json"])

    assert result.exit_code == 0
    assert '"id": "agent_abc"' in result.output


@respx.mock
def test_agents_versions_lists_versions_with_pagination(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_abc/versions").mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {
                        "id": "version_2",
                        "agent_id": "agent_abc",
                        "major_version": 2,
                        "name": "Support Bot",
                        "is_deployed": True,
                    }
                ],
                "next_cursor": "cursor_2",
            },
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "versions", "agent_abc", "--limit", "25", "--cursor", "cursor_1"])

    assert result.exit_code == 0, result.output
    assert "version_2" in result.output
    assert "Support Bot" in result.output
    assert "cursor_2" in result.output
    assert route.calls[0].request.url.params["page_size"] == "25"
    assert route.calls[0].request.url.params["cursor"] == "cursor_1"


@respx.mock
def test_agents_export_writes_version_response_as_json(cli_runner: CliRunner, tmp_path: Path) -> None:
    respx.get(f"{API_BASE}/agents/agent_abc/versions/version_2").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": {
                    "id": "version_2",
                    "agent_id": "agent_abc",
                    "major_version": 2,
                    "name": "Support Bot",
                    "composition": {
                        "complete": True,
                        "name": "Support Bot",
                        "model_name": "auto",
                        "system_prompt": "Be helpful.",
                    },
                },
                "changes": None,
            },
        )
    )
    save_credentials(Credentials(api_key="key"))
    output_path = tmp_path / "agent-version.json"

    result = cli_runner.invoke(
        app,
        ["agents", "export", "agent_abc", "version_2", "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["version"]["id"] == "version_2"
    assert payload["version"]["composition"]["system_prompt"] == "Be helpful."


@respx.mock
def test_agents_create_posts_required_fields(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_new", "name": "Bot"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["agents", "create", "--name", "Bot", "--model", "auto", "--description", "test", "--json"],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["name"] == "Bot"
    assert sent["model_name"] == "auto"
    assert sent["description"] == "test"


@respx.mock
def test_agents_create_reads_system_prompt_from_file(cli_runner: CliRunner, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("# system prompt body\n\nbe nice")
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_new", "name": "Bot"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["agents", "create", "--name", "Bot", "--model", "auto", "--system-prompt-file", str(prompt_file), "--json"],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["system_prompt"] == "# system prompt body\n\nbe nice"


@respx.mock
def test_agents_create_parses_tools_json_into_request_body(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_new", "name": "Bot"}})
    )
    save_credentials(Credentials(api_key="key"))

    tools = '[{"type": "gumcp_server", "server": "gmail"}]'
    cli_runner.invoke(
        app,
        ["agents", "create", "--name", "Bot", "--model", "auto", "--tools-json", tools, "--json"],
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["tools"] == [{"type": "gumcp_server", "server": "gmail"}]


@respx.mock
def test_agents_create_rejects_invalid_tools_json(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["agents", "create", "--name", "Bot", "--model", "auto", "--tools-json", "{not array}", "--json"],
    )

    assert result.exit_code != 0


@respx.mock
def test_agents_update_only_sends_specified_fields(cli_runner: CliRunner) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_abc").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_abc", "name": "Bot"}})
    )
    save_credentials(Credentials(api_key="key"))

    cli_runner.invoke(
        app,
        ["agents", "update", "agent_abc", "--name", "Renamed", "--inactive", "--json"],
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent == {"name": "Renamed", "is_active": False}


@respx.mock
def test_agents_attach_skills_command(cli_runner: CliRunner) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_abc/skills").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_abc", "attached": ["s1", "s2"]})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "attach-skills", "agent_abc", "s1", "s2"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"attach": ["s1", "s2"]}


@respx.mock
def test_agents_detach_skills_command(cli_runner: CliRunner) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_abc/skills").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_abc", "detached": ["s1"]})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "detach-skills", "agent_abc", "s1"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"detach": ["s1"]}


@respx.mock
def test_agents_attach_mcp_server_command(cli_runner: CliRunner) -> None:
    route = respx.put(f"{API_BASE}/agents/agent_abc/mcp-servers/gmail").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_abc", "created": True, "auth_status": "connected"})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "attach-mcp-server", "agent_abc", "gmail", "--approval-mode", "off"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"approval_mode": "off"}
    assert "connected" in result.output


@respx.mock
def test_agents_detach_mcp_server_command(cli_runner: CliRunner) -> None:
    route = respx.delete(f"{API_BASE}/agents/agent_abc/mcp-servers/gmail").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_abc", "server_id": "gmail", "detached": True})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "detach-mcp-server", "agent_abc", "gmail"])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "true" in result.output


@respx.mock
def test_agents_update_rejects_skill_ids_option(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["agents", "update", "agent_abc", "--skill-ids", "s1"])

    assert result.exit_code != 0


@respx.mock
def test_agents_create_uses_effective_team_id(cli_runner: CliRunner, monkeypatch) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_new", "name": "Bot"}})
    )
    save_credentials(Credentials(api_key="key"))
    monkeypatch.setenv("GUMLOOP_TEAM_ID", "team_env")

    cli_runner.invoke(
        app,
        ["agents", "create", "--name", "Bot", "--model", "auto", "--json"],
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["team_id"] == "team_env"
