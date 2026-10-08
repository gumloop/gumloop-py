from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.types import AgentVersionTextFieldChange
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
def test_agents_list_versions_sends_pagination(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_123/versions").mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {
                        "id": "version_2",
                        "agent_id": "agent_123",
                        "major_version": 2,
                        "name": "Support Agent",
                    }
                ],
                "next_cursor": "cursor_2",
            },
        )
    )

    result = client.agents.list_versions(
        "agent_123",
        page_size=10,
        cursor="cursor_1",
        team_id="team_123",
    )

    assert result.versions[0].id == "version_2"
    assert result.next_cursor == "cursor_2"
    assert route.calls[0].request.url.params["page_size"] == "10"
    assert route.calls[0].request.url.params["cursor"] == "cursor_1"
    assert route.calls[0].request.url.params["team_id"] == "team_123"


@respx.mock
def test_agents_get_version_returns_exportable_composition(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_123/versions/version_2").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": {
                    "id": "version_2",
                    "agent_id": "agent_123",
                    "major_version": 2,
                    "name": "Support Agent",
                    "composition": {
                        "complete": True,
                        "schema_version": 1,
                        "name": "Support Agent",
                        "model_name": "auto",
                        "system_prompt": "Be helpful.",
                        "skill_ids": ["skill_1"],
                    },
                },
                "changes": {
                    "base_version_id": "version_1",
                    "attachment_changes_complete": True,
                    "field_changes": [
                        {
                            "field": "model_name",
                            "status": "changed",
                            "old_value": "gpt-4",
                            "new_value": "auto",
                        },
                        {
                            "field": "system_prompt",
                            "status": "changed",
                            "text_hunks": [
                                {
                                    "old_start": 3,
                                    "old_end": 10,
                                    "new_start": 3,
                                    "new_end": 10,
                                    "old_text": "concise",
                                    "new_text": "helpful",
                                }
                            ],
                        },
                    ],
                    "tool_changes": [
                        {
                            "identity": {"type": "mcp_server", "server_id": "server_1"},
                            "status": "changed",
                            "old_position": 0,
                            "new_position": 0,
                            "field_changes": [
                                {
                                    "field": "approval_mode",
                                    "status": "changed",
                                    "old_value": "all",
                                    "new_value": "off",
                                }
                            ],
                        }
                    ],
                    "skill_changes": [{"skill_id": "skill_1", "status": "added"}],
                    "knowledge_source_changes": [
                        {
                            "connector_id": "connector_1",
                            "status": "changed",
                            "old_config": None,
                            "new_config": {"folder_ids": ["folder_1"]},
                            "field_changes": [
                                {
                                    "field": "config",
                                    "status": "changed",
                                    "old_value": None,
                                    "new_value": {"folder_ids": ["folder_1"]},
                                }
                            ],
                        }
                    ],
                },
            },
        )
    )

    result = client.agents.get_version("agent_123", "version_2", team_id="team_123")

    assert result.version.composition.system_prompt == "Be helpful."
    assert result.version.composition.skill_ids == ["skill_1"]
    assert result.changes is not None
    assert result.changes.base_version_id == "version_1"
    assert result.changes.field_changes[0].field == "model_name"
    prompt_change = result.changes.field_changes[1]
    assert isinstance(prompt_change, AgentVersionTextFieldChange)
    assert prompt_change.text_hunks[0].new_text == "helpful"
    assert result.changes.tool_changes[0].identity["server_id"] == "server_1"
    assert result.changes.tool_changes[0].field_changes[0].field == "approval_mode"
    assert result.changes.skill_changes[0].status == "added"
    assert result.changes.knowledge_source_changes[0].status == "changed"
    assert result.changes.knowledge_source_changes[0].field_changes[0].field == "config"
    assert route.calls[0].request.url.params["team_id"] == "team_123"


@respx.mock
def test_agents_attach_skills_sends_only_attach_body(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123/skills").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "skill_ids": ["s1", "s2"], "attached": ["s2"]})
    )

    result = client.agents.attach_skills("agent_123", ["s1", "s2"])

    assert result.agent_id == "agent_123"
    assert result.skill_ids == ["s1", "s2"]
    assert result.attached == ["s2"]
    assert request_json(route.calls[0].request) == {"attach": ["s1", "s2"]}


@respx.mock
def test_agents_attach_skills_coerces_bare_string(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123/skills").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "attached": ["s1"]})
    )

    client.agents.attach_skills("agent_123", "s1")

    assert request_json(route.calls[0].request) == {"attach": ["s1"]}


