from __future__ import annotations

import json

import pytest
import respx

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

SOURCE = {"id": "source", "name": "Docs", "source_type": "mcp", "status": "draft", "scope": "personal"}


@respx.mock
def test_brain_connect_uses_structured_stdin_without_implicit_approval(cli_runner):
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{API_BASE}/brain/sources").respond(201, json={"source": SOURCE})
    request = {"name": "Docs", "source_type": "mcp", "config": {"setup_session_id": "ready-session"}}
    result = cli_runner.invoke(app, ["brain", "sources", "connect", "--args", "-", "--json"], input=json.dumps(request))
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == request


@pytest.mark.parametrize(
    "input_json",
    ["{}", '{"name":"Docs","source_type":"direct_file_uploads"}', '{"name":"Docs","source_type":"mcp","config":[]}'],
)
@respx.mock
def test_brain_connect_invalid_input_exits_before_request(cli_runner, input_json):
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["brain", "sources", "connect", "--args-json", input_json, "--json"])
    assert result.exit_code != 0
    assert not respx.calls


@pytest.mark.parametrize(("command", "body"), [("pause", {"status": "paused"}), ("resume", {"status": "active"})])
@respx.mock
def test_brain_status_commands_preserve_explicit_action(cli_runner, command, body):
    save_credentials(Credentials(api_key="key"))
    route = respx.patch(f"{API_BASE}/brain/sources/source/status").respond(200, json={"source": SOURCE})
    result = cli_runner.invoke(app, ["brain", "sources", command, "source", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == body


@respx.mock
def test_brain_configure_preserves_false_and_reports_api_denial(cli_runner):
    save_credentials(Credentials(api_key="key"))
    route = respx.patch(f"{API_BASE}/brain/sources/source").respond(
        403, json={"error": {"code": "insufficient_permissions", "message": "Denied"}}
    )
    result = cli_runner.invoke(
        app,
        ["brain", "sources", "configure", "source", "--args-json", '{"respect_source_permissions":false}', "--json"],
    )
    assert result.exit_code != 0
    assert json.loads(route.calls[0].request.content) == {"respect_source_permissions": False}
