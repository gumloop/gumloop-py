from __future__ import annotations

# pyright: reportTypedDictNotRequiredAccess=false
import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@respx.mock
def test_agents_list_sends_optional_query_params(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents").mock(return_value=httpx.Response(200, json={"object": "list", "data": []}))

    result = client.agents.list(search="support", limit=25)

    assert result == {"object": "list", "data": []}
    assert route.calls[0].request.url.params["search"] == "support"
    assert route.calls[0].request.url.params["limit"] == "25"


@respx.mock
def test_agents_create_accepts_kwargs_and_skips_unset_fields(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "object": "agent"}})
    )

    result = client.agents.create(
        name="Support Agent",
        model="auto",
        instructions="Draft helpful replies.",
        tools=[{"type": "gumcp_server", "server": "gmail"}],
        team_id="team_123",
    )

    assert result["agent"]["id"] == "agent_123"
    assert request_json(route.calls[0].request) == {
        "name": "Support Agent",
        "model": "auto",
        "instructions": "Draft helpful replies.",
        "tools": [{"type": "gumcp_server", "server": "gmail"}],
        "team_id": "team_123",
    }


@respx.mock
def test_agents_create_request_object_can_be_overridden_by_kwargs(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "object": "agent"}})
    )

    client.agents.create({"name": "Draft", "model": "old-model"}, model="auto")

    assert request_json(route.calls[0].request) == {"name": "Draft", "model": "auto"}


@respx.mock
def test_agents_retrieve_and_update_routes(client: Gumloop) -> None:
    get_route = respx.get(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "object": "agent"}})
    )
    patch_route = respx.patch(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "object": "agent"}})
    )

    retrieved = client.agents.retrieve("agent_123")
    updated = client.agents.update("agent_123", instructions="New instructions", is_active=False)

    assert retrieved["agent"]["id"] == "agent_123"
    assert updated["agent"]["id"] == "agent_123"
    assert get_route.call_count == 1
    assert request_json(patch_route.calls[0].request) == {
        "instructions": "New instructions",
        "is_active": False,
    }


@respx.mock
def test_models_list(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/models").mock(
        return_value=httpx.Response(200, json={"object": "list", "data": [{"id": "auto"}]})
    )

    assert client.models.list()["data"][0]["id"] == "auto"


@respx.mock
def test_async_agents_models_and_user_methods() -> None:
    respx.get(f"{API_BASE}/agents").mock(return_value=httpx.Response(200, json={"object": "list", "data": []}))
    respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "object": "agent"}})
    )
    respx.get(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "object": "agent"}})
    )
    respx.patch(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "object": "agent"}})
    )
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"object": "list", "data": []}))

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert await client.agents.list() == {"object": "list", "data": []}
            assert (await client.agents.create(name="Support Agent", model="auto"))["agent"]["id"] == "agent_123"
            assert (await client.agents.retrieve("agent_123"))["agent"]["id"] == "agent_123"
            assert (await client.agents.update("agent_123", model="auto"))["agent"]["id"] == "agent_123"
            assert await client.models.list() == {"object": "list", "data": []}

    asyncio.run(run())
