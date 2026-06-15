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
def test_agents_get_evaluation_config(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/agents/agent_123/evaluation-config").mock(
        return_value=httpx.Response(200, json={"config": {"agent_id": "agent_123", "enabled": False}})
    )

    result = client.agents.get_evaluation_config("agent_123")

    assert result.config.agent_id == "agent_123"
    assert result.config.enabled is False


@respx.mock
def test_agents_update_evaluation_config_patches_only_sent_fields(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123/evaluation-config").mock(
        return_value=httpx.Response(200, json={"config": {"agent_id": "agent_123", "enabled": True}})
    )

    result = client.agents.update_evaluation_config("agent_123", enabled=True)

    assert result.config.enabled is True
    # PATCH merge: only the field we set goes on the wire — omitted fields aren't
    # cleared client-side (the backend preserves them).
    assert request_json(route.calls[0].request) == {"enabled": True}


@respx.mock
def test_agents_list_evaluations_sends_filters(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_123/evaluations").mock(
        return_value=httpx.Response(
            200,
            json={
                "evaluations": [{"evaluation_id": "eval_1", "interaction_id": "i1", "agent_id": "agent_123"}],
                "next_cursor": "cursor_2",
            },
        )
    )

    result = client.agents.list_evaluations("agent_123", grade="needs_review", page_size=10, cursor="cursor_1")

    assert result.evaluations[0].evaluation_id == "eval_1"
    assert result.next_cursor == "cursor_2"
    params = route.calls[0].request.url.params
    assert params["grade"] == "needs_review"
    assert params["page_size"] == "10"
    assert params["cursor"] == "cursor_1"


@respx.mock
def test_agents_get_evaluation(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/agents/agent_123/evaluations/eval_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "evaluation": {
                    "evaluation_id": "eval_1",
                    "interaction_id": "i1",
                    "agent_id": "agent_123",
                    "status": "completed",
                    "grade": "pass",
                }
            },
        )
    )

    result = client.agents.get_evaluation("agent_123", "eval_1")

    assert result.evaluation is not None
    assert result.evaluation.evaluation_id == "eval_1"
    assert result.evaluation.status == "completed"
    assert result.evaluation.grade == "pass"


@respx.mock
def test_async_agents_evaluation_methods() -> None:
    respx.get(f"{API_BASE}/agents/agent_123/evaluation-config").mock(
        return_value=httpx.Response(200, json={"config": {"agent_id": "agent_123"}})
    )
    respx.patch(f"{API_BASE}/agents/agent_123/evaluation-config").mock(
        return_value=httpx.Response(200, json={"config": {"agent_id": "agent_123", "enabled": True}})
    )
    respx.get(f"{API_BASE}/agents/agent_123/evaluations").mock(
        return_value=httpx.Response(200, json={"evaluations": []})
    )
    respx.get(f"{API_BASE}/agents/agent_123/evaluations/eval_1").mock(
        return_value=httpx.Response(
            200, json={"evaluation": {"evaluation_id": "eval_1", "interaction_id": "i1", "agent_id": "agent_123"}}
        )
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.agents.get_evaluation_config("agent_123")).config.agent_id == "agent_123"
            assert (await client.agents.update_evaluation_config("agent_123", enabled=True)).config.enabled is True
            assert (await client.agents.list_evaluations("agent_123")).evaluations == []
            assert (await client.agents.get_evaluation("agent_123", "eval_1")).evaluation.evaluation_id == "eval_1"

    asyncio.run(run())


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
