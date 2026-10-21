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
from tests.sdk.test_session_approvals import ITEM
from tests.sdk.test_session_approvals import RESPONSE


@pytest.mark.parametrize("source", ["inline", "file", "stdin"])
@respx.mock
def test_approvals_json_sources(cli_runner: CliRunner, tmp_path: Path, source: str) -> None:
    route = respx.post(f"{API_BASE}/sessions/session_1/approvals").respond(200, json=RESPONSE)
    save_credentials(Credentials(api_key="key"))
    body = json.dumps({"approval_responses": [ITEM]})
    path = tmp_path / "responses.json"
    path.write_text(body)
    args = {"inline": ["--args-json", body], "file": ["--args-file", str(path)], "stdin": ["--args", "-"]}[source]
    result = cli_runner.invoke(app, ["sessions", "approvals", "session_1", *args, "--json"], input=body)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["results"] == RESPONSE["results"]
    assert json.loads(route.calls[0].request.content) == {"approval_responses": [ITEM]}


@pytest.mark.parametrize(
    "body",
    ["{}", '{"approval_responses":[]}', '{"approval_responses":[{"action_request_id":"ask_1","action":"allow"}]}'],
)
@respx.mock
def test_approvals_invalid_shape_is_json_error(cli_runner: CliRunner, body: str) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "approvals", "session_1", "--args-json", body, "--json"])
    assert result.exit_code == 1
    assert "error" in json.loads(result.output)
    assert "Traceback" not in result.output
    assert not respx.calls
