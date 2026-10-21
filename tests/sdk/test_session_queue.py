from __future__ import annotations

import asyncio

import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

MESSAGE = {"id": "queued_1", "input": "Next turn", "state": "queued", "position": 0}


@respx.mock
def test_queue_lifecycle_parses_order_and_routes(client: Gumloop) -> None:
    url = f"{API_BASE}/sessions/session_1/queue"
    add = respx.post(url).respond(201, json={"queued_message": MESSAGE, "queue": [MESSAGE]})
    respx.get(url).respond(200, json={"queue": [MESSAGE]})
    edit = respx.patch(f"{url}/queued_1").respond(
        200, json={"queued_message": {**MESSAGE, "input": "Edited"}, "queue": [{**MESSAGE, "input": "Edited"}]}
    )
    respx.delete(f"{url}/queued_1").respond(200, json={"queue": []})
    send = respx.post(f"{url}/queued_1/send").respond(
        200, json={"session": {"id": "session_1", "agent_id": "agent_1", "state": "queued"}}
    )

    assert client.sessions.queue_message("session_1", "Next turn").queued_message.id == "queued_1"
    assert client.sessions.list_queue("session_1").queue[0].position == 0
    assert client.sessions.edit_queued_message("session_1", "queued_1", "Edited").queued_message.input == "Edited"
    assert client.sessions.delete_queued_message("session_1", "queued_1").queue == []
    assert client.sessions.send_queued_message("session_1", "queued_1").session.state == "queued"
    assert request_json(add.calls[0].request) == {"input": "Next turn"}
    assert request_json(edit.calls[0].request) == {"input": "Edited"}
    assert request_json(send.calls[0].request) == {}


@respx.mock
def test_async_queue_lifecycle() -> None:
    url = f"{API_BASE}/sessions/session_1/queue"
    respx.post(url).respond(201, json={"queued_message": MESSAGE, "queue": [MESSAGE]})
    respx.get(url).respond(200, json={"queue": [MESSAGE]})
    edit = respx.patch(f"{url}/queued_1").respond(200, json={"queued_message": MESSAGE, "queue": [MESSAGE]})
    respx.delete(f"{url}/queued_1").respond(200, json={"queue": []})
    respx.post(f"{url}/queued_1/send").respond(200, json={"session": {"id": "session_1", "agent_id": "agent_1"}})

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.sessions.queue_message("session_1", "Next turn")).queued_message.id == "queued_1"
            assert (await client.sessions.list_queue("session_1")).queue[0].input == "Next turn"
            assert (
                await client.sessions.edit_queued_message("session_1", "queued_1", "Next turn")
            ).queued_message.state == "queued"
            assert (await client.sessions.delete_queued_message("session_1", "queued_1")).queue == []
            assert (await client.sessions.send_queued_message("session_1", "queued_1")).session.id == "session_1"

    asyncio.run(run())
    assert request_json(edit.calls[0].request) == {"input": "Next turn"}


@respx.mock
def test_queue_server_conflict_is_preserved(client: Gumloop) -> None:
    import pytest

    from gumloop import APIStatusError

    respx.post(f"{API_BASE}/sessions/session_1/queue/queued_1/send").respond(
        409, json={"error": {"code": "queued_message_not_eligible", "message": "Already sent."}}
    )
    with pytest.raises(APIStatusError) as caught:
        client.sessions.send_queued_message("session_1", "queued_1")
    assert caught.value.status_code == 409
