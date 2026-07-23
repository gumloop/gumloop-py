from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop import Gumloop
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app

# Both unary and stream chat completions go to the WS host (the SDK's
# ``post_to_stream_host`` covers unary; ``stream_typed`` covers streaming).
STREAM_BASE = "https://ws.gumloop.com/api/v1"


def _sse(payloads: list[dict | str]) -> str:
    return "".join(f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in payloads)


_UNARY_RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "claude-sonnet-4-5",
    "system_fingerprint": "fp",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "Paris"},
        }
    ],
}


@respx.mock
def test_create_no_stream_outputs_message_content(cli_runner: CliRunner) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "capital of France?", "-m", "claude-sonnet-4-5", "--no-stream"],
    )

    assert result.exit_code == 0, result.output
    assert "Paris" in result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "claude-sonnet-4-5"
    assert sent["messages"] == [{"role": "user", "content": "capital of France?"}]
    assert "stream" not in sent  # SDK omits default-False stream via exclude_unset


@respx.mock
def test_create_json_implies_no_stream_and_outputs_json(cli_runner: CliRunner) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "hi", "-m", "claude-sonnet-4-5", "--json"],
    )

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["choices"][0]["message"]["content"] == "Paris"
    sent = json.loads(route.calls[0].request.content)
    assert "stream" not in sent


@respx.mock
def test_create_stdin_message_routes_to_request_body(cli_runner: CliRunner) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "-m", "claude-sonnet-4-5", "--message-stdin", "-", "--json"],
        input="hi from stdin\n",
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    # stdin preserves the trailing newline; assert content not content.rstrip(),
    # since the SDK doesn't mutate the message.
    assert sent["messages"][-1]["content"] == "hi from stdin\n"


@respx.mock
def test_create_system_messages_repeatable_and_ordered(cli_runner: CliRunner) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "go",
            "-m",
            "claude-sonnet-4-5",
            "--system",
            "you are A",
            "--system",
            "you are B",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["messages"] == [
        {"role": "system", "content": "you are A"},
        {"role": "system", "content": "you are B"},
        {"role": "user", "content": "go"},
    ]


@respx.mock
def test_create_rejects_both_prompt_and_message_stdin(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "x",
            "-m",
            "claude-sonnet-4-5",
            "--message-stdin",
            "-",
            "--json",
        ],
        input="y\n",
    )

    assert result.exit_code != 0


@respx.mock
def test_create_surfaces_provider_400(cli_runner: CliRunner) -> None:
    respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": "model_image_unsupported",
                    "message": "Model 'claude-sonnet-4-5' does not support image generation.",
                    "type": "invalid_request_error",
                    "param": "modalities",
                    "details": {},
                }
            },
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "hi", "-m", "claude-sonnet-4-5", "--no-stream", "--json"],
    )

    assert result.exit_code == 1
    # --json sends the error envelope to stderr via print_json_error.
    parsed = json.loads(result.stderr or result.output)
    assert parsed["error"]["status_code"] == 400
    assert parsed["error"]["code"] == "model_image_unsupported"


@respx.mock
def test_create_streaming_outputs_concatenated_deltas(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default streaming is gated on ``_stdout_is_tty()``; CliRunner pipes
    # stdout into a buffer so the real isatty() returns False. Force True via
    # the wrapper so the streaming branch fires.
    monkeypatch.setattr("gumloop.cli.commands.chat._stdout_is_tty", lambda: True)

    chunks = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"}, "finish_reason": None}],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": " there"}, "finish_reason": None}],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        "[DONE]",
    ]
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=_sse(chunks),
            headers={"content-type": "text/event-stream"},
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "say hi", "-m", "m"],
    )

    assert result.exit_code == 0, result.output
    assert "Hi there" in result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent.get("stream") is True


# ---------------------------------------------------------------------------
# Feature tests for the new flags (stream-force, conflict, modality, schema, ndjson).
# ---------------------------------------------------------------------------


@respx.mock
def test_create_stream_flag_forces_streaming_when_piped(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pretend stdout is *not* a TTY so the default would be unary; --stream must override.
    monkeypatch.setattr("gumloop.cli.commands.chat._stdout_is_tty", lambda: False)
    chunks: list[dict | str] = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hi"}, "finish_reason": None}],
        },
        "[DONE]",
    ]
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=_sse(chunks),
            headers={"content-type": "text/event-stream"},
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "say hi", "-m", "m", "--stream"],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent.get("stream") is True
    assert "hi" in result.output


def test_create_stream_and_no_stream_conflict(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "x", "-m", "m", "--stream", "--no-stream"],
    )

    assert result.exit_code == 1
    combined = (result.output or "") + (result.stderr or "")
    assert "--stream" in combined and "--no-stream" in combined


