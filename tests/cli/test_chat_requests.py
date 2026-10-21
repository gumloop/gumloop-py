from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.cli.test_chat import _UNARY_RESPONSE
from tests.cli.test_chat import STREAM_BASE
from tests.cli.test_chat import _sse

REQUEST = {
    "model": "test-model",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What color?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
            ],
        },
        {"role": "assistant", "content": "Blue"},
        {"role": "user", "content": "Make it red"},
    ],
    "image_config": {"aspect_ratio": "1:1", "image_size": "1K"},
    "provider": {"sort": "latency"},
    "reasoning": {"effort": "low"},
    "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object", "properties": {}}}}],
}


@pytest.mark.parametrize("source", ["inline", "file", "stdin"])
@respx.mock
def test_chat_structured_requests_preserve_sdk_fields(cli_runner: CliRunner, tmp_path: Path, source: str) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").respond(200, json=_UNARY_RESPONSE)
    save_credentials(Credentials(api_key="key"))
    raw = json.dumps(REQUEST)
    path = tmp_path / "request.json"
    path.write_text(raw)
    options = {"inline": ["--args-json", raw], "file": ["--args-file", str(path)], "stdin": ["--args", "-"]}[source]
    result = cli_runner.invoke(app, ["chat", "completions", "create", *options, "--json"], input=raw)
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == REQUEST
    assert json.loads(result.output)["choices"][0]["message"]["content"] == "Paris"


@respx.mock
def test_chat_explicit_flags_override_request(cli_runner: CliRunner) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").respond(200, json=_UNARY_RESPONSE)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "--args-json",
            json.dumps({**REQUEST, "stream": True, "temperature": 0.7}),
            "--model",
            "override",
            "--temperature",
            "0.1",
            "--no-stream",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "override" and sent["temperature"] == 0.1
    assert "stream" not in sent


@respx.mock
def test_chat_json_request_stream_emits_ndjson(cli_runner: CliRunner) -> None:
    payload = {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": "stop"}],
    }
    respx.post(f"{STREAM_BASE}/chat/completions").respond(
        200, text=_sse([payload, "[DONE]"]), headers={"content-type": "text/event-stream"}
    )
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app, ["chat", "completions", "create", "--args-json", json.dumps({**REQUEST, "stream": True}), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["choices"][0]["delta"]["content"] == "Hello"


@pytest.mark.parametrize("extra", [["prompt"], ["--message-stdin", "-"], ["--system", "system"]])
@respx.mock
def test_chat_rejects_mixed_message_sources(cli_runner: CliRunner, extra: list[str]) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app, ["chat", "completions", "create", *extra, "--args-json", json.dumps(REQUEST), "--json"]
    )
    assert result.exit_code == 1
    assert "not both" in json.loads(result.output)["error"]["message"]
    assert not respx.calls


@pytest.mark.parametrize("streamed", [False, True])
@respx.mock
def test_chat_human_image_output_notice(cli_runner: CliRunner, streamed: bool) -> None:
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}
    if streamed:
        payload = {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"images": [image]}, "finish_reason": "stop"}],
        }
        response = httpx.Response(200, text=_sse([payload, "[DONE]"]), headers={"content-type": "text/event-stream"})
    else:
        response = httpx.Response(
            200,
            json={
                **_UNARY_RESPONSE,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": None, "images": [image]},
                    }
                ],
            },
        )
    respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=response)
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "--args-json",
            json.dumps(REQUEST),
            "--stream" if streamed else "--no-stream",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Generated image available" in result.output
    assert "--json" in result.output
    assert "aGVsbG8=" not in result.output