@respx.mock
def test_agents_detach_skills_sends_only_detach_body(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123/skills").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "detached": ["s1"]})
    )

    result = client.agents.detach_skills("agent_123", "s1")

    assert result.detached == ["s1"]
    assert request_json(route.calls[0].request) == {"detach": ["s1"]}


@respx.mock
def test_agents_list_skills_sends_agent_id_param(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/skills").mock(return_value=httpx.Response(200, json={"skills": []}))

    result = client.agents.list_skills("agent_123")

    assert result.skills == []
    assert route.calls[0].request.url.params["agent_id"] == "agent_123"


@respx.mock
def test_agents_attach_mcp_server_puts_config(client: Gumloop) -> None:
    route = respx.put(f"{API_BASE}/agents/agent_123/mcp-servers/gmail").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_id": "agent_123",
                "mcp_server": {"type": "gumcp_server", "server_id": "gmail", "approval_mode": "off"},
                "created": True,
                "auth_status": "connected",
            },
        )
    )

    result = client.agents.attach_mcp_server("agent_123", "gmail", approval_mode="off")

    assert result.created is True
    assert result.auth_status == "connected"
    assert result.mcp_server is not None and result.mcp_server.server_id == "gmail"
    assert request_json(route.calls[0].request) == {"approval_mode": "off"}


@respx.mock
def test_agents_detach_mcp_server(client: Gumloop) -> None:
    route = respx.delete(f"{API_BASE}/agents/agent_123/mcp-servers/gmail").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "server_id": "gmail", "detached": True})
    )

    result = client.agents.detach_mcp_server("agent_123", "gmail")

    assert result.detached is True
    assert result.server_id == "gmail"
    assert route.call_count == 1


@respx.mock
def test_agents_list_mcp_servers(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/agents/agent_123/mcp-servers").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "mcp_servers": [{"server_id": "gmail"}]})
    )

    result = client.agents.list_mcp_servers("agent_123")

    assert result.agent_id == "agent_123"
    assert [server.server_id for server in result.mcp_servers] == ["gmail"]


@respx.mock
def test_async_agents_skill_and_mcp_methods() -> None:
    respx.patch(f"{API_BASE}/agents/agent_123/skills").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "attached": ["s1"]})
    )
    respx.get(f"{API_BASE}/skills").mock(return_value=httpx.Response(200, json={"skills": []}))
    respx.put(f"{API_BASE}/agents/agent_123/mcp-servers/gmail").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "created": True})
    )
    respx.delete(f"{API_BASE}/agents/agent_123/mcp-servers/gmail").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "server_id": "gmail", "detached": True})
    )
    respx.get(f"{API_BASE}/agents/agent_123/mcp-servers").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "mcp_servers": []})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.agents.attach_skills("agent_123", "s1")).attached == ["s1"]
            assert (await client.agents.detach_skills("agent_123", ["s1"])).agent_id == "agent_123"
            assert (await client.agents.list_skills("agent_123")).skills == []
            assert (await client.agents.attach_mcp_server("agent_123", "gmail", approval_mode="off")).created is True
            assert (await client.agents.detach_mcp_server("agent_123", "gmail")).detached is True
            assert (await client.agents.list_mcp_servers("agent_123")).mcp_servers == []

    asyncio.run(run())


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

    result = client.agents.list_evaluations(
        "agent_123", grade="needs_review", organization_evaluation_id="oe_1", page_size=10, cursor="cursor_1"
    )

    assert result.evaluations[0].evaluation_id == "eval_1"
    assert result.next_cursor == "cursor_2"
    params = route.calls[0].request.url.params
    assert params["grade"] == "needs_review"
    assert params["organization_evaluation_id"] == "oe_1"
    assert params["page_size"] == "10"
    assert params["cursor"] == "cursor_1"


