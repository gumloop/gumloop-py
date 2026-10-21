from __future__ import annotations

import json

import pytest
import respx

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.test_voice import STARTED
from tests.sdk.test_voice import STREAM_BASE


@respx.mock
def test_voice_answer_stdout_preserves_protocol_bytes(cli_runner, tmp_path, monkeypatch):
    monkeypatch.setenv("GUMLOOP_STREAM_BASE_URL", STREAM_BASE)
    monkeypatch.setenv("COLUMNS", "40")
    save_credentials(Credentials(api_key="key"))
    source = tmp_path / "offer.sdp"
    source.write_bytes(b"v=0\r\no=synthetic-offer\r\n")
    answer = "v=0\r\na=candidate:" + "x" * 150 + " [not-markup]\r\n"
    respx.post(f"{STREAM_BASE}/agents/agent/voice/sessions").respond(201, json={**STARTED, "answer_sdp": answer})

    result = cli_runner.invoke(app, ["voice", "start", "agent", "--session", "chat", "--offer-sdp-file", str(source)])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == answer.encode("utf-8")
    assert "voice-1" in result.stderr


@pytest.mark.parametrize("from_stdin", [False, True])
@respx.mock
def test_voice_start_reads_sdp_and_prints_answer_metadata(cli_runner, tmp_path, monkeypatch, from_stdin):
    monkeypatch.setenv("GUMLOOP_STREAM_BASE_URL", STREAM_BASE)
    save_credentials(Credentials(api_key="key"))
    offer = "v=0\r\no=synthetic-offer"
    source = tmp_path / "offer.sdp"
    source.write_bytes(offer.encode())
    route = respx.post(f"{STREAM_BASE}/agents/agent/voice/sessions").respond(201, json=STARTED)
    options = ["--offer-sdp-stdin", "-"] if from_stdin else ["--offer-sdp-file", str(source)]

    result = cli_runner.invoke(
        app,
        ["voice", "start", "agent", "--session", "chat", *options, "--incognito", "--json"],
        input=offer if from_stdin else None,
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == STARTED
    assert json.loads(route.calls[0].request.content) == {
        "session_id": "chat",
        "offer_sdp": offer,
        "is_incognito": True,
    }


@pytest.mark.parametrize("kind", ["missing", "both", "bad-marker", "directory", "non-utf8", "blank", "oversize"])
@respx.mock
def test_voice_file_errors_are_structured_and_do_not_call_http(cli_runner, tmp_path, kind):
    save_credentials(Credentials(api_key="key"))
    source = tmp_path / "offer.sdp"
    source.write_bytes(b"v=0")
    if kind == "directory":
        source = tmp_path
    elif kind == "non-utf8":
        source.write_bytes(b"\xff")
    elif kind == "blank":
        source.write_bytes(b" \n")
    elif kind == "oversize":
        source.write_bytes(b"x" * (1024 * 1024 + 1))
    options = ["--offer-sdp-file", str(source)]
    if kind == "missing":
        options = []
    elif kind == "both":
        options += ["--offer-sdp-stdin", "-"]
    elif kind == "bad-marker":
        options = ["--offer-sdp-stdin", "offer"]

    result = cli_runner.invoke(app, ["voice", "start", "agent", "--session", "chat", *options, "--json"])

    assert result.exit_code == 1, result.output
    assert json.loads(result.output)["error"]["type"] == "gumloop_error"
    assert not respx.calls


@respx.mock
def test_voice_end_requests_existing_session_shutdown(cli_runner, monkeypatch):
    monkeypatch.setenv("GUMLOOP_STREAM_BASE_URL", STREAM_BASE)
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{STREAM_BASE}/agents/agent/voice/sessions/voice-1/end").respond(202, json={"status": "ending"})

    result = cli_runner.invoke(app, ["voice", "end", "agent", "voice-1", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"status": "ending"}
    assert route.call_count == 1
