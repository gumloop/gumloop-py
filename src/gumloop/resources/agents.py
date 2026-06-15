from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import AgentCreateRequest
from gumloop.types import AgentListResponse
from gumloop.types import AgentResponse
from gumloop.types import AgentUpdateRequest
from gumloop.types import EvaluationConfigResponse
from gumloop.types import EvaluationConfigUpdateRequest
from gumloop.types import EvaluationResultListResponse
from gumloop.types import EvaluationResultResponse
from gumloop.types import ModelListResponse


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
        return AgentResponse.model_validate(
            self._client.post("agents", json=AgentCreateRequest.build(request, **kwargs))
        )

    def retrieve(self, agent_id: str) -> AgentResponse:
        return AgentResponse.model_validate(self._client.get(f"agents/{agent_id}"))

    def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        return AgentResponse.model_validate(
            self._client.patch(f"agents/{agent_id}", json=AgentUpdateRequest.build(request, **kwargs))
        )

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
        data = await self._client.post("agents", json=AgentCreateRequest.build(request, **kwargs))
        return AgentResponse.model_validate(data)

    async def retrieve(self, agent_id: str) -> AgentResponse:
        return AgentResponse.model_validate(await self._client.get(f"agents/{agent_id}"))

    async def update(
        self,
        agent_id: str,
        request: AgentUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        data = await self._client.patch(f"agents/{agent_id}", json=AgentUpdateRequest.build(request, **kwargs))
        return AgentResponse.model_validate(data)

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