@respx.mock
def test_agents_run_evaluations_supports_dry_run(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents/agent_123/evaluations/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "dry_run": True,
                "credit_cost": 1,
                "results": [{"id": None, "session_id": "session_1", "status": "planned"}],
                "skipped": [{"session_id": "session_2", "reason": "ineligible", "result_id": None}],
            },
        )
    )

    result = client.agents.run_evaluations("agent_123", session_ids=["session_1", "session_2"], dry_run=True)

    assert request_json(route.calls[0].request) == {"session_ids": ["session_1", "session_2"], "dry_run": True}
    assert result.dry_run is True
    assert [item.status for item in result.results] == ["planned"]
    assert result.skipped[0].reason == "ineligible"


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
            evaluation = (await client.agents.get_evaluation("agent_123", "eval_1")).evaluation
            assert evaluation is not None
            assert evaluation.evaluation_id == "eval_1"

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
    respx.get(f"{API_BASE}/agents/agent_123/versions").mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {
                        "id": "version_1",
                        "agent_id": "agent_123",
                        "major_version": 1,
                        "name": "Support Agent",
                    }
                ]
            },
        )
    )
    respx.get(f"{API_BASE}/agents/agent_123/versions/version_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": {
                    "id": "version_1",
                    "agent_id": "agent_123",
                    "major_version": 1,
                    "name": "Support Agent",
                    "composition": {
                        "complete": True,
                        "name": "Support Agent",
                        "model_name": "auto",
                    },
                }
            },
        )
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
            assert (await client.agents.list_versions("agent_123")).versions[0].id == "version_1"
            assert (await client.agents.get_version("agent_123", "version_1")).version.major_version == 1
            assert (await client.agents.update("agent_123", model_name="auto")).agent.id == "agent_123"
            assert (await client.models.list()).model_groups == []

    asyncio.run(run())


@respx.mock
def test_agents_update_sends_version_and_typed_metadata(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent": {"id": "agent_123", "name": "A", "version": 4}})
    )

    result = client.agents.update("agent_123", version=3, metadata={"fallback": {"enabled": True}, "max_steps": 20})

    assert result.agent.version == 4
    assert request_json(route.calls[0].request) == {
        "version": 3,
        "metadata": {"fallback": {"enabled": True}, "max_steps": 20},
    }


@respx.mock
def test_agents_retrieve_parses_whole_configuration(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent": {
                    "id": "agent_123",
                    "name": "A",
                    "version": 2,
                    "tools": [{"type": "gumcp_server", "server_id": "slack", "approval_mode": "write"}],
                    "metadata": {"voice": {"enabled": True}, "future_section": {"x": 1}},
                    "abilities": {
                        "web_search": {"enabled": True, "provider": "exa"},
                        "ask_question": {"enabled": False},
                    },
                    "knowledge_sources": [{"connector_id": "conn_1", "config": None}],
                    "triggers": [{"id": "trg_1", "agent_id": "agent_123", "type": "schedule", "enabled": True}],
                }
            },
        )
    )

    agent = client.agents.retrieve("agent_123").agent

    assert agent.version == 2
    assert agent.tools[0].server_id == "slack"
    assert agent.metadata.voice is not None and agent.metadata.voice.enabled is True
    assert agent.abilities is not None and agent.abilities.web_search is not None
    assert agent.abilities.web_search.provider == "exa"
    assert agent.knowledge_sources is not None and agent.knowledge_sources[0].config is None
    assert agent.triggers is not None and agent.triggers[0].type == "schedule"


@respx.mock
def test_agents_create_sends_knowledge_sources_without_scope_as_null(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(201, json={"agent": {"id": "agent_123", "name": "A"}})
    )

    client.agents.create(
        name="A",
        knowledge_sources=[
            {"connector_id": "conn_1"},
            {
                "connector_id": "conn_2",
                "config": {"mode": "include_only", "inclusions": [{"type": "container", "id": "f"}]},
            },
        ],
    )

    assert request_json(route.calls[0].request)["knowledge_sources"] == [
        {"connector_id": "conn_1"},
        {
            "connector_id": "conn_2",
            "config": {"mode": "include_only", "inclusions": [{"type": "container", "id": "f"}]},
        },
    ]


@respx.mock
def test_agents_delete(client: Gumloop) -> None:
    respx.delete(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "deleted": True})
    )

    assert client.agents.delete("agent_123").deleted is True


@respx.mock
def test_agents_update_abilities_sends_only_given_abilities(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123/abilities").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_id": "agent_123",
                "abilities": {"web_search": {"enabled": True, "provider": "exa"}, "ask_question": {"enabled": False}},
                "version": 5,
            },
        )
    )

    result = client.agents.update_abilities(
        "agent_123", web_search={"enabled": True, "provider": "exa"}, ask_question={"enabled": False}, version=4
    )

    assert result.version == 5
    assert result.abilities.ask_question is not None and result.abilities.ask_question.enabled is False
    assert request_json(route.calls[0].request) == {
        "web_search": {"enabled": True, "provider": "exa"},
        "ask_question": {"enabled": False},
        "version": 4,
    }


