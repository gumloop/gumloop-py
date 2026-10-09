from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import AgentAbilitiesResponse
from gumloop.types import AgentAbilitiesUpdateRequest
from gumloop.types import AgentAppRulesResponse
from gumloop.types import AgentCreateRequest
from gumloop.types import AgentDeleteResponse
from gumloop.types import AgentEvaluationMetricsResponse
from gumloop.types import AgentEvaluationOptionsResponse
from gumloop.types import AgentKnowledgeSourceDetachResponse
from gumloop.types import AgentKnowledgeSourceResponse
from gumloop.types import AgentKnowledgeSourcesResponse
from gumloop.types import AgentListResponse
from gumloop.types import AgentMcpServerDetachResponse
from gumloop.types import AgentMcpServerResponse
from gumloop.types import AgentMcpServersResponse
from gumloop.types import AgentResponse
from gumloop.types import AgentSkillsResponse
from gumloop.types import AgentSubagentsResponse
from gumloop.types import AgentTriggerCreateRequest
from gumloop.types import AgentTriggerDeleteResponse
from gumloop.types import AgentTriggerResponse
from gumloop.types import AgentTriggersResponse
from gumloop.types import AgentTriggerUpdateRequest
from gumloop.types import AgentTriggerWebhookUrlResponse
from gumloop.types import AgentUpdateRequest
from gumloop.types import AgentVersionResponse
from gumloop.types import AgentVersionsResponse
from gumloop.types import EvaluationConfigResponse
from gumloop.types import EvaluationConfigUpdateRequest
from gumloop.types import EvaluationResultListResponse
from gumloop.types import EvaluationResultResponse
from gumloop.types import EvaluationRunRequest
from gumloop.types import EvaluationRunResponse
from gumloop.types import KnowledgeSourceScope
from gumloop.types import ModelListResponse
from gumloop.types import ModelRouteRequest
from gumloop.types import ModelRouteResponse
from gumloop.types import SkillListResponse


def _skill_id_list(skill_ids: str | Sequence[str]) -> list[str]:
    return [skill_ids] if isinstance(skill_ids, str) else list(skill_ids)


def _knowledge_scope_body(config: KnowledgeSourceScope | Mapping[str, Any] | None) -> dict[str, Any]:
    # The key is always sent: null means the whole source.
    if config is None:
        return {"config": None}
    scope = config if isinstance(config, KnowledgeSourceScope) else KnowledgeSourceScope.model_validate(config)
    return {"config": scope.model_dump(exclude_unset=True)}


