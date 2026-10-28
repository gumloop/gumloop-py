from __future__ import annotations

import asyncio
import json

import pytest
import respx
from pydantic import ValidationError

from gumloop import APIStatusError
from gumloop import AsyncGumloop
from gumloop import Gumloop

STREAM_ORIGIN = "https://staging.ws.gumloop.com"
STREAM_BASE = "https://staging.ws.gumloop.com/api/v1"
STARTED = {
    "voice_session_id": "voice-1",
    "answer_sdp": "v=0\r\nanswer",
    "expires_at": 1900000000,
    "model": "gpt-live-1",
    "voice": "marin",
    "transcript_settle_ms": 1500,
    "user_segment_gap_ms": 700,
    "assistant_segment_gap_ms": 800,
    "idle_timeout_ms": 120000,
}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_voice_uses_explicit_stream_host_and_typed_lifecycle(asynchronous):
    start = respx.post(f"{STREAM_ORIGIN}/gummies/agent%3F1/voice/sessions").respond(201, json=STARTED)
    end = respx.post(f"{STREAM_ORIGIN}/gummies/agent%3F1/voice/sessions/voice%3F1/end").respond(
        202, json={"status": "ending"}
    )

    async def run():
        async with AsyncGumloop(access_token="oauth-token", stream_base_url=STREAM_BASE) as client:
            started = await client.voice.start("agent?1", session_id="chat-1", offer_sdp="v=0\r\noffer", incognito=True)
            ended = await client.voice.end("agent?1", "voice?1")
            return started, ended

    if asynchronous:
        started, ended = asyncio.run(run())
    else:
        with Gumloop(access_token="oauth-token", stream_base_url=STREAM_BASE) as client:
            started = client.voice.start("agent?1", session_id="chat-1", offer_sdp="v=0\r\noffer", incognito=True)
            ended = client.voice.end("agent?1", "voice?1")

    assert started.model_dump() == STARTED
    assert ended.status == "ending"
    assert json.loads(start.calls[0].request.content) == {
        "interaction_id": "chat-1",
        "offer_sdp": "v=0\r\noffer",
        "is_incognito": True,
    }
    assert start.calls[0].request.headers["Authorization"] == "Bearer oauth-token"
    assert end.calls[0].request.url.raw_path == b"/gummies/agent%3F1/voice/sessions/voice%3F1/end"


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("session_id", "offer"),
    [("", "v=0"), ("  ", "v=0"), ("chat", "  "), ("chat", "x" * (1024 * 1024 + 1)), ("chat", "é" * 524289)],
    ids=["empty-session", "blank-session", "blank-offer", "oversize-ascii", "oversize-utf8"],
)
@respx.mock
def test_voice_rejects_invalid_request_before_http(asynchronous, session_id, offer):
    async def run():
        async with AsyncGumloop(access_token="oauth-token") as client:
            return await client.voice.start("agent", session_id=session_id, offer_sdp=offer)

    with pytest.raises(ValidationError):
        if asynchronous:
            asyncio.run(run())
        else:
            with Gumloop(access_token="oauth-token") as client:
                client.voice.start("agent", session_id=session_id, offer_sdp=offer)
    assert not respx.calls


@respx.mock
def test_voice_preserves_disabled_agent_error():
    respx.post(f"{STREAM_ORIGIN}/gummies/agent/voice/sessions").respond(
        403, json={"error": "gummie_voice_disabled_for_agent", "message": "Voice is turned off."}
    )
    with (
        Gumloop(access_token="oauth-token", stream_base_url=STREAM_BASE) as client,
        pytest.raises(APIStatusError) as raised,
    ):
        client.voice.start("agent", session_id="chat", offer_sdp="v=0")
    assert raised.value.code == "gummie_voice_disabled_for_agent"


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_voice_default_incognito_and_configured_origin(asynchronous):
    route = respx.post("https://voice.example.test/gummies/agent/voice/sessions").respond(201, json=STARTED)

    async def run():
        async with AsyncGumloop(access_token="oauth", stream_base_url="https://voice.example.test/custom/v2") as client:
            await client.voice.start("agent", session_id="chat", offer_sdp="v=0\r\n")

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(access_token="oauth", stream_base_url="https://voice.example.test/custom/v2") as client:
            client.voice.start("agent", session_id="chat", offer_sdp="v=0\r\n")
    assert json.loads(route.calls[0].request.content) == {
        "interaction_id": "chat",
        "offer_sdp": "v=0\r\n",
        "is_incognito": False,
    }
    assert "x-auth-key" not in route.calls[0].request.headers


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_voice_keeps_a_path_prefix_mounted_above_api_v1(asynchronous):
    mounted = "http://192.0.2.1/bound/gumloop-ws"
    route = respx.post(f"{mounted}/gummies/agent/voice/sessions").respond(201, json=STARTED)

    async def run():
        async with AsyncGumloop(access_token="oauth", stream_base_url=f"{mounted}/api/v1") as client:
            await client.voice.start("agent", session_id="chat", offer_sdp="v=0\r\n")

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(access_token="oauth", stream_base_url=f"{mounted}/api/v1") as client:
            client.voice.start("agent", session_id="chat", offer_sdp="v=0\r\n")
    assert route.called


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_voice_origin_helper_preserves_chat_base_path(asynchronous):
    chat = respx.post(f"{STREAM_BASE}/chat/completions").respond(
        200,
        json={
            "id": "chat",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [],
            "system_fingerprint": None,
        },
    )

    async def run():
        async with AsyncGumloop(access_token="oauth", stream_base_url=STREAM_BASE) as client:
            await client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hello"}])

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(access_token="oauth", stream_base_url=STREAM_BASE) as client:
            client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hello"}])
    assert chat.called


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("agent_id", ["gumball", "analytics"])
@pytest.mark.parametrize("operation", ["start", "end"])
@respx.mock
def test_voice_delegates_agent_identifier_policy_to_server(asynchronous, agent_id, operation):
    suffix = "" if operation == "start" else "/voice/end"
    route = respx.post(f"{STREAM_ORIGIN}/gummies/{agent_id}/voice/sessions{suffix}").respond(
        404, json={"error": {"message": "Agent not found"}}
    )

    async def run():
        async with AsyncGumloop(access_token="oauth", stream_base_url=STREAM_BASE) as client:
            if operation == "start":
                await client.voice.start(agent_id, session_id="chat", offer_sdp="v=0")
            else:
                await client.voice.end(agent_id, "voice")

    with pytest.raises(APIStatusError):
        if asynchronous:
            asyncio.run(run())
        else:
            with Gumloop(access_token="oauth", stream_base_url=STREAM_BASE) as client:
                if operation == "start":
                    client.voice.start(agent_id, session_id="chat", offer_sdp="v=0")
                else:
                    client.voice.end(agent_id, "voice")
    assert route.call_count == 1


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_voice_preserves_concrete_agent_prefix(asynchronous):
    route = respx.post(f"{STREAM_ORIGIN}/gummies/agent_concrete/voice/sessions").respond(201, json=STARTED)

    async def run():
        async with AsyncGumloop(access_token="oauth", stream_base_url=STREAM_BASE) as client:
            await client.voice.start("agent_concrete", session_id="chat", offer_sdp="v=0")

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(access_token="oauth", stream_base_url=STREAM_BASE) as client:
            client.voice.start("agent_concrete", session_id="chat", offer_sdp="v=0")
    assert route.called
