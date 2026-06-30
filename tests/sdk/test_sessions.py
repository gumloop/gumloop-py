from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

STREAM_BASE = "https://ws.gumloop.com/api/v1"


@respx.mock
def test_sessions_create_without_input_returns_session(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_123", "agent_id": "agent_123"}})
    )

    result = client.sessions.create("agent_123", session_id="session_123", metadata={"source": "test"})

    assert result.session.id == "session_123"
    assert request_json(route.calls[0].request) == {
        "session_id": "session_123",
        "metadata": {"source": "test"},
    }


@respx.mock
def test_sessions_create_with_input(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(
            200, json={"session": {"id": "session_123", "agent_id": "agent_123"}, "queue_position": 1}
        )
    )

    result = client.sessions.create("agent_123", input="Hello")

    assert result.session.id == "session_123"
    assert result.queue_position == 1
    assert request_json(route.calls[0].request) == {"input": "Hello"}


@respx.mock
def test_sessions_create_request_object_can_be_overridden_by_kwargs(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_123", "agent_id": "agent_123"}})
    )

    # When both ``request`` and kwargs supply fields, kwargs win on overlap;
    # non-overlapping fields from both are sent through as-is. Backend
    # decides which of ``input`` / ``message`` to honor.
    client.sessions.create("agent_123", {"input": "Old"}, message="New")

    assert request_json(route.calls[0].request) == {"input": "Old", "message": "New"}


@respx.mock
def test_sessions_retrieve_send_and_cancel_routes(client: Gumloop) -> None:
    retrieve_route = respx.get(f"{API_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_123", "agent_id": "agent_123"}})
    )
    send_route = respx.post(f"{API_BASE}/sessions/session_123/messages").mock(
        return_value=httpx.Response(
            200, json={"session": {"id": "session_123", "agent_id": "agent_123"}, "queue_position": 0}
        )
    )
    cancel_route = respx.post(f"{API_BASE}/sessions/session_123/cancel").mock(
        return_value=httpx.Response(
            200, json={"session": {"id": "session_123", "agent_id": "agent_123", "state": "cancelled"}}
        )
    )

    assert client.sessions.retrieve("session_123").session.id == "session_123"
    assert client.sessions.send("session_123", message="Continue").session.id == "session_123"
    assert client.sessions.cancel("session_123").session.id == "session_123"
    assert retrieve_route.call_count == 1
    assert request_json(send_route.calls[0].request) == {"message": "Continue"}
    assert request_json(cancel_route.calls[0].request) == {}


@respx.mock
def test_sessions_list_forwards_filters_and_returns_envelope(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(
            200,
            json={
                "sessions": [
                    {"id": "session_123", "agent_id": "agent_123", "name": "Run", "type": "api", "state": "completed"}
                ],
                "next_cursor": "next",
            },
        )
    )

    result = client.sessions.list(
        "agent_123",
        search="invoice",
        state="completed",
        type="api",
        sort_order="oldest",
        page_size=10,
        cursor="prev",
    )

    assert [s.id for s in result.sessions] == ["session_123"]
    assert result.sessions[0].type == "api"
    assert result.next_cursor == "next"
    params = route.calls[0].request.url.params
    assert params["search"] == "invoice"
    assert params["state"] == "completed"
    assert params["type"] == "api"
    assert params["sort_order"] == "oldest"
    assert params["page_size"] == "10"
    assert params["cursor"] == "prev"
    assert "creator_user_id" not in params
    assert "trigger_id" not in params


def test_sessions_send_requires_input_or_message() -> None:
    client = Gumloop(access_token="token")

    with pytest.raises(ValueError, match="required"):
        client.sessions.send("session_123")


@respx.mock
def test_sessions_create_with_stream_true_uses_stream_host(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(
            200,
            text='event: message\ndata: {"type": "message", "stream_cursor": "sid:1"}\n\n'
            'event: finish\ndata: {"type": "finish", "final": true}\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )

    events = [e.model_dump(exclude_unset=True) for e in client.sessions.create("agent_123", input="Hello", stream=True)]

    assert events == [
        {"type": "message", "stream_cursor": "sid:1"},
        {"type": "finish", "final": True},
    ]
    assert request_json(route.calls[0].request) == {"input": "Hello", "stream": True}


@respx.mock
def test_sessions_send_with_stream_true_uses_stream_host(client: Gumloop) -> None:
    route = respx.post(f"{STREAM_BASE}/sessions/session_123/messages").mock(
        return_value=httpx.Response(
            200,
            text='event: finish\ndata: {"type": "finish", "final": true}\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )

    events = [
        e.model_dump(exclude_unset=True) for e in client.sessions.send("session_123", input="Continue", stream=True)
    ]

    assert events == [{"type": "finish", "final": True}]
    assert request_json(route.calls[0].request) == {"input": "Continue", "stream": True}


@respx.mock
def test_sessions_resume_stream_uses_last_cursor(client: Gumloop) -> None:
    route = respx.get(f"{STREAM_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(
            200,
            text='event: finish\ndata: {"type": "finish", "finishReason": "not_resumable", "final": true}\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )

    events = list(client.sessions.resume_stream("session_123", "sid:1"))

    assert len(events) == 1
    assert events[0].type == "finish"
    assert events[0].finish_reason == "not_resumable"
    assert events[0].final is True
    assert route.calls[0].request.url.params["stream"] == "true"
    assert route.calls[0].request.url.params["last_cursor"] == "sid:1"


@respx.mock
def test_async_sessions_methods() -> None:
    respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_123", "agent_id": "agent_123"}})
    )
    respx.get(f"{API_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_123", "agent_id": "agent_123"}})
    )
    respx.post(f"{API_BASE}/sessions/session_123/messages").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_123", "agent_id": "agent_123"}})
    )
    respx.post(f"{API_BASE}/sessions/session_123/cancel").mock(
        return_value=httpx.Response(
            200, json={"session": {"id": "session_123", "agent_id": "agent_123", "state": "cancelled"}}
        )
    )
    respx.get(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(200, json={"sessions": [{"id": "session_123", "agent_id": "agent_123"}]})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.sessions.create("agent_123")).session.id == "session_123"
            assert (await client.sessions.retrieve("session_123")).session.id == "session_123"
            assert (await client.sessions.send("session_123", input="Hello")).session.id == "session_123"
            assert (await client.sessions.cancel("session_123")).session.id == "session_123"
            listed = await client.sessions.list("agent_123", state="completed")
            assert [s.id for s in listed.sessions] == ["session_123"]

    asyncio.run(run())


@respx.mock
def test_async_sessions_stream_methods() -> None:
    create_route = respx.post(f"{STREAM_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(
            200,
            text='event: message\ndata: {"type": "message", "stream_cursor": "sid:1"}\n\n'
            'event: finish\ndata: {"type": "finish", "final": true}\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            stream = await client.sessions.create("agent_123", input="Hello", stream=True)
            events = [event.model_dump(exclude_unset=True) async for event in stream]

        assert events == [
            {"type": "message", "stream_cursor": "sid:1"},
            {"type": "finish", "final": True},
        ]
        assert request_json(create_route.calls[0].request) == {"input": "Hello", "stream": True}

    asyncio.run(run())
