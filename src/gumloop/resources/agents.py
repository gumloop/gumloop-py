from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import AgentCreateRequest
from gumloop.types import AgentListResponse
from gumloop.types import AgentMcpServerDetachResponse
from gumloop.types import AgentMcpServerResponse
from gumloop.types import AgentMcpServersResponse
from gumloop.types import AgentResponse
from gumloop.types import AgentSkillsResponse
from gumloop.types import AgentUpdateRequest
from gumloop.types import EvaluationConfigResponse
from gumloop.types import EvaluationConfigUpdateRequest
from gumloop.types import EvaluationResultListResponse
from gumloop.types import EvaluationResultResponse
from gumloop.types import ModelListResponse
from gumloop.types import SkillListResponse


def _skill_id_list(skill_ids: str | Sequence[str]) -> list[str]:
    return [skill_ids] if isinstance(skill_ids, str) else list(skill_ids)


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

    def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """``tools`` replaces the entire list when provided (legacy bulk path); prefer
        attach_mcp_server/detach_mcp_server for individual MCP servers and
        attach_skills/detach_skills for skills."""
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
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> EvaluationResultListResponse:
        return EvaluationResultListResponse.model_validate(
            self._client.get(
                f"agents/{agent_id}/evaluations",
                params={"grade": grade, "page_size": page_size, "cursor": cursor, **kwargs},
            )
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

    async def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """``tools`` replaces the entire list when provided (legacy bulk path); prefer
        attach_mcp_server/detach_mcp_server for individual MCP servers and
        attach_skills/detach_skills for skills."""
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
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> EvaluationResultListResponse:
        data = await self._client.get(
            f"agents/{agent_id}/evaluations",
            params={"grade": grade, "page_size": page_size, "cursor": cursor, **kwargs},
        )
        return EvaluationResultListResponse.model_validate(data)

    async def get_evaluation(self, agent_id: str, evaluation_id: str) -> EvaluationResultResponse:
        data = await self._client.get(f"agents/{agent_id}/evaluations/{evaluation_id}")
        return EvaluationResultResponse.model_validate(data)


class AsyncModels:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self, **kwargs: Any) -> ModelListResponse:
        return ModelListResponse.model_validate(await self._client.get("models", params=kwargs))
