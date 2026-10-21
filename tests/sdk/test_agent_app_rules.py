from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.types import AgentAppRuleCreateRequest
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_rule_create_typed_request_and_kwargs(asynchronous: bool) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_1/app-rules").respond(
        201, json={"agent_id": "agent_1", "app_rule": {"id": "rule_1", "name": "Override", "status": "disabled"}}
    )
    request = AgentAppRuleCreateRequest(name="Original", conditions="true", status="disabled")

    async def run():
        async with AsyncGumloop(access_token="token") as client:
            return await client.agents.create_app_rule("agent_1", request, name="Override")

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(access_token="token") as client:
            response = client.agents.create_app_rule("agent_1", request, name="Override")
    assert (response.agent_id, response.app_rule.id, response.app_rule.status) == ("agent_1", "rule_1", "disabled")
    assert request_json(route.calls[0].request) == {"name": "Override", "conditions": "true", "status": "disabled"}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_rule_update_preserves_explicit_null_and_falsey_values(asynchronous: bool) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_1/app-rules/rule_1").respond(
        200, json={"agent_id": "agent_1", "app_rule": {"id": "rule_1", "priority": 0}}
    )
    request = {"description": None, "scope": None, "conditions": "true", "priority": 0}

    async def run():
        async with AsyncGumloop(access_token="token") as client:
            return await client.agents.update_app_rule("agent_1", "rule_1", request)

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(access_token="token") as client:
            response = client.agents.update_app_rule("agent_1", "rule_1", request)
    assert response.app_rule.priority == 0
    assert request_json(route.calls[0].request) == request


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_rule_delete_is_scoped_to_agent(asynchronous: bool) -> None:
    route = respx.delete(f"{API_BASE}/agents/agent_1/app-rules/rule_1").respond(
        200, json={"agent_id": "agent_1", "rule_id": "rule_1", "deleted": True}
    )

    async def run():
        async with AsyncGumloop(access_token="token") as client:
            return await client.agents.delete_app_rule("agent_1", "rule_1")

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(access_token="token") as client:
            response = client.agents.delete_app_rule("agent_1", "rule_1")
    assert (response.agent_id, response.rule_id, response.deleted) == ("agent_1", "rule_1", True)
    assert route.call_count == 1


@respx.mock
def test_empty_rule_update_fails_without_http(client: Gumloop) -> None:
    with pytest.raises(ValidationError) as error:
        client.agents.update_app_rule("agent_1", "rule_1", {})
    assert error.value.errors()[0]["type"] == "value_error"
    assert respx.calls.call_count == 0
