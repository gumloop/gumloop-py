from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import EvaluationCreateRequest
from gumloop.types import EvaluationListResponse
from gumloop.types import EvaluationMetricsResponse
from gumloop.types import EvaluationResponse
from gumloop.types import EvaluationResultRecordListResponse
from gumloop.types import EvaluationResultRecordResponse
from gumloop.types import EvaluationRunResponse
from gumloop.types import EvaluationTarget
from gumloop.types import EvaluationTargetsResponse
from gumloop.types import EvaluationUpdateRequest


def _session_id_list(session_ids: str | Sequence[str]) -> list[str]:
    return [session_ids] if isinstance(session_ids, str) else list(session_ids)


def _target_dicts(targets: Sequence[EvaluationTarget | Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [EvaluationTarget.build(target) for target in targets]


def _results_params(
    *,
    agent_id: str | None,
    session_id: str | None,
    grade: str | None,
    status: str | None,
    created_after: str | None,
    created_before: str | None,
    page_size: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "session_id": session_id,
        "grade": grade,
        "status": status,
        "created_after": created_after,
        "created_before": created_before,
        "page_size": page_size,
        "cursor": cursor,
    }


class Evaluations:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def options(self) -> dict[str, Any]:
        return self._client.get("evaluation-options")

    def list(
        self,
        organization_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> EvaluationListResponse:
        return EvaluationListResponse.model_validate(
            self._client.get(
                "evaluations",
                params={"organization_id": organization_id, "page_size": page_size, "cursor": cursor},
            )
        )

    def create(
        self,
        request: EvaluationCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationResponse:
        """A new evaluation cannot start enabled: set targets first, then ``update(enabled=True)``."""
        return EvaluationResponse.model_validate(
            self._client.post("evaluations", json=EvaluationCreateRequest.build(request, **kwargs))
        )

    def retrieve(self, evaluation_id: str) -> EvaluationResponse:
        return EvaluationResponse.model_validate(self._client.get(f"evaluations/{evaluation_id}"))

    def update(
        self,
        evaluation_id: str,
        request: EvaluationUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationResponse:
        """Only the fields you send change. A provided ``config`` list (criteria/tags/data_points)
        replaces that list wholesale; ``description=None`` is ignored, pass ``""`` to clear it."""
        return EvaluationResponse.model_validate(
            self._client.patch(f"evaluations/{evaluation_id}", json=EvaluationUpdateRequest.build(request, **kwargs))
        )

    def delete(self, evaluation_id: str) -> None:
        self._client.delete(f"evaluations/{evaluation_id}")

    def set_targets(
        self,
        evaluation_id: str,
        targets: Sequence[EvaluationTarget | Mapping[str, Any]],
    ) -> EvaluationTargetsResponse:
        """Replaces the whole target set. Removing the last target pauses an enabled evaluation."""
        return EvaluationTargetsResponse.model_validate(
            self._client.put(f"evaluations/{evaluation_id}/targets", json={"targets": _target_dicts(targets)})
        )

    def run(
        self,
        evaluation_id: str,
        session_ids: str | Sequence[str],
        *,
        dry_run: bool = False,
    ) -> EvaluationRunResponse:
        """Queue the evaluation over existing sessions of covered agents. Each queued result id can be
        polled with :meth:`get_result`; ``dry_run`` reports the credit cost without queuing."""
        return EvaluationRunResponse.model_validate(
            self._client.post(
                f"evaluations/{evaluation_id}/run",
                json={"session_ids": _session_id_list(session_ids), "dry_run": dry_run},
            )
        )

    def list_results(
        self,
        evaluation_id: str,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> EvaluationResultRecordListResponse:
        return EvaluationResultRecordListResponse.model_validate(
            self._client.get(
                f"evaluations/{evaluation_id}/results",
                params=_results_params(
                    agent_id=agent_id,
                    session_id=session_id,
                    grade=grade,
                    status=status,
                    created_after=created_after,
                    created_before=created_before,
                    page_size=page_size,
                    cursor=cursor,
                ),
            )
        )

    def get_result(self, evaluation_id: str, result_id: str) -> EvaluationResultRecordResponse:
        return EvaluationResultRecordResponse.model_validate(
            self._client.get(f"evaluations/{evaluation_id}/results/{result_id}")
        )

    def metrics(self, evaluation_id: str, *, days: int | None = None) -> EvaluationMetricsResponse:
        return EvaluationMetricsResponse.model_validate(
            self._client.get(f"evaluations/{evaluation_id}/metrics", params={"days": days})
        )


class AsyncEvaluations:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def options(self) -> dict[str, Any]:
        return await self._client.get("evaluation-options")

    async def list(
        self,
        organization_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> EvaluationListResponse:
        data = await self._client.get(
            "evaluations",
            params={"organization_id": organization_id, "page_size": page_size, "cursor": cursor},
        )
        return EvaluationListResponse.model_validate(data)

    async def create(
        self,
        request: EvaluationCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationResponse:
        """A new evaluation cannot start enabled: set targets first, then ``update(enabled=True)``."""
        data = await self._client.post("evaluations", json=EvaluationCreateRequest.build(request, **kwargs))
        return EvaluationResponse.model_validate(data)

    async def retrieve(self, evaluation_id: str) -> EvaluationResponse:
        return EvaluationResponse.model_validate(await self._client.get(f"evaluations/{evaluation_id}"))

    async def update(
        self,
        evaluation_id: str,
        request: EvaluationUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> EvaluationResponse:
        """Only the fields you send change. A provided ``config`` list (criteria/tags/data_points)
        replaces that list wholesale; ``description=None`` is ignored, pass ``""`` to clear it."""
        data = await self._client.patch(
            f"evaluations/{evaluation_id}", json=EvaluationUpdateRequest.build(request, **kwargs)
        )
        return EvaluationResponse.model_validate(data)

    async def delete(self, evaluation_id: str) -> None:
        await self._client.delete(f"evaluations/{evaluation_id}")

    async def set_targets(
        self,
        evaluation_id: str,
        targets: Sequence[EvaluationTarget | Mapping[str, Any]],
    ) -> EvaluationTargetsResponse:
        """Replaces the whole target set. Removing the last target pauses an enabled evaluation."""
        data = await self._client.put(f"evaluations/{evaluation_id}/targets", json={"targets": _target_dicts(targets)})
        return EvaluationTargetsResponse.model_validate(data)

    async def run(
        self,
        evaluation_id: str,
        session_ids: str | Sequence[str],
        *,
        dry_run: bool = False,
    ) -> EvaluationRunResponse:
        """Queue the evaluation over existing sessions of covered agents. Each queued result id can be
        polled with :meth:`get_result`; ``dry_run`` reports the credit cost without queuing."""
        data = await self._client.post(
            f"evaluations/{evaluation_id}/run",
            json={"session_ids": _session_id_list(session_ids), "dry_run": dry_run},
        )
        return EvaluationRunResponse.model_validate(data)

    async def list_results(
        self,
        evaluation_id: str,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> EvaluationResultRecordListResponse:
        data = await self._client.get(
            f"evaluations/{evaluation_id}/results",
            params=_results_params(
                agent_id=agent_id,
                session_id=session_id,
                grade=grade,
                status=status,
                created_after=created_after,
                created_before=created_before,
                page_size=page_size,
                cursor=cursor,
            ),
        )
        return EvaluationResultRecordListResponse.model_validate(data)

    async def get_result(self, evaluation_id: str, result_id: str) -> EvaluationResultRecordResponse:
        data = await self._client.get(f"evaluations/{evaluation_id}/results/{result_id}")
        return EvaluationResultRecordResponse.model_validate(data)

    async def metrics(self, evaluation_id: str, *, days: int | None = None) -> EvaluationMetricsResponse:
        data = await self._client.get(f"evaluations/{evaluation_id}/metrics", params={"days": days})
        return EvaluationMetricsResponse.model_validate(data)