@respx.mock
def test_agents_set_incognito_patches_the_dedicated_route_and_reads_the_flag_back(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/agents/agent_123/incognito").mock(
        return_value=httpx.Response(
            200, json={"agent": {"id": "agent_123", "name": "Quiet", "incognito": {"enforced": True}}}
        )
    )

    result = client.agents.set_incognito("agent_123", True)

    assert (result.agent.incognito.enforced, request_json(route.calls[0].request)) == (True, {"enforced": True})


@respx.mock
def test_agents_knowledge_source_attach_sends_config_key_even_when_whole_source(client: Gumloop) -> None:
    whole = respx.put(f"{API_BASE}/agents/agent_123/knowledge-sources/conn_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_id": "agent_123",
                "knowledge_source": {"connector_id": "conn_1", "config": None},
                "outcome": "attached",
            },
        )
    )

    result = client.agents.attach_knowledge_source("agent_123", "conn_1")
    client.agents.attach_knowledge_source(
        "agent_123", "conn_1", config={"exclusions": [{"type": "document", "id": "d"}]}
    )

    assert result.outcome == "attached"
    assert request_json(whole.calls[0].request) == {"config": None}
    assert request_json(whole.calls[1].request) == {"config": {"exclusions": [{"type": "document", "id": "d"}]}}


@respx.mock
def test_agents_knowledge_source_list_and_detach(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/agents/agent_123/knowledge-sources").mock(
        return_value=httpx.Response(
            200, json={"agent_id": "agent_123", "knowledge_sources": [{"connector_id": "conn_1", "config": None}]}
        )
    )
    respx.delete(f"{API_BASE}/agents/agent_123/knowledge-sources/conn_1").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "connector_id": "conn_1", "detached": True})
    )

    assert client.agents.list_knowledge_sources("agent_123").knowledge_sources[0].connector_id == "conn_1"
    assert client.agents.detach_knowledge_source("agent_123", "conn_1").detached is True


@respx.mock
def test_agents_subagent_attach_and_detach(client: Gumloop) -> None:
    attach = respx.put(f"{API_BASE}/agents/agent_123/subagents/agent_456").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "subagent_ids": ["agent_456"], "changed": True})
    )
    respx.delete(f"{API_BASE}/agents/agent_123/subagents/agent_456").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "subagent_ids": [], "changed": True})
    )

    assert client.agents.attach_subagent("agent_123", "agent_456").subagent_ids == ["agent_456"]
    assert client.agents.detach_subagent("agent_123", "agent_456").subagent_ids == []
    assert attach.calls[0].request.content == b""


@respx.mock
def test_agents_triggers_create_update_list_delete_and_reveal(client: Gumloop) -> None:
    created = respx.post(f"{API_BASE}/agents/agent_123/triggers").mock(
        return_value=httpx.Response(
            201,
            json={"trigger": {"id": "trg_1", "agent_id": "agent_123", "type": "schedule", "enabled": True}},
        )
    )
    updated = respx.patch(f"{API_BASE}/agents/agent_123/triggers/trg_1").mock(
        return_value=httpx.Response(
            200, json={"trigger": {"id": "trg_1", "agent_id": "agent_123", "type": "schedule", "enabled": False}}
        )
    )
    respx.get(f"{API_BASE}/agents/agent_123/triggers").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "triggers": [], "next_cursor": None})
    )
    respx.get(f"{API_BASE}/agents/agent_123/triggers/trg_1/webhook-url").mock(
        return_value=httpx.Response(
            200, json={"agent_id": "agent_123", "trigger_id": "trg_1", "webhook_url": "https://hooks/trg_1/s"}
        )
    )
    respx.delete(f"{API_BASE}/agents/agent_123/triggers/trg_1").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "trigger_id": "trg_1", "deleted": True})
    )

    trigger = client.agents.create_trigger(
        "agent_123", type="schedule", prompt="Daily digest", cron_expression="0 9 * * 1-5", timezone="UTC"
    ).trigger
    client.agents.update_trigger("agent_123", "trg_1", enabled=False)

    assert trigger.id == "trg_1" and trigger.enabled is True
    assert request_json(created.calls[0].request) == {
        "type": "schedule",
        "prompt": "Daily digest",
        "cron_expression": "0 9 * * 1-5",
        "timezone": "UTC",
    }
    assert request_json(updated.calls[0].request) == {"enabled": False}
    assert client.agents.list_triggers("agent_123").triggers == []
    assert client.agents.get_trigger_webhook_url("agent_123", "trg_1").webhook_url == "https://hooks/trg_1/s"
    assert client.agents.delete_trigger("agent_123", "trg_1").deleted is True


