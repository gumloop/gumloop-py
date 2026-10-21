from __future__ import annotations

import asyncio
import json

import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE

CONFIG = {
    "operator_name": "Gmail Reader",
    "parameters": {"Label": "Inbox"},
    "credentials_to_use": {"gmail_access_token": {"secret_id": "account", "is_personal_credential": True}},
}
PAYLOAD = {
    "id": "trigger",
    "agent_id": "agent",
    "type": "integration",
    "enabled": False,
    "name": None,
    "prompt": None,
    "cron_expression": None,
    "run_at": None,
    "timezone": None,
    "pass_raw_data": None,
    "status": None,
    "max_failures": None,
    "webhook_url": None,
    "created_at": None,
    "last_run_at": None,
    "integration": {"operator_name": "Gmail Reader", "operator_version": "v1", "parameters": {"Label": "Inbox"}},
}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_create_and_replace_integration_configuration_are_typed(asynchronous):
    create = respx.post(f"{API_BASE}/agents/agent/triggers").respond(201, json={"trigger": PAYLOAD})
    update = respx.patch(f"{API_BASE}/agents/agent/triggers/trigger").respond(200, json={"trigger": PAYLOAD})
    body = {"type": "integration", "prompt": "Summarize mail", "enabled": False, "integration": CONFIG}

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            created = await client.agents.create_trigger("agent", body)
            changed = await client.agents.update_trigger("agent", "trigger", integration=CONFIG)
            return created, changed

    if asynchronous:
        created, changed = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            created = client.agents.create_trigger("agent", body)
            changed = client.agents.update_trigger("agent", "trigger", integration=CONFIG)
    assert created.trigger.integration is not None
    assert changed.trigger.integration is not None
    assert created.trigger.integration.operator_name == changed.trigger.integration.operator_name == "Gmail Reader"
    assert json.loads(create.calls[0].request.content) == body
    assert json.loads(update.calls[0].request.content) == {"integration": CONFIG}


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("method", "suffix", "response"),
    [
        (
            "list_trigger_operators",
            "trigger-operators",
            {
                "operators": [
                    {
                        "name": "Gmail Reader",
                        "display_name": "Gmail Reader",
                        "version": "v1",
                        "credential_types": ["gmail_access_token"],
                    }
                ]
            },
        ),
        ("get_trigger", "triggers/trigger%3Fid", {"trigger": PAYLOAD}),
        (
            "list_trigger_runs",
            "triggers/trigger%3Fid/runs",
            {
                "items": [
                    {"gummie_trigger_run_id": "run", "interaction_id": "chat", "state": "COMPLETED", "credit_cost": 3.0}
                ],
                "next_cursor": "next",
            },
        ),
        (
            "get_trigger_stats",
            "triggers/trigger%3Fid/stats",
            {"run_count": 1, "run_credits": 3.0, "poll_credits": 1.0, "total_credits": 4.0},
        ),
    ],
)
@respx.mock
def test_public_trigger_inspection_uses_encoded_ids_and_typed_responses(asynchronous, method, suffix, response):
    route = respx.get(f"{API_BASE}/agents/agent%3Fid/{suffix}").respond(200, json=response)
    args = ("agent?id",) if method == "list_trigger_operators" else ("agent?id", "trigger?id")
    kwargs = (
        {"page_size": 5, "cursor": "cursor", "states": ["COMPLETED", "FAILED"]} if method == "list_trigger_runs" else {}
    )

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            return await getattr(client.agents, method)(*args, **kwargs)

    if asynchronous:
        result = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            result = getattr(client.agents, method)(*args, **kwargs)
    assert result.model_dump(exclude_unset=True) == response
    assert dict(route.calls[0].request.url.params) == (
        {"page_size": "5", "cursor": "cursor", "state": "COMPLETED,FAILED"} if kwargs else {}
    )


@pytest.mark.parametrize(
    "body",
    [
        {"type": "integration", "prompt": "Mail"},
        {"type": "webhook", "prompt": "Mail", "integration": CONFIG},
        {"type": "integration", "prompt": "Mail", "integration": {**CONFIG, "event": {"internal_trigger": True}}},
        {
            "type": "integration",
            "prompt": "Mail",
            "integration": {
                **CONFIG,
                "credentials_to_use": {"gmail_access_token": {"secret_id": "account", "token": "secret"}},
            },
        },
    ],
)
@respx.mock
def test_integration_requests_refuse_ambiguous_or_raw_server_configuration(body):
    with Gumloop(api_key="key") as client, pytest.raises(ValidationError):
        client.agents.create_trigger("agent", body)
    assert not respx.calls


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("field", ["cron_expression", "run_at", "timezone"])
@respx.mock
def test_integration_requests_reject_empty_schedule_fields_before_http(asynchronous, field):
    body = {"type": "integration", "prompt": "Mail", "integration": CONFIG, field: ""}

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            await client.agents.create_trigger("agent", body)

    with pytest.raises(ValidationError, match="do not take schedule fields"):
        if asynchronous:
            asyncio.run(run())
        else:
            with Gumloop(api_key="key") as client:
                client.agents.create_trigger("agent", body)
    assert not respx.calls


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_null_schedule_fields_remain_absent_configuration(asynchronous):
    body = {
        "type": "integration",
        "prompt": "Mail",
        "integration": CONFIG,
        "cron_expression": None,
        "run_at": None,
        "timezone": None,
    }
    route = respx.post(f"{API_BASE}/agents/agent/triggers").respond(201, json={"trigger": PAYLOAD})

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            return await client.agents.create_trigger("agent", body)

    if asynchronous:
        result = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            result = client.agents.create_trigger("agent", body)
    assert result.trigger.id == "trigger"
    assert json.loads(route.calls[0].request.content) == body


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("refused_interaction", [{}, {"interaction_id": None}])
@respx.mock
def test_run_page_preserves_refused_deliveries_without_interactions(asynchronous, refused_interaction):
    respx.get(f"{API_BASE}/agents/agent/triggers/trigger/runs").respond(
        200,
        json={
            "items": [
                {"gummie_trigger_run_id": "complete", "interaction_id": "chat", "state": "COMPLETED"},
                {
                    "gummie_trigger_run_id": "refused",
                    "state": "FAILED",
                    "delivery_refusal": "not_reachable",
                    **refused_interaction,
                },
            ],
            "next_cursor": "next-page",
        },
    )

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            return await client.agents.list_trigger_runs("agent", "trigger")

    if asynchronous:
        page = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            page = client.agents.list_trigger_runs("agent", "trigger")
    assert [item.gummie_trigger_run_id for item in page.items] == ["complete", "refused"]
    assert page.items[0].interaction_id == "chat"
    assert page.items[1].interaction_id is None
    assert page.items[1].delivery_refusal == "not_reachable"
    assert page.next_cursor == "next-page"
