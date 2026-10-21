from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.context import CliContext
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

STREAM_BASE = "https://ws.gumloop.com/api/v1"
EVENTS = [
    {"type": "interaction-ready", "interaction_id": "session_1", "stream_cursor": "session_1:1"},
    {"type": "text-delta", "delta": "[hello]"},
    {"type": "finish", "finishReason": "stop", "final": True},
]


def sse(events: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        text="".join(f"data: {json.dumps(event)}\n\n" for event in events),
        headers={"content-type": "text/event-stream"},
    )


@pytest.mark.parametrize("options", [[], ["--input", ""], ["--input-stdin", "-"]])
@respx.mock
def test_empty_stream_creation_fails_before_request(cli_runner: CliRunner, options: list[str]) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "create", "agent_1", *options, "--stream", "--json"], input="")
    assert result.exit_code == 1
    assert "with text to start a stream" in json.loads(result.stderr)["error"]["message"]
    assert not respx.calls


@respx.mock
def test_empty_ordinary_creation_remains_supported(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_1/sessions").respond(
        201, json={"session": {"id": "session_1", "agent_id": "agent_1"}}
    )
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "create", "agent_1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {}


@pytest.mark.parametrize(
    "command,path", [("create", "agents/agent_1/sessions"), ("send", "sessions/session_1/messages")]
)
@respx.mock
def test_session_stream_commands_emit_ndjson(cli_runner: CliRunner, command: str, path: str) -> None:
    route = respx.post(f"{STREAM_BASE}/{path}").mock(return_value=sse(EVENTS))
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app,
        [
            "sessions",
            command,
            "agent_1" if command == "create" else "session_1",
            "--input",
            "Hello",
            "--stream",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[0]["stream_cursor"] == "session_1:1"
    assert events[1]["delta"] == "[hello]"
    assert events[-1]["final"] is True
    assert json.loads(route.calls[0].request.content) == {"input": "Hello", "stream": True}


@respx.mock
def test_session_resume_uses_cursor_and_prints_literal_text(cli_runner: CliRunner) -> None:
    route = respx.get(f"{STREAM_BASE}/sessions/session_1").mock(return_value=sse(EVENTS))
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "resume", "session_1", "--cursor", "session_1:0"])
    assert result.exit_code == 0, result.output
    assert "[hello]" in result.output and "session_1:1" in result.output
    assert dict(route.calls[0].request.url.params) == {"stream": "true", "last_cursor": "session_1:0"}


@respx.mock
def test_session_stream_refreshes_before_first_event(cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    route = respx.post(f"{STREAM_BASE}/agents/agent_1/sessions").mock(
        side_effect=[httpx.Response(401, json={"error": {"message": "Expired"}}), sse(EVENTS)]
    )
    save_credentials(Credentials(access_token="expired", refresh_token="refresh"))

    def refresh(context: CliContext) -> bool:
        context.credentials.access_token = "fresh"
        return True

    monkeypatch.setattr(CliContext, "refresh_if_possible", refresh)
    result = cli_runner.invoke(app, ["sessions", "create", "agent_1", "--input", "Hello", "--stream", "--json"])
    assert result.exit_code == 0, result.output
    assert [call.request.headers["authorization"] for call in route.calls] == ["Bearer expired", "Bearer fresh"]


@respx.mock
def test_session_stream_error_preserves_event_and_exits_nonzero(cli_runner: CliRunner) -> None:
    respx.post(f"{STREAM_BASE}/sessions/session_1/messages").mock(
        return_value=sse([EVENTS[0], {"type": "error", "error": {"message": "Run failed"}}])
    )
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["sessions", "send", "session_1", "--input", "Hello", "--stream", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout.splitlines()[-1])["error"] == {"message": "Run failed"}
    assert "Run failed" in json.loads(result.stderr)["error"]["message"]
    assert json.loads(result.stderr)["error"]["message"] == "Run failed"


@pytest.mark.parametrize("json_output", [False, True])
@respx.mock
def test_session_resume_not_resumable_fails(cli_runner: CliRunner, json_output: bool) -> None:
    event = {"type": "finish", "finishReason": "not_resumable", "final": True}
    respx.get(f"{STREAM_BASE}/sessions/session_1").mock(return_value=sse([event]))
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app, ["sessions", "resume", "session_1", "--cursor", "old:0", *(["--json"] if json_output else [])]
    )
    assert result.exit_code == 1
    assert "cannot be resumed" in result.stderr
    if json_output:
        assert json.loads(result.stdout) == {"type": "finish", "finish_reason": "not_resumable", "final": True}


@pytest.mark.parametrize(
    "command,method,path,options",
    [
        ("create", "POST", "agents/agent_1/sessions", ["--input", "Hello", "--stream"]),
        ("send", "POST", "sessions/session_1/messages", ["--input", "Hello", "--stream"]),
        ("resume", "GET", "sessions/session_1", ["--cursor", "session_1:0"]),
    ],
)
@respx.mock
def test_session_streams_preserve_unscoped_transport(cli_runner: CliRunner, command, method, path, options) -> None:
    route = respx.route(method=method, url=f"{STREAM_BASE}/{path}").mock(return_value=sse(EVENTS))
    save_credentials(Credentials(access_token="personal"))
    result = cli_runner.invoke(
        app,
        [
            "--team-id",
            "team_1",
            "sessions",
            command,
            "agent_1" if command == "create" else "session_1",
            *options,
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "team_id" not in route.calls[0].request.url.params


@pytest.mark.parametrize("stream", [False, True])
@respx.mock
def test_session_create_metadata(cli_runner: CliRunner, stream: bool) -> None:
    url = f"{STREAM_BASE if stream else API_BASE}/agents/agent_1/sessions"
    response = (
        sse(EVENTS) if stream else httpx.Response(201, json={"session": {"id": "session_1", "agent_id": "agent_1"}})
    )
    route = respx.post(url).mock(return_value=response)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app,
        [
            "sessions",
            "create",
            "agent_1",
            "--input",
            "Hello",
            "--metadata-json",
            '{"source":"cli"}',
            *(["--stream"] if stream else []),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["metadata"] == {"source": "cli"}


@respx.mock
def test_session_stream_send_attaches_uploaded_file(cli_runner: CliRunner, tmp_path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hello")
    respx.post(f"{API_BASE}/sessions/session_1/files").respond(201, json={"file_name": "input/note.txt", "size": 5})
    route = respx.post(f"{STREAM_BASE}/sessions/session_1/messages").mock(return_value=sse(EVENTS))
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app, ["sessions", "send", "session_1", "--input", "Read", "--file", str(path), "--stream", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["attachments"][0]["file_name"] == "input/note.txt"