@respx.mock
def test_create_modality_lands_in_request_body_as_modalities(cli_runner: CliRunner) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "x",
            "-m",
            "m",
            "--modality",
            "image",
            "--modality",
            "text",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["modalities"] == ["image", "text"]


@respx.mock
def test_create_schema_file_lands_in_response_format(
    cli_runner: CliRunner,
    tmp_path,
) -> None:
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    schema_path = tmp_path / "person.json"
    schema_path.write_text(json.dumps(schema))
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "x",
            "-m",
            "m",
            "--schema-file",
            str(schema_path),
            "--schema-name",
            "Person",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    rf = sent["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "Person"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] == schema


@respx.mock
def test_create_stream_json_emits_ndjson(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("gumloop.cli.commands.chat._stdout_is_tty", lambda: False)
    chunks: list[dict | str] = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"}, "finish_reason": None}],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": " there"}, "finish_reason": None}],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        "[DONE]",
    ]
    respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=_sse(chunks),
            headers={"content-type": "text/event-stream"},
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "say hi", "-m", "m", "--stream", "--json"],
    )

    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    # Each line is a full ChatStreamChunk JSON document with at minimum id/choices.
    assert all("choices" in obj and "id" in obj for obj in parsed)
    # Concatenated content reconstructs to the streamed text.
    text = "".join(
        (choice.get("delta", {}) or {}).get("content", "") or "" for obj in parsed for choice in obj["choices"]
    )
    assert text == "Hi there"


# ---------------------------------------------------------------------------
# Parity invariants — guardrails against CLI <-> SDK drift.
# ---------------------------------------------------------------------------


@respx.mock
def test_max_tokens_alias_sends_same_wire_field_as_max_completion_tokens(
    cli_runner: CliRunner,
) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    a = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "x", "-m", "m", "--no-stream", "--max-tokens", "512"],
    )
    b = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "x", "-m", "m", "--no-stream", "--max-completion-tokens", "512"],
    )

    assert a.exit_code == 0, a.output
    assert b.exit_code == 0, b.output
    assert len(route.calls) == 2
    body_a = json.loads(route.calls[0].request.content)
    body_b = json.loads(route.calls[1].request.content)
    assert body_a["max_completion_tokens"] == 512
    assert body_b["max_completion_tokens"] == 512
    assert "max_tokens" not in body_a
    assert "max_tokens" not in body_b
    assert body_a == body_b


def test_max_tokens_and_max_completion_tokens_conflict(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        [
            "chat",
            "completions",
            "create",
            "x",
            "-m",
            "m",
            "--no-stream",
            "--max-tokens",
            "256",
            "--max-completion-tokens",
            "256",
        ],
    )

    assert result.exit_code == 1
    combined = (result.output or "") + (result.stderr or "")
    assert "--max-tokens" in combined and "--max-completion-tokens" in combined


# Registry of CLI subcommand paths <-> SDK resource paths. Future commands
# must be added here; the test below proves both halves resolve.
PARITY_MAPPINGS: list[tuple[list[str], str]] = [
    (["chat", "completions", "create"], "chat.completions.create"),
]


@pytest.mark.parametrize(("cli_path", "sdk_path"), PARITY_MAPPINGS)
def test_cli_command_paths_mirror_sdk_resource_paths(
    cli_runner: CliRunner,
    cli_path: list[str],
    sdk_path: str,
) -> None:
    # (a) CLI path resolves: --help exits 0.
    result = cli_runner.invoke(app, [*cli_path, "--help"])
    assert result.exit_code == 0, f"CLI path {cli_path} did not resolve:\n{result.output}"

    # (b) SDK path resolves to a callable on the real client.
    client = Gumloop(api_key="x")
    target: Any = client
    for segment in sdk_path.split("."):
        target = getattr(target, segment)
    assert callable(target), f"SDK path {sdk_path} does not end in a callable: {type(target)}"


@respx.mock
def test_stream_flag_overrides_tty_detection(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TTY=True would normally stream; --no-stream must override and produce unary.
    monkeypatch.setattr("gumloop.cli.commands.chat._stdout_is_tty", lambda: True)
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "x", "-m", "m", "--no-stream"],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert "stream" not in sent or sent["stream"] is False


@respx.mock
def test_modality_flag_wire_name_matches_sdk_kwarg(cli_runner: CliRunner) -> None:
    # The kwarg name on the SDK is ``modalities`` (plural). The CLI flag is
    # ``--modality`` (singular, repeatable) for ergonomics, but the wire MUST
    # carry the plural so the SDK accepts it.
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(return_value=httpx.Response(200, json=_UNARY_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["chat", "completions", "create", "x", "-m", "m", "--modality", "text", "--json"],
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert "modalities" in sent
    assert "modality" not in sent
    assert sent["modalities"] == ["text"]
