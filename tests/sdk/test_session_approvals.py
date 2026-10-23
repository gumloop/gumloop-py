from __future__ import annotations

import asyncio

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.types import SessionApprovalResponseItem
from gumloop.types import SessionApprovalsRequest
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

STREAM_BASE = "https://ws.gumloop.com/api/v1"
ITEM = {"action_request_id": "ask_1", "action": "accept", "response": {"values": {"color": "blue"}}}
RESPONSE = {
    "session": {"id": "session_1", "agent_id": "agent_1"},
    "results": [{"action_request_id": "ask_1", "action": "accept", "outcome": "resolved"}],
    "stream_cursor": "cursor_1",
}


@respx.mock
def test_resolve_approvals_accepts_typed_forms_and_exposes_pending_requests(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/sessions/session_1").respond(
        200,
        json={
            "session": {
                "id": "session_1",
                "agent_id": "agent_1",
                "pending_approvals": [
                    {"action_request_id": "ask_1", "type": "human_input", "questions": [{"name": "color"}]}
                ],
            }
        },
    )
    route = respx.post(f"{API_BASE}/sessions/session_1/approvals").respond(200, json=RESPONSE)
    pending = client.sessions.retrieve("session_1").session.pending_approvals
    assert pending and pending[0].questions == [{"name": "color"}]
    result = client.sessions.resolve_approvals(
        "session_1", SessionApprovalsRequest(approval_responses=[SessionApprovalResponseItem.model_validate(ITEM)])
    )
    assert request_json(route.calls[0].request) == {"approval_responses": [ITEM]}
    assert result.results[0].outcome == "resolved"
    assert result.stream_cursor == "cursor_1"


@respx.mock
def test_async_approval_rejection() -> None:
    route = respx.post(f"{API_BASE}/sessions/session_1/approvals").respond(200, json=RESPONSE)

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            result = await client.sessions.resolve_approvals(
                "session_1",
                approval_responses=[{"action_request_id": "ask_1", "action": "reject", "reason": "Declined"}],
            )
            assert result.session.id == "session_1"

    asyncio.run(run())
    assert request_json(route.calls[0].request) == {
        "approval_responses": [{"action_request_id": "ask_1", "action": "reject", "reason": "Declined"}]
    }


@pytest.mark.parametrize("method", ["send", "stream_message"])
@respx.mock
def test_approval_only_streams_use_stream_host(client: Gumloop, method: str) -> None:
    route = respx.post(f"{STREAM_BASE}/sessions/session_1/messages").respond(
        200, text='data: {"type":"finish","final":true}\n\n', headers={"content-type": "text/event-stream"}
    )
    stream = (
        client.sessions.send("session_1", stream=True, approval_responses=[ITEM])
        if method == "send"
        else client.sessions.stream_message("session_1", approval_responses=[ITEM])
    )
    assert list(stream)[-1].final is True
    assert request_json(route.calls[0].request) == {"stream": True, "approval_responses": [ITEM]}
    with pytest.raises(ValueError, match="input or message is required"):
        client.sessions.send("session_1", approval_responses=[ITEM])


@pytest.mark.parametrize("method", ["send", "stream_message"])
@respx.mock
def test_async_approval_only_streams(method: str) -> None:
    route = respx.post(f"{STREAM_BASE}/sessions/session_1/messages").respond(
        200, text='data: {"type":"finish","final":true}\n\n', headers={"content-type": "text/event-stream"}
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            stream = (
                await client.sessions.send("session_1", stream=True, approval_responses=[ITEM])
                if method == "send"
                else client.sessions.stream_message("session_1", approval_responses=[ITEM])
            )
            assert [event async for event in stream][-1].final is True
            with pytest.raises(ValueError, match="input or message is required"):
                await client.sessions.send("session_1", approval_responses=[ITEM])

    asyncio.run(run())
    assert request_json(route.calls[0].request)["approval_responses"] == [ITEM]


@respx.mock
def test_invalid_approval_request_raises_sdk_error_before_http(client: Gumloop) -> None:
    with pytest.raises(GumloopError, match="SessionApprovalsRequest"):
        client.sessions.resolve_approvals("session_1", {"approval_responses": [{"action": "unknown"}]})
    assert not respx.calls
