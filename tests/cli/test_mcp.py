from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_mcp_list_emits_raw_sdk_response_with_json_flag(cli_runner: CliRunner) -> None:
    payload = {
        "servers": [
            {
                "server_id": "gmail",
                "name": "Gmail",
                "type": "gumcp",
                "status": "connected",
                "tool_count": 4,
                "gumloop_auth_url": "",
            }
        ]
    }
    respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json=payload))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["mcp", "list", "--json"])

    assert result.exit_code == 0
    assert '"server_id": "gmail"' in result.output


@respx.mock
def test_mcp_list_forwards_root_team_id_flag_to_sdk_request(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    save_credentials(Credentials(api_key="key"))

    cli_runner.invoke(app, ["--team-id", "team_xyz", "mcp", "list", "--json"])

    assert route.calls[0].request.url.params["team_id"] == "team_xyz"


@respx.mock
def test_mcp_list_exits_nonzero_on_api_error(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/mcp/servers").mock(
        return_value=httpx.Response(403, json={"error": {"message": "forbidden", "type": "auth"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["mcp", "list", "--json"])

    assert result.exit_code == 1


@respx.mock
def test_mcp_get_calls_per_server_endpoint(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/mcp/servers/gmail").mock(
        return_value=httpx.Response(200, json={"server": {"server_id": "gmail", "name": "Gmail"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["mcp", "get", "gmail", "--json"])

    assert result.exit_code == 0
    assert '"server_id": "gmail"' in result.output


@respx.mock
def test_mcp_tools_lists_tools_for_server(cli_runner: CliRunner) -> None:
    payload = {"server_id": "gmail", "status": "connected", "tools": [{"name": "read_emails", "tool_call_id": "t1"}]}
    respx.get(f"{API_BASE}/mcp/servers/gmail/tools").mock(return_value=httpx.Response(200, json=payload))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["mcp", "tools", "gmail", "--json"])

    assert result.exit_code == 0
    assert '"name": "read_emails"' in result.output


@respx.mock
def test_mcp_tools_shows_auth_url_when_server_is_not_connected(cli_runner: CliRunner) -> None:
    payload = {
        "server_id": "gmail",
        "status": "unauthenticated",
        "gumloop_auth_url": "http://localhost:3000/settings/profile/apps?server=gmail",
        "tools": [],
    }
    respx.get(f"{API_BASE}/mcp/servers/gmail/tools").mock(return_value=httpx.Response(200, json=payload))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["mcp", "tools", "gmail"])

    assert result.exit_code == 0
    assert "not connected" in result.output
    assert "http://localhost:3000/settings/profile/apps?server=gmail" in result.output


@respx.mock
def test_mcp_call_posts_args_from_inline_json(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["mcp", "call", "gmail", "read_emails", "--args-json", '{"max_results": 5}', "--json"],
    )

    assert result.exit_code == 0
    sent = route.calls[0].request.content
    assert b'"max_results": 5' in sent or b'"max_results":5' in sent
    assert b'"tool_name": "read_emails"' in sent or b'"tool_name":"read_emails"' in sent


@respx.mock
def test_mcp_call_reads_args_from_stdin_when_dash_passed(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["mcp", "call", "gmail", "read_emails", "--args", "-", "--json"],
        input='{"max_results": 9}\n',
    )

    assert result.exit_code == 0, result.output
    sent = route.calls[0].request.content
    assert b'"max_results": 9' in sent or b'"max_results":9' in sent


@respx.mock
def test_mcp_call_rejects_multiple_args_input_modes(cli_runner: CliRunner, tmp_path) -> None:
    save_credentials(Credentials(api_key="key"))
    args_file = tmp_path / "a.json"
    args_file.write_text("{}")

    result = cli_runner.invoke(
        app,
        [
            "mcp",
            "call",
            "gmail",
            "read_emails",
            "--args-json",
            "{}",
            "--args-file",
            str(args_file),
            "--json",
        ],
    )

    assert result.exit_code == 1
