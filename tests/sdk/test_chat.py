from __future__ import annotations

import asyncio
import json

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.spec import ChatRequest
from gumloop.spec import ChatStreamChunk
from gumloop.spec import ChatUsage
from tests.sdk.helpers import request_json

STREAM_BASE = "https://ws.gumloop.com/api/v1"


# ---------------------------------------------------------------------------
# Non-streaming
# ---------------------------------------------------------------------------


@respx.mock
def test_chat_create_returns_typed_result(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "moonshotai/kimi-k2.6",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Paris"},
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            },
        )
    )

    result = client.chat.completions.create(
        model="moonshotai/kimi-k2.6",
        messages=[{"role": "user", "content": "capital of France?"}],
    )

    assert result.id == "chatcmpl-1"
    assert result.choices[0].message.content == "Paris"
    body = request_json(route.calls[0].request)
    assert body["model"] == "moonshotai/kimi-k2.6"
    assert body["messages"] == [{"role": "user", "content": "capital of France?"}]
    assert "stream" not in body  # exclude_unset hides defaults


@respx.mock
def test_chat_accepts_chatrequest_instance(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "moonshotai/kimi-k2.6",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
            },
        )
    )

    req = ChatRequest(
        model="moonshotai/kimi-k2.6",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
    )
    client.chat.completions.create(req)

    body = request_json(route.calls[0].request)
    assert body["model"] == "moonshotai/kimi-k2.6"
    assert body["temperature"] == 0.2


@respx.mock
def test_chat_kwargs_override_request_body(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": "moonshotai/kimi-k2.6",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
            },
        )
    )

    client.chat.completions.create(
        {"model": "moonshotai/kimi-k2.6", "messages": [{"role": "user", "content": "old"}]},
        temperature=0.9,
    )

    body = request_json(route.calls[0].request)
    assert body["temperature"] == 0.9


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _sse(payloads: list[dict | str]) -> str:
    return "".join(
        f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in payloads
    )


@respx.mock
def test_chat_stream_yields_typed_chunks(client: Gumloop) -> None:
    chunks = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": "Hi"}, "finish_reason": None}
            ],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": "!"}, "finish_reason": None}],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "total_tokens": 7,
                "cost": 0.0001,
                "is_byok": False,
            },
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

    received = list(
        client.chat.completions.create(
            model="m",
            messages=[{"role": "user", "content": "x"}],
            stream=True,
        )
    )

    assert len(received) == 3
    assert all(isinstance(c, ChatStreamChunk) for c in received)
    assert received[0].choices[0].delta.content == "Hi"
    assert received[1].choices[0].delta.content == "!"

    # Extended ChatUsage carries cost/is_byok (Speakeasy 0.9.1 drops them).
    final_usage = received[2].usage
    assert final_usage is not None
    assert isinstance(final_usage, ChatUsage)
    assert final_usage.cost == 0.0001
    assert final_usage.is_byok is False
    assert final_usage.total_tokens == 7


@respx.mock
def test_chat_stream_skips_done_sentinel(client: Gumloop) -> None:
    respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=_sse([{
                "id": "c1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": None}],
            }, "[DONE]"]),
            headers={"content-type": "text/event-stream"},
        )
    )

    received = list(
        client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}], stream=True)
    )

    assert len(received) == 1


@respx.mock
def test_chat_stream_error_chunk_surfaces_via_chunk_error(client: Gumloop) -> None:
    # OR-shape mid-stream error: full ChatStreamChunk envelope with top-level
    # `error` field. Without the envelope shape, the SDK's stream_typed
    # ValidationError catch would silently drop the chunk.
    error_chunk = {
        "id": "chunk-error-deadbeef",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
        "error": {"code": 402, "message": "budget exceeded"},
    }
    respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text=_sse([error_chunk, "[DONE]"]),
            headers={"content-type": "text/event-stream"},
        )
    )

    received = list(
        client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}], stream=True)
    )

    assert len(received) == 1
    chunk = received[0]
    assert chunk.error is not None
    assert chunk.error.code == 402
    assert chunk.error.message == "budget exceeded"
    assert chunk.choices[0].finish_reason == "error"


@respx.mock
def test_structured_output_serializes_as_json_schema(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"answer":"42"}'},
                    }
                ],
            },
        )
    )

    client.chat.completions.create(
        model="m",
        messages=[{"role": "user", "content": "x"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "ans",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            },
        },
    )

    body = request_json(route.calls[0].request)
    rf = body["response_format"]
    assert rf["type"] == "json_schema"
    # Wire uses `schema`, not Speakeasy's Python-side `schema_`.
    assert "schema" in rf["json_schema"]
    assert rf["json_schema"]["name"] == "ans"


@respx.mock
def test_image_generation_request_shape(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": "google/gemini-3.1-flash-image-preview",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
            },
        )
    )

    client.chat.completions.create(
        model="google/gemini-3.1-flash-image-preview",
        messages=[{"role": "user", "content": "logo"}],
        modalities=["image", "text"],
        image_config={"aspect_ratio": "1:1", "image_size": "2K"},
    )

    body = request_json(route.calls[0].request)
    assert body["modalities"] == ["image", "text"]
    assert body["image_config"] == {"aspect_ratio": "1:1", "image_size": "2K"}


@respx.mock
def test_provider_preferences_passthrough(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
            },
        )
    )

    client.chat.completions.create(
        model="m",
        messages=[{"role": "user", "content": "x"}],
        provider={"sort": "latency", "order": ["fireworks", "together"]},
    )

    body = request_json(route.calls[0].request)
    assert body["provider"]["sort"] == "latency"
    assert body["provider"]["order"] == ["fireworks", "together"]


@respx.mock
def test_chat_stream_carries_image_delta_chunks(client: Gumloop) -> None:
    """delta.images must round-trip through pydantic validation — without the
    SDK extension, Speakeasy's parent ChatStreamDelta drops the field silently."""
    chunks = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-image-1.5",
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "images": [{"image_url": {"url": "data:image/png;base64,YWJj"}}],
                },
                "finish_reason": None,
            }],
        },
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-image-1.5",
            "choices": [{
                "index": 0,
                "delta": {
                    "images": [{"image_url": {"url": "data:image/png;base64,ZGVm"}}],
                },
                "finish_reason": "stop",
            }],
        },
        "[DONE]",
    ]
    respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(200, text=_sse(chunks), headers={"content-type": "text/event-stream"})
    )

    received = list(
        client.chat.completions.create(
            model="gpt-image-1.5",
            messages=[{"role": "user", "content": "draw"}],
            stream=True,
            modalities=["image", "text"],
        )
    )

    assert len(received) == 2
    assert all(isinstance(c, ChatStreamChunk) for c in received)
    first_images = received[0].choices[0].delta.images
    assert first_images and first_images[0].image_url.url == "data:image/png;base64,YWJj"
    final = received[1].choices[0]
    assert final.delta.images and final.delta.images[0].image_url.url == "data:image/png;base64,ZGVm"
    assert final.finish_reason == "stop"


@respx.mock
def test_async_chat_create(async_client: AsyncGumloop) -> None:
    respx.post(f"{STREAM_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "system_fingerprint": "fp",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "hi"},
                    }
                ],
            },
        )
    )

    async def run() -> None:
        result = await async_client.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "x"}]
        )
        assert result.choices[0].message.content == "hi"

    asyncio.run(run())
