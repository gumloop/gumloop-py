from __future__ import annotations

# pyright: reportGeneralTypeIssues=false, reportTypedDictNotRequiredAccess=false, reportArgumentType=false
import asyncio

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@respx.mock
def test_sessions_create_without_input_returns_session(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_123", "object": "session"}})
    )

    result = client.sessions.create("agent_123", session_id="session_123", metadata={"source": "test"})

    assert result["session"]["id"] == "session_123"
    assert request_json(route.calls[0].request) == {
        "session_id": "session_123",
        "metadata": {"source": "test"},
    }


@respx.mock
def test_sessions_create_with_input_can_return_response(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(200, json={"response": {"id": "session_123", "object": "response"}})
    )

    result = client.sessions.create("agent_123", input="Hello")

    assert result["response"]["id"] == "session_123"
    assert request_json(route.calls[0].request) == {"input": "Hello"}


@respx.mock
def test_sessions_create_request_object_can_be_overridden_by_kwargs(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_123", "object": "session"}})
    )

    client.sessions.create("agent_123", {"input": "Old"}, message="New")

    assert request_json(route.calls[0].request) == {"input": "Old", "message": "New"}


@respx.mock
def test_sessions_retrieve_send_and_cancel_routes(client: Gumloop) -> None:
    retrieve_route = respx.get(f"{API_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_123", "object": "session"}})
    )
    send_route = respx.post(f"{API_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(200, json={"response": {"id": "session_123", "object": "response"}})
    )
    cancel_route = respx.post(f"{API_BASE}/sessions/session_123/cancel").mock(
        return_value=httpx.Response(200, json={"response": {"id": "session_123", "object": "response"}})
    )

    assert client.sessions.retrieve("session_123")["session"]["id"] == "session_123"
    assert client.sessions.send("session_123", message="Continue")["response"]["id"] == "session_123"
    assert client.sessions.cancel("session_123")["response"]["id"] == "session_123"
    assert retrieve_route.call_count == 1
    assert request_json(send_route.calls[0].request) == {"message": "Continue"}
    assert request_json(cancel_route.calls[0].request) == {}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input": "Hello", "message": "Continue"},
        {},
    ],
)
def test_sessions_reject_ambiguous_or_empty_message(kwargs: dict) -> None:
    client = Gumloop(access_token="token")

    with pytest.raises(ValueError):
        client.sessions.send("session_123", **kwargs)


def test_sessions_do_not_expose_stream_methods(client: Gumloop) -> None:
    assert not hasattr(client.sessions, "stream")
    assert not hasattr(client, "stream_session")


@respx.mock
def test_async_sessions_methods() -> None:
    respx.post(f"{API_BASE}/agents/agent_123/sessions").mock(
        return_value=httpx.Response(201, json={"session": {"id": "session_123", "object": "session"}})
    )
    respx.get(f"{API_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(200, json={"session": {"id": "session_123", "object": "session"}})
    )
    respx.post(f"{API_BASE}/sessions/session_123").mock(
        return_value=httpx.Response(200, json={"response": {"id": "session_123", "object": "response"}})
    )
    respx.post(f"{API_BASE}/sessions/session_123/cancel").mock(
        return_value=httpx.Response(200, json={"response": {"id": "session_123", "object": "response"}})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.sessions.create("agent_123"))["session"]["id"] == "session_123"
            assert (await client.sessions.retrieve("session_123"))["session"]["id"] == "session_123"
            assert (await client.sessions.send("session_123", input="Hello"))["response"]["id"] == "session_123"
            assert (await client.sessions.cancel("session_123"))["response"]["id"] == "session_123"

    asyncio.run(run())