@respx.mock
def test_agents_list_app_rules(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/agents/agent_123/app-rules").mock(
        return_value=httpx.Response(
            200,
            json={"agent_id": "agent_123", "app_rules": [{"id": "pol_1", "name": "No deletes", "server_id": "gmail"}]},
        )
    )

    rules = client.agents.list_app_rules("agent_123").app_rules

    assert rules[0].id == "pol_1" and rules[0].server_id == "gmail"


@respx.mock
def test_async_agents_configuration_methods() -> None:
    respx.delete(f"{API_BASE}/agents/agent_123").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "deleted": True})
    )
    respx.patch(f"{API_BASE}/agents/agent_123/abilities").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "abilities": {}, "version": 2})
    )
    respx.put(f"{API_BASE}/agents/agent_123/knowledge-sources/conn_1").mock(
        return_value=httpx.Response(
            200, json={"agent_id": "agent_123", "knowledge_source": {"connector_id": "conn_1"}, "outcome": "attached"}
        )
    )
    respx.get(f"{API_BASE}/agents/agent_123/knowledge-sources").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "knowledge_sources": []})
    )
    respx.delete(f"{API_BASE}/agents/agent_123/knowledge-sources/conn_1").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "connector_id": "conn_1", "detached": True})
    )
    respx.put(f"{API_BASE}/agents/agent_123/subagents/agent_456").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "subagent_ids": ["agent_456"], "changed": True})
    )
    respx.delete(f"{API_BASE}/agents/agent_123/subagents/agent_456").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "subagent_ids": [], "changed": True})
    )
    respx.get(f"{API_BASE}/agents/agent_123/triggers").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "triggers": []})
    )
    respx.post(f"{API_BASE}/agents/agent_123/triggers").mock(
        return_value=httpx.Response(
            201,
            json={"trigger": {"id": "trg_1", "agent_id": "agent_123", "type": "webhook", "webhook_url": "https://h"}},
        )
    )
    respx.patch(f"{API_BASE}/agents/agent_123/triggers/trg_1").mock(
        return_value=httpx.Response(200, json={"trigger": {"id": "trg_1", "agent_id": "agent_123", "type": "webhook"}})
    )
    respx.get(f"{API_BASE}/agents/agent_123/triggers/trg_1/webhook-url").mock(
        return_value=httpx.Response(
            200, json={"agent_id": "agent_123", "trigger_id": "trg_1", "webhook_url": "https://h"}
        )
    )
    respx.delete(f"{API_BASE}/agents/agent_123/triggers/trg_1").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "trigger_id": "trg_1", "deleted": True})
    )
    respx.get(f"{API_BASE}/agents/agent_123/app-rules").mock(
        return_value=httpx.Response(200, json={"agent_id": "agent_123", "app_rules": []})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.agents.update_abilities("agent_123", web_search={"enabled": True})).version == 2
            assert (await client.agents.attach_knowledge_source("agent_123", "conn_1")).outcome == "attached"
            assert (await client.agents.list_knowledge_sources("agent_123")).knowledge_sources == []
            assert (await client.agents.detach_knowledge_source("agent_123", "conn_1")).detached is True
            assert (await client.agents.attach_subagent("agent_123", "agent_456")).changed is True
            assert (await client.agents.detach_subagent("agent_123", "agent_456")).subagent_ids == []
            assert (await client.agents.list_triggers("agent_123")).triggers == []
            created = await client.agents.create_trigger("agent_123", type="webhook", prompt="Handle it")
            assert created.trigger.webhook_url == "https://h"
            assert (await client.agents.update_trigger("agent_123", "trg_1", prompt="x")).trigger.id == "trg_1"
            assert (await client.agents.get_trigger_webhook_url("agent_123", "trg_1")).webhook_url == "https://h"
            assert (await client.agents.delete_trigger("agent_123", "trg_1")).deleted is True
            assert (await client.agents.list_app_rules("agent_123")).app_rules == []
            assert (await client.agents.delete("agent_123")).deleted is True

    asyncio.run(run())
