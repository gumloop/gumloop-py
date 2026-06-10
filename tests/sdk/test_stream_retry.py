"""Tests for retry logic on streaming endpoints."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import RateLimitError
from gumloop.errors import ServerError
from tests.sdk.helpers import API_BASE

_STREAM_BASE = "https://ws.gumloop.com/api/v1"


def _sse(data: str) -> bytes:
    return f"data: {data}\n\n".encode()


@respx.mock
def test_stream_retries_on_429_then_yields_events(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    session_id = "sess_abc"
    respx.post(f"{_STREAM_BASE}/sessions/{session_id}/stream").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "1"}, json={}),
            httpx.Response(200, content=_sse('{"type": "message"}'), headers={"content-type": "text/event-stream"}),
        ]
    )

    events = list(client._http.stream("POST", f"sessions/{session_id}/stream"))
    assert len(events) == 1
    assert events[0].type == "message"


@respx.mock
def test_stream_retries_on_500_then_yields_events_for_get(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    # Only idempotent methods (GET, DELETE, …) retry on 5xx; POST does not.
    monkeypatch.setattr(time, "sleep", lambda _: None)

    session_id = "sess_abc"
    respx.get(f"{_STREAM_BASE}/sessions/{session_id}/stream").mock(
        side_effect=[
            httpx.Response(500, json={}),
            httpx.Response(200, content=_sse('{"type": "done"}'), headers={"content-type": "text/event-stream"}),
        ]
    )

    events = list(client._http.stream("GET", f"sessions/{session_id}/stream"))
    assert len(events) == 1


@respx.mock
def test_stream_post_does_not_retry_on_500(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    # POST is non-idempotent: a 5xx may arrive after the server already acted,
    # so we raise immediately rather than risk duplicating the side-effect.
    monkeypatch.setattr(time, "sleep", lambda _: None)

    route = respx.post(f"{_STREAM_BASE}/sessions/sess_abc/stream").mock(
        side_effect=[
            httpx.Response(500, json={}),
            httpx.Response(200, content=_sse('{"type": "done"}'), headers={"content-type": "text/event-stream"}),
        ]
    )

    with pytest.raises(ServerError):
        list(client._http.stream("POST", "sessions/sess_abc/stream"))

    assert route.call_count == 1  # raised on first attempt, never retried


@respx.mock
def test_stream_raises_after_max_retries(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    session_id = "sess_abc"
    respx.post(f"{_STREAM_BASE}/sessions/{session_id}/stream").mock(
        return_value=httpx.Response(500, json={})
    )

    with pytest.raises(ServerError):
        list(client._http.stream("POST", f"sessions/{session_id}/stream"))


@respx.mock
def test_stream_does_not_retry_on_404(client: Gumloop) -> None:
    session_id = "sess_missing"
    route = respx.post(f"{_STREAM_BASE}/sessions/{session_id}/stream").mock(
        return_value=httpx.Response(404, json={})
    )

    with pytest.raises(Exception):
        list(client._http.stream("POST", f"sessions/{session_id}/stream"))

    assert route.call_count == 1


@respx.mock
def test_stream_max_retries_zero_raises_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    client = Gumloop(access_token="token", max_retries=0)
    route = respx.post(f"{_STREAM_BASE}/sessions/sess_abc/stream").mock(
        return_value=httpx.Response(429, json={})
    )

    with pytest.raises(RateLimitError):
        list(client._http.stream("POST", "sessions/sess_abc/stream"))

    assert route.call_count == 1


@respx.mock
def test_async_stream_retries_on_429_then_yields_events(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    respx.post(f"{_STREAM_BASE}/sessions/sess_abc/stream").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "0"}, json={}),
            httpx.Response(
                200,
                content=_sse('{"type": "message"}'),
                headers={"content-type": "text/event-stream"},
            ),
        ]
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            events = [e async for e in client._http.stream("POST", "sessions/sess_abc/stream")]
        assert len(events) == 1

    asyncio.run(run())
