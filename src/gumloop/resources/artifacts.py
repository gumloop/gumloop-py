from __future__ import annotations

from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import ArtifactDownloadResponse
from gumloop.types import ArtifactListResponse


class Artifacts:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(
        self,
        agent_id: str,
        *,
        session_id: str | None = None,
        search_query: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> ArtifactListResponse:
        return ArtifactListResponse.model_validate(
            self._client.get(
                f"agents/{agent_id}/artifacts",
                params={
                    "session_id": session_id,
                    "search_query": search_query,
                    "sort_order": sort_order,
                    "page_size": page_size,
                    "cursor": cursor,
                    **kwargs,
                },
            )
        )

    def download(
        self,
        artifact_id: str,
        *,
        version_id: str | None = None,
        **kwargs: Any,
    ) -> ArtifactDownloadResponse:
        return ArtifactDownloadResponse.model_validate(
            self._client.get(f"artifacts/{artifact_id}/download", params={"version_id": version_id, **kwargs})
        )


class AsyncArtifacts:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(
        self,
        agent_id: str,
        *,
        session_id: str | None = None,
        search_query: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> ArtifactListResponse:
        data = await self._client.get(
            f"agents/{agent_id}/artifacts",
            params={
                "session_id": session_id,
                "search_query": search_query,
                "sort_order": sort_order,
                "page_size": page_size,
                "cursor": cursor,
                **kwargs,
            },
        )
        return ArtifactListResponse.model_validate(data)

    async def download(
        self,
        artifact_id: str,
        *,
        version_id: str | None = None,
        **kwargs: Any,
    ) -> ArtifactDownloadResponse:
        data = await self._client.get(f"artifacts/{artifact_id}/download", params={"version_id": version_id, **kwargs})
        return ArtifactDownloadResponse.model_validate(data)
