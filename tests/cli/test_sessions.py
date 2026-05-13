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
def test_sessions_create_posts_to_per_agent_endpoint_with_inline_input(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_abc/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_xyz", "agent_id": "agent_abc"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["sessions", "create", "agent_abc", "--input", "hello there", "--json"],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["input"] == "hello there"


@respx.mock
def test_sessions_create_reads_input_from_stdin(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_abc/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_xyz"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["sessions", "create", "agent_abc", "--input-stdin", "-", "--json"],
        input="piped initial message\n",
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["input"].rstrip() == "piped initial message"


@respx.mock
def test_sessions_create_rejects_both_input_and_input_stdin(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["sessions", "create", "agent_abc", "--input", "x", "--input-stdin", "-", "--json"],
    )

    assert result.exit_code != 0


@respx.mock
def test_sessions_get_calls_per_session_endpoint(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/sessions/session_xyz").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_xyz", "state": "completed"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["sessions", "get", "session_xyz", "--json"])

    assert result.exit_code == 0
    assert '"id": "session_xyz"' in result.output


@respx.mock
def test_sessions_send_posts_to_messages_endpoint(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/sessions/session_xyz/messages").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_xyz"}})
    )
    save_credentials(Credentials(api_key="key"))

    cli_runner.invoke(
        app,
        ["sessions", "send", "session_xyz", "--input", "next turn", "--json"],
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["input"] == "next turn"


@respx.mock
def test_sessions_send_requires_message_text(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["sessions", "send", "session_xyz", "--json"])

    assert result.exit_code != 0


@respx.mock
def test_sessions_cancel_posts_to_cancel_endpoint(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/sessions/session_xyz/cancel").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_xyz", "state": "cancelled"}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["sessions", "cancel", "session_xyz", "--json"])

    assert result.exit_code == 0
    assert route.called
