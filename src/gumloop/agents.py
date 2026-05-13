from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop.types import AgentCreateRequest
from gumloop.types import AgentListResponse
from gumloop.types import AgentResponse
from gumloop.types import AgentUpdateRequest
from gumloop.types import ModelListResponse


def _body(request: Mapping[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
    data = dict(request or {})
    data.update({key: value for key, value in fields.items() if value is not None})
    return data


class Agents:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, *, search: str | None = None, team_id: str | None = None, **kwargs: Any) -> AgentListResponse:
        params = _body(search=search or None, team_id=team_id, **kwargs)
        return self._client._request_json("GET", "agents", params=params)

    def create(
        self,
        request: AgentCreateRequest | None = None,
        *,
        name: str | None = None,
        model_name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        folder_id: str | None = None,
        is_active: bool | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        body = _body(
            request,
            name=name,
            model_name=model_name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            resources=resources,
            metadata=metadata,
            folder_id=folder_id,
            is_active=is_active,
            agent_id=agent_id,
            team_id=team_id,
            **kwargs,
        )
        return self._client._request_json("POST", "agents", json=body)

    def retrieve(self, agent_id: str) -> AgentResponse:
        return self._client._request_json("GET", f"agents/{agent_id}")

    def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | None = None,
        *,
        name: str | None = None,
        model_name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        is_active: bool | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        body = _body(
            request,
            name=name,
            model_name=model_name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            resources=resources,
            metadata=metadata,
            is_active=is_active,
            team_id=team_id,
            **kwargs,
        )
        return self._client._request_json("PATCH", f"agents/{agent_id}", json=body)


class Models:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, **kwargs: Any) -> ModelListResponse:
        params = _body(**kwargs)
        return self._client._request_json("GET", "models", params=params)


class AsyncAgents:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def list(self, *, search: str | None = None, team_id: str | None = None, **kwargs: Any) -> AgentListResponse:
        params = _body(search=search or None, team_id=team_id, **kwargs)
        return await self._client._request_json("GET", "agents", params=params)

    async def create(
        self,
        request: AgentCreateRequest | None = None,
        *,
        name: str | None = None,
        model_name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        folder_id: str | None = None,
        is_active: bool | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        body = _body(
            request,
            name=name,
            model_name=model_name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            resources=resources,
            metadata=metadata,
            folder_id=folder_id,
            is_active=is_active,
            agent_id=agent_id,
            team_id=team_id,
            **kwargs,
        )
        return await self._client._request_json("POST", "agents", json=body)

    async def retrieve(self, agent_id: str) -> AgentResponse:
        return await self._client._request_json("GET", f"agents/{agent_id}")

    async def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | None = None,
        *,
        name: str | None = None,
        model_name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        resources: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        is_active: bool | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        body = _body(
            request,
            name=name,
            model_name=model_name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            resources=resources,
            metadata=metadata,
            is_active=is_active,
            team_id=team_id,
            **kwargs,
        )
        return await self._client._request_json("PATCH", f"agents/{agent_id}", json=body)


class AsyncModels:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def list(self, **kwargs: Any) -> ModelListResponse:
        params = _body(**kwargs)
        return await self._client._request_json("GET", "models", params=params)