class Agents:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(
        self,
        *,
        search: str | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> AgentListResponse:
        return AgentListResponse.model_validate(
            self._client.get("agents", params={"search": search, "team_id": team_id, **kwargs})
        )

    def create(
        self,
        request: AgentCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        body = AgentCreateRequest.build(request, **kwargs)
        # The create workspace is read from the body, not the query.
        if self._client.team_id is not None:
            body.setdefault("team_id", self._client.team_id)
        return AgentResponse.model_validate(self._client.post("agents", json=body))

    def retrieve(self, agent_id: str) -> AgentResponse:
        return AgentResponse.model_validate(self._client.get(f"agents/{agent_id}"))

    def list_versions(
        self,
        agent_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        team_id: str | None = None,
    ) -> AgentVersionsResponse:
        return AgentVersionsResponse.model_validate(
            self._client.get(
                f"agents/{agent_id}/versions",
                params={"page_size": page_size, "cursor": cursor, "team_id": team_id},
            )
        )

    def get_version(
        self,
        agent_id: str,
        version_id: str,
        *,
        team_id: str | None = None,
    ) -> AgentVersionResponse:
        return AgentVersionResponse.model_validate(
            self._client.get(
                f"agents/{agent_id}/versions/{version_id}",
                params={"team_id": team_id},
            )
        )

    def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Settings live under ``metadata`` and merge section by section. Pass ``version``
        from a previous read to refuse the update if the agent changed since
        (``agent_version_conflict``). ``tools`` replaces the whole list when provided;
        prefer update_abilities, attach_mcp_server/detach_mcp_server and
        attach_skills/detach_skills."""
        return AgentResponse.model_validate(
            self._client.patch(f"agents/{agent_id}", json=AgentUpdateRequest.build(request, **kwargs))
        )

    def attach_skills(self, agent_id: str, skill_ids: str | Sequence[str]) -> AgentSkillsResponse:
        """Attach skills to an agent. Idempotent: safe to retry, already-attached ids are reported."""
        return AgentSkillsResponse.model_validate(
            self._client.patch(f"agents/{agent_id}/skills", json={"attach": _skill_id_list(skill_ids)})
        )

    def detach_skills(self, agent_id: str, skill_ids: str | Sequence[str]) -> AgentSkillsResponse:
        """Detach skills from an agent. Idempotent: safe to retry, already-detached ids are reported."""
        return AgentSkillsResponse.model_validate(
            self._client.patch(f"agents/{agent_id}/skills", json={"detach": _skill_id_list(skill_ids)})
        )

    def list_skills(self, agent_id: str, **kwargs: Any) -> SkillListResponse:
        return SkillListResponse.model_validate(self._client.get("skills", params={"agent_id": agent_id, **kwargs}))

    def attach_mcp_server(self, agent_id: str, server_id: str, **config: Any) -> AgentMcpServerResponse:
        """Attach an MCP server, or update its config if already attached (idempotent upsert)."""
        return AgentMcpServerResponse.model_validate(
            self._client.put(
                f"agents/{agent_id}/mcp-servers/{server_id}",
                json={k: v for k, v in config.items() if v is not None},
            )
        )

    def detach_mcp_server(self, agent_id: str, server_id: str) -> AgentMcpServerDetachResponse:
        """Detach an MCP server from an agent. Idempotent: safe to retry."""
        return AgentMcpServerDetachResponse.model_validate(
            self._client.delete(f"agents/{agent_id}/mcp-servers/{server_id}")
        )

    def list_mcp_servers(self, agent_id: str) -> AgentMcpServersResponse:
        return AgentMcpServersResponse.model_validate(self._client.get(f"agents/{agent_id}/mcp-servers"))

    def delete(self, agent_id: str) -> AgentDeleteResponse:
        """Delete a custom agent. Platform agents (``gumball``, ``analytics``) are refused."""
        return AgentDeleteResponse.model_validate(self._client.delete(f"agents/{agent_id}"))

    def update_abilities(
        self,
        agent_id: str,
        request: AgentAbilitiesUpdateRequest | Mapping[str, Any] | None = None,
        **abilities: Any,
    ) -> AgentAbilitiesResponse:
        """Turn native abilities on or off and set their options, e.g.
        ``update_abilities(agent_id, web_search={"enabled": True, "provider": "exa"},
        ask_question={"enabled": False})``. Only the abilities you send change."""
        return AgentAbilitiesResponse.model_validate(
            self._client.patch(
                f"agents/{agent_id}/abilities",
                json=AgentAbilitiesUpdateRequest.build(request, **abilities),
            )
        )

    def set_incognito(self, agent_id: str, enforced: bool) -> AgentResponse:
        """Make every session on the agent incognito (nothing is saved), or stop doing so.
        Needs the Incognito agents role permission (``organization_permission_required`` otherwise)."""
        return AgentResponse.model_validate(
            self._client.patch(f"agents/{agent_id}/incognito", json={"enforced": enforced})
        )

    def list_knowledge_sources(self, agent_id: str) -> AgentKnowledgeSourcesResponse:
        return AgentKnowledgeSourcesResponse.model_validate(self._client.get(f"agents/{agent_id}/knowledge-sources"))

    def attach_knowledge_source(
        self,
        agent_id: str,
        connector_id: str,
        *,
        config: KnowledgeSourceScope | Mapping[str, Any] | None = None,
    ) -> AgentKnowledgeSourceResponse:
        """Attach a Brain source, or change its scope if already attached (idempotent upsert).
        ``config=None`` attaches the whole source."""
        return AgentKnowledgeSourceResponse.model_validate(
            self._client.put(
                f"agents/{agent_id}/knowledge-sources/{connector_id}",
                json=_knowledge_scope_body(config),
            )
        )

    def detach_knowledge_source(self, agent_id: str, connector_id: str) -> AgentKnowledgeSourceDetachResponse:
        """Detach a Brain source. Idempotent: safe to retry."""
        return AgentKnowledgeSourceDetachResponse.model_validate(
            self._client.delete(f"agents/{agent_id}/knowledge-sources/{connector_id}")
        )

    def attach_subagent(self, agent_id: str, subagent_id: str) -> AgentSubagentsResponse:
        """Allow the agent to delegate to ``subagent_id``. Idempotent; the subagent must live in the same workspace."""
        return AgentSubagentsResponse.model_validate(self._client.put(f"agents/{agent_id}/subagents/{subagent_id}"))

    def detach_subagent(self, agent_id: str, subagent_id: str) -> AgentSubagentsResponse:
        return AgentSubagentsResponse.model_validate(self._client.delete(f"agents/{agent_id}/subagents/{subagent_id}"))

    def list_triggers(
        self,
        agent_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> AgentTriggersResponse:
        return AgentTriggersResponse.model_validate(
            self._client.get(f"agents/{agent_id}/triggers", params={"page_size": page_size, "cursor": cursor})
        )

    def create_trigger(
        self,
        agent_id: str,
        request: AgentTriggerCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentTriggerResponse:
        """Create a ``schedule`` (``cron_expression`` or ``run_at``) or ``webhook`` trigger.
        A webhook's URL is returned here and from ``get_trigger_webhook_url``, never in lists."""
        return AgentTriggerResponse.model_validate(
            self._client.post(f"agents/{agent_id}/triggers", json=AgentTriggerCreateRequest.build(request, **kwargs))
        )

    def update_trigger(
        self,
        agent_id: str,
        trigger_id: str,
        request: AgentTriggerUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentTriggerResponse:
        """Edit, enable or disable a schedule or webhook trigger. Only the fields you send change."""
        return AgentTriggerResponse.model_validate(
            self._client.patch(
                f"agents/{agent_id}/triggers/{trigger_id}",
                json=AgentTriggerUpdateRequest.build(request, **kwargs),
            )
        )

    def delete_trigger(self, agent_id: str, trigger_id: str) -> AgentTriggerDeleteResponse:
        return AgentTriggerDeleteResponse.model_validate(
            self._client.delete(f"agents/{agent_id}/triggers/{trigger_id}")
        )

    def get_trigger_webhook_url(self, agent_id: str, trigger_id: str) -> AgentTriggerWebhookUrlResponse:
        """The webhook URL embeds its secret; fetch it on demand rather than storing it."""
        return AgentTriggerWebhookUrlResponse.model_validate(
            self._client.get(f"agents/{agent_id}/triggers/{trigger_id}/webhook-url")
        )

    def list_app_rules(self, agent_id: str) -> AgentAppRulesResponse:
        """Rules the agent has authored for its connectors. Read only."""
        return AgentAppRulesResponse.model_validate(self._client.get(f"agents/{agent_id}/app-rules"))

    def get_evaluation_options(self) -> AgentEvaluationOptionsResponse:
        return AgentEvaluationOptionsResponse.model_validate(self._client.get("agents/evaluation-options"))

    def get_evaluation_config(self, agent_id: str) -> EvaluationConfigResponse:
        return EvaluationConfigResponse.model_validate(self._client.get(f"agents/{agent_id}/evaluation-config"))

    def update_evaluation_config(
        self,
        agent_id: str,
        request: EvaluationConfigUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationConfigResponse:
        """Partially update the evaluation config. Only the fields you send are changed;
        omitted fields keep their current value. A provided list (criteria/tags/
        data_points) replaces that list wholesale."""
        return EvaluationConfigResponse.model_validate(
            self._client.patch(
                f"agents/{agent_id}/evaluation-config",
                json=EvaluationConfigUpdateRequest.build(request, **kwargs),
            )
        )

    def list_evaluations(
        self,
        agent_id: str,
        *,
        grade: str | None = None,
        status: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        session_id: str | None = None,
        organization_evaluation_id: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> EvaluationResultListResponse:
        """Results from the agent's own evaluation by default; ``organization_evaluation_id`` selects the
        results one organization evaluation produced for this agent instead."""
        return EvaluationResultListResponse.model_validate(
            self._client.get(
                f"agents/{agent_id}/evaluations",
                params={
                    "grade": grade,
                    "status": status,
                    "created_after": created_after.isoformat() if created_after is not None else None,
                    "created_before": created_before.isoformat() if created_before is not None else None,
                    "session_id": session_id,
                    "organization_evaluation_id": organization_evaluation_id,
                    "page_size": page_size,
                    "cursor": cursor,
                    **kwargs,
                },
            )
        )

    def get_evaluation_metrics(self, agent_id: str, days: int = 30) -> AgentEvaluationMetricsResponse:
        return AgentEvaluationMetricsResponse.model_validate(
            self._client.get(f"agents/{agent_id}/evaluations/metrics", params={"days": days})
        )

    def run_evaluations(
        self,
        agent_id: str,
        request: EvaluationRunRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationRunResponse:
        return EvaluationRunResponse.model_validate(
            self._client.post(f"agents/{agent_id}/evaluations/run", json=EvaluationRunRequest.build(request, **kwargs))
        )

    def get_evaluation(self, agent_id: str, evaluation_id: str) -> EvaluationResultResponse:
        return EvaluationResultResponse.model_validate(
            self._client.get(f"agents/{agent_id}/evaluations/{evaluation_id}")
        )


class Models:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self, **kwargs: Any) -> ModelListResponse:
        return ModelListResponse.model_validate(self._client.get("models", params=kwargs))

    def route(
        self,
        request: ModelRouteRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelRouteResponse:
        body = ModelRouteRequest.build(request, **kwargs)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        return ModelRouteResponse.model_validate(self._client.post("models/route", json=body))


class AsyncAgents:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(
        self,
        *,
        search: str | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> AgentListResponse:
        data = await self._client.get("agents", params={"search": search, "team_id": team_id, **kwargs})
        return AgentListResponse.model_validate(data)

    async def create(
        self,
        request: AgentCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        body = AgentCreateRequest.build(request, **kwargs)
        # The create workspace is read from the body, not the query.
        if self._client.team_id is not None:
            body.setdefault("team_id", self._client.team_id)
        data = await self._client.post("agents", json=body)
        return AgentResponse.model_validate(data)

    async def retrieve(self, agent_id: str) -> AgentResponse:
        return AgentResponse.model_validate(await self._client.get(f"agents/{agent_id}"))

    async def list_versions(
        self,
        agent_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        team_id: str | None = None,
    ) -> AgentVersionsResponse:
        data = await self._client.get(
            f"agents/{agent_id}/versions",
            params={"page_size": page_size, "cursor": cursor, "team_id": team_id},
        )
        return AgentVersionsResponse.model_validate(data)

    async def get_version(
        self,
        agent_id: str,
        version_id: str,
        *,
        team_id: str | None = None,
    ) -> AgentVersionResponse:
        data = await self._client.get(
            f"agents/{agent_id}/versions/{version_id}",
            params={"team_id": team_id},
        )
        return AgentVersionResponse.model_validate(data)

    async def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Settings live under ``metadata`` and merge section by section. Pass ``version``
        from a previous read to refuse the update if the agent changed since
        (``agent_version_conflict``). ``tools`` replaces the whole list when provided;
        prefer update_abilities, attach_mcp_server/detach_mcp_server and
        attach_skills/detach_skills."""
        data = await self._client.patch(f"agents/{agent_id}", json=AgentUpdateRequest.build(request, **kwargs))
        return AgentResponse.model_validate(data)

    async def attach_skills(self, agent_id: str, skill_ids: str | Sequence[str]) -> AgentSkillsResponse:
        """Attach skills to an agent. Idempotent: safe to retry, already-attached ids are reported."""
        data = await self._client.patch(f"agents/{agent_id}/skills", json={"attach": _skill_id_list(skill_ids)})
        return AgentSkillsResponse.model_validate(data)

    async def detach_skills(self, agent_id: str, skill_ids: str | Sequence[str]) -> AgentSkillsResponse:
        """Detach skills from an agent. Idempotent: safe to retry, already-detached ids are reported."""
        data = await self._client.patch(f"agents/{agent_id}/skills", json={"detach": _skill_id_list(skill_ids)})
        return AgentSkillsResponse.model_validate(data)

    async def list_skills(self, agent_id: str, **kwargs: Any) -> SkillListResponse:
        data = await self._client.get("skills", params={"agent_id": agent_id, **kwargs})
        return SkillListResponse.model_validate(data)

    async def attach_mcp_server(self, agent_id: str, server_id: str, **config: Any) -> AgentMcpServerResponse:
        """Attach an MCP server, or update its config if already attached (idempotent upsert)."""
        data = await self._client.put(
            f"agents/{agent_id}/mcp-servers/{server_id}",
            json={k: v for k, v in config.items() if v is not None},
        )
        return AgentMcpServerResponse.model_validate(data)

    async def detach_mcp_server(self, agent_id: str, server_id: str) -> AgentMcpServerDetachResponse:
        """Detach an MCP server from an agent. Idempotent: safe to retry."""
        data = await self._client.delete(f"agents/{agent_id}/mcp-servers/{server_id}")
        return AgentMcpServerDetachResponse.model_validate(data)

    async def list_mcp_servers(self, agent_id: str) -> AgentMcpServersResponse:
        data = await self._client.get(f"agents/{agent_id}/mcp-servers")
        return AgentMcpServersResponse.model_validate(data)

    async def delete(self, agent_id: str) -> AgentDeleteResponse:
        """Delete a custom agent. Platform agents (``gumball``, ``analytics``) are refused."""
        return AgentDeleteResponse.model_validate(await self._client.delete(f"agents/{agent_id}"))

    async def update_abilities(
        self,
        agent_id: str,
        request: AgentAbilitiesUpdateRequest | Mapping[str, Any] | None = None,
        **abilities: Any,
    ) -> AgentAbilitiesResponse:
        """Turn native abilities on or off and set their options. Only the abilities you send change."""
        data = await self._client.patch(
            f"agents/{agent_id}/abilities", json=AgentAbilitiesUpdateRequest.build(request, **abilities)
        )
        return AgentAbilitiesResponse.model_validate(data)

    async def set_incognito(self, agent_id: str, enforced: bool) -> AgentResponse:
        """Make every session on the agent incognito (nothing is saved), or stop doing so.
        Needs the Incognito agents role permission (``organization_permission_required`` otherwise)."""
        data = await self._client.patch(f"agents/{agent_id}/incognito", json={"enforced": enforced})
        return AgentResponse.model_validate(data)

    async def list_knowledge_sources(self, agent_id: str) -> AgentKnowledgeSourcesResponse:
        data = await self._client.get(f"agents/{agent_id}/knowledge-sources")
        return AgentKnowledgeSourcesResponse.model_validate(data)

    async def attach_knowledge_source(
        self,
        agent_id: str,
        connector_id: str,
        *,
        config: KnowledgeSourceScope | Mapping[str, Any] | None = None,
    ) -> AgentKnowledgeSourceResponse:
        """Attach a Brain source, or change its scope if already attached (idempotent upsert).
        ``config=None`` attaches the whole source."""
        data = await self._client.put(
            f"agents/{agent_id}/knowledge-sources/{connector_id}", json=_knowledge_scope_body(config)
        )
        return AgentKnowledgeSourceResponse.model_validate(data)

    async def detach_knowledge_source(self, agent_id: str, connector_id: str) -> AgentKnowledgeSourceDetachResponse:
        data = await self._client.delete(f"agents/{agent_id}/knowledge-sources/{connector_id}")
        return AgentKnowledgeSourceDetachResponse.model_validate(data)

    async def attach_subagent(self, agent_id: str, subagent_id: str) -> AgentSubagentsResponse:
        data = await self._client.put(f"agents/{agent_id}/subagents/{subagent_id}")
        return AgentSubagentsResponse.model_validate(data)

    async def detach_subagent(self, agent_id: str, subagent_id: str) -> AgentSubagentsResponse:
        data = await self._client.delete(f"agents/{agent_id}/subagents/{subagent_id}")
        return AgentSubagentsResponse.model_validate(data)

    async def list_triggers(
        self,
        agent_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> AgentTriggersResponse:
        data = await self._client.get(f"agents/{agent_id}/triggers", params={"page_size": page_size, "cursor": cursor})
        return AgentTriggersResponse.model_validate(data)

    async def create_trigger(
        self,
        agent_id: str,
        request: AgentTriggerCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentTriggerResponse:
        """Create a ``schedule`` (``cron_expression`` or ``run_at``) or ``webhook`` trigger.
        A webhook's URL is returned here and from ``get_trigger_webhook_url``, never in lists."""
        data = await self._client.post(
            f"agents/{agent_id}/triggers", json=AgentTriggerCreateRequest.build(request, **kwargs)
        )
        return AgentTriggerResponse.model_validate(data)

    async def update_trigger(
        self,
        agent_id: str,
        trigger_id: str,
        request: AgentTriggerUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentTriggerResponse:
        data = await self._client.patch(
            f"agents/{agent_id}/triggers/{trigger_id}", json=AgentTriggerUpdateRequest.build(request, **kwargs)
        )
        return AgentTriggerResponse.model_validate(data)

    async def delete_trigger(self, agent_id: str, trigger_id: str) -> AgentTriggerDeleteResponse:
        data = await self._client.delete(f"agents/{agent_id}/triggers/{trigger_id}")
        return AgentTriggerDeleteResponse.model_validate(data)

    async def get_trigger_webhook_url(self, agent_id: str, trigger_id: str) -> AgentTriggerWebhookUrlResponse:
        data = await self._client.get(f"agents/{agent_id}/triggers/{trigger_id}/webhook-url")
        return AgentTriggerWebhookUrlResponse.model_validate(data)

    async def list_app_rules(self, agent_id: str) -> AgentAppRulesResponse:
        data = await self._client.get(f"agents/{agent_id}/app-rules")
        return AgentAppRulesResponse.model_validate(data)

    async def get_evaluation_options(self) -> AgentEvaluationOptionsResponse:
        data = await self._client.get("agents/evaluation-options")
        return AgentEvaluationOptionsResponse.model_validate(data)

    async def get_evaluation_config(self, agent_id: str) -> EvaluationConfigResponse:
        data = await self._client.get(f"agents/{agent_id}/evaluation-config")
        return EvaluationConfigResponse.model_validate(data)

    async def update_evaluation_config(
        self,
        agent_id: str,
        request: EvaluationConfigUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationConfigResponse:
        """Partially update the evaluation config. Only the fields you send are changed;
        omitted fields keep their current value. A provided list (criteria/tags/
        data_points) replaces that list wholesale."""
        data = await self._client.patch(
            f"agents/{agent_id}/evaluation-config",
            json=EvaluationConfigUpdateRequest.build(request, **kwargs),
        )
        return EvaluationConfigResponse.model_validate(data)

    async def list_evaluations(
        self,
        agent_id: str,
        *,
        grade: str | None = None,
        status: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        session_id: str | None = None,
        organization_evaluation_id: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> EvaluationResultListResponse:
        """Results from the agent's own evaluation by default; ``organization_evaluation_id`` selects the
        results one organization evaluation produced for this agent instead."""
        data = await self._client.get(
            f"agents/{agent_id}/evaluations",
            params={
                "grade": grade,
                "status": status,
                "created_after": created_after.isoformat() if created_after is not None else None,
                "created_before": created_before.isoformat() if created_before is not None else None,
                "session_id": session_id,
                "organization_evaluation_id": organization_evaluation_id,
                "page_size": page_size,
                "cursor": cursor,
                **kwargs,
            },
        )
        return EvaluationResultListResponse.model_validate(data)

    async def get_evaluation_metrics(self, agent_id: str, days: int = 30) -> AgentEvaluationMetricsResponse:
        data = await self._client.get(f"agents/{agent_id}/evaluations/metrics", params={"days": days})
        return AgentEvaluationMetricsResponse.model_validate(data)

    async def run_evaluations(
        self,
        agent_id: str,
        request: EvaluationRunRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationRunResponse:
        data = await self._client.post(
            f"agents/{agent_id}/evaluations/run", json=EvaluationRunRequest.build(request, **kwargs)
        )
        return EvaluationRunResponse.model_validate(data)

    async def get_evaluation(self, agent_id: str, evaluation_id: str) -> EvaluationResultResponse:
        data = await self._client.get(f"agents/{agent_id}/evaluations/{evaluation_id}")
        return EvaluationResultResponse.model_validate(data)


class AsyncModels:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self, **kwargs: Any) -> ModelListResponse:
        return ModelListResponse.model_validate(await self._client.get("models", params=kwargs))

    async def route(
        self,
        request: ModelRouteRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelRouteResponse:
        body = ModelRouteRequest.build(request, **kwargs)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        data = await self._client.post("models/route", json=body)
        return ModelRouteResponse.model_validate(data)
