from __future__ import annotations

import json

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE
from tests.sdk.test_session_queue import MESSAGE


@pytest.mark.parametrize(
    "command,method,path,extra,payload",
    [
        ("list", "GET", "", [], {"queue": [MESSAGE]}),
        ("add", "POST", "", ["--input", "Next turn"], {"queued_message": MESSAGE, "queue": [MESSAGE]}),
        (
            "edit",
            "PATCH",
            "/queued_1",
            ["queued_1", "--input-stdin", "-"],
            {"queued_message": MESSAGE, "queue": [MESSAGE]},
        ),
        ("delete", "DELETE", "/queued_1", ["queued_1"], {"queue": []}),
        ("send", "POST", "/queued_1/send", ["queued_1"], {"session": {"id": "session_1", "agent_id": "agent_1"}}),
    ],
)
@respx.mock
def test_queue_commands(
    cli_runner: CliRunner, command: str, method: str, path: str, extra: list[str], payload: dict
) -> None:
    route = respx.route(method=method, url=f"{API_BASE}/sessions/session_1/queue{path}").respond(200, json=payload)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "queue", command, "session_1", *extra, "--json"], input="Next turn")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    if command == "send":
        assert data["session"]["id"] == "session_1"
    else:
        assert [message["id"] for message in data["queue"]] == [message["id"] for message in payload["queue"]]
        if command in ("add", "edit"):
            assert {key: data["queued_message"][key] for key in MESSAGE} == MESSAGE
    if command in ("add", "edit"):
        assert json.loads(route.calls[0].request.content) == {"input": "Next turn"}


@pytest.mark.parametrize(
    "extra", [[], ["--input", " "], ["--input", "x", "--input-stdin", "-"], ["--input-stdin", "file.txt"]]
)
@respx.mock
def test_queue_add_rejects_invalid_input_before_network(cli_runner: CliRunner, extra: list[str]) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "queue", "add", "session_1", *extra, "--json"])
    assert result.exit_code == 1
    assert "error" in json.loads(result.output)
    assert not respx.calls
