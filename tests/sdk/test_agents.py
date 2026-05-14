from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@respx.mock
def test_agents_list_sends_optional_query_params(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents").mock(return_value=httpx.Response(200, json={"agents": []}))

    result = client.agents.list(search="support", team_id="team_123")

    assert result.agents == []
    assert route.calls[0].request.url.params["search"] == "support"
    assert route.calls[0].request.url.params["team_id"] == "team_123"


@respx.mock
def test_agents_create_accepts_kwargs_and_skips_unset_fields(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "name": "Support Agent"}})
    )

    result = client.agents.create(
        name="Support Agent",
        model_name="auto",
        system_prompt="Draft helpful replies.",
        tools=[{"type": "gumcp_server", "server": "gmail"}],
        team_id="team_123",
    )

    assert result.agent.id == "agent_123"
    assert request_json(route.calls[0].request) == {
        "name": "Support Agent",
        "model_name": "auto",
        "system_prompt": "Draft helpful replies.",
        "tools": [{"type": "gumcp_server", "server": "gmail"}],
        "team_id": "team_123",
    }


@respx.mock
def test_agents_create_request_object_can_be_overridden_by_kwargs(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "name": "Draft"}})
    )

    client.agents.create({"name": "Draft", "model_name": "old-model"}, model_name="auto")

    assert request_json(route.calls[0].request) == {"name": "Draft", "model_name": "auto"}


@respx.mock
def test_agents_create_accepts_extra_kwargs(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "name": "Agent"}})
    )

    client.agents.create(name="Agent", model_name="auto", some_future_field="value")

    assert request_json(route.calls[0].request) == {
        "name": "Agent",
        "model_name": "auto",
        "some_future_field": "value",
    }


@respx.mock
def test_agents_retrieve_and_update_routes(client: Gumloop) -> None:
    get_route = respx.get(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "name": "Agent"}})
    )
    patch_route = respx.patch(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "name": "Agent"}})
    )

    retrieved = client.agents.retrieve("agent_123")
    updated = client.agents.update("agent_123", system_prompt="New prompt", is_active=False)

    assert retrieved.agent.id == "agent_123"
    assert updated.agent.id == "agent_123"
    assert get_route.call_count == 1
    assert request_json(patch_route.calls[0].request) == {
        "system_prompt": "New prompt",
        "is_active": False,
    }


@respx.mock
def test_models_list(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": [{"id": "auto"}]}))

    assert client.models.list().model_groups[0]["id"] == "auto"


@respx.mock
def test_async_agents_models_and_user_methods() -> None:
    respx.get(f"{API_BASE}/agents").mock(return_value=httpx.Response(200, json={"agents": []}))
    respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "name": "Support Agent"}})
    )
    respx.get(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "name": "Support Agent"}})
    )
    respx.patch(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "name": "Support Agent"}})
    )
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.agents.list()).agents == []
            assert (await client.agents.create(name="Support Agent", model_name="auto")).agent.id == "agent_123"
            assert (await client.agents.retrieve("agent_123")).agent.id == "agent_123"
            assert (await client.agents.update("agent_123", model_name="auto")).agent.id == "agent_123"
            assert (await client.models.list()).model_groups == []

    asyncio.run(run())
