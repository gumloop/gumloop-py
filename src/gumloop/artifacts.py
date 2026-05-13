from __future__ import annotations

from typing import Any

from gumloop.types import ArtifactDownloadResponse
from gumloop.types import ArtifactListResponse


def _params(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


class Artifacts:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        agent_id: str,
        *,
        interaction_id: str | None = None,
        search_query: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> ArtifactListResponse:
        params = _params(
            interaction_id=interaction_id,
            search_query=search_query,
            sort_order=sort_order,
            page_size=page_size,
            cursor=cursor,
            **kwargs,
        )
        return self._client._request_json("GET", f"agents/{agent_id}/artifacts", params=params)

    def download(self, artifact_id: str, *, version_id: str | None = None, **kwargs: Any) -> ArtifactDownloadResponse:
        params = _params(version_id=version_id, **kwargs)
        return self._client._request_json("GET", f"artifacts/{artifact_id}/download", params=params)


class AsyncArtifacts:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def list(
        self,
        agent_id: str,
        *,
        interaction_id: str | None = None,
        search_query: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> ArtifactListResponse:
        params = _params(
            interaction_id=interaction_id,
            search_query=search_query,
            sort_order=sort_order,
            page_size=page_size,
            cursor=cursor,
            **kwargs,
        )
        return await self._client._request_json("GET", f"agents/{agent_id}/artifacts", params=params)

    async def download(
        self, artifact_id: str, *, version_id: str | None = None, **kwargs: Any
    ) -> ArtifactDownloadResponse:
        params = _params(version_id=version_id, **kwargs)
        return await self._client._request_json("GET", f"artifacts/{artifact_id}/download", params=params)
