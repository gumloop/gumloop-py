from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.resources._item_access import item_access_body
from gumloop.types import ArtifactDownloadResponse
from gumloop.types import ArtifactListResponse
from gumloop.types import ArtifactPasswordResponse
from gumloop.types import ItemAccessChangeResponse
from gumloop.types import ItemAccessResponse


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

    def get_access(self, artifact_id: str) -> ItemAccessResponse:
        return ItemAccessResponse.model_validate(self._client.get(f"artifacts/{artifact_id}/access"))

    def update_access(
        self,
        artifact_id: str,
        *,
        share: Sequence[Mapping[str, Any]] | None = None,
        remove: Sequence[Mapping[str, Any]] | None = None,
        link: Mapping[str, Any] | None = None,
    ) -> ItemAccessChangeResponse:
        return ItemAccessChangeResponse.model_validate(
            self._client.put(
                f"artifacts/{artifact_id}/access",
                json=item_access_body(share=share, remove=remove, link=link),
            )
        )

    def set_password(self, artifact_id: str, password: str) -> ArtifactPasswordResponse:
        return ArtifactPasswordResponse.model_validate(
            self._client.put(f"artifacts/{artifact_id}/password", json={"password": password})
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

    async def get_access(self, artifact_id: str) -> ItemAccessResponse:
        return ItemAccessResponse.model_validate(await self._client.get(f"artifacts/{artifact_id}/access"))

    async def update_access(
        self,
        artifact_id: str,
        *,
        share: Sequence[Mapping[str, Any]] | None = None,
        remove: Sequence[Mapping[str, Any]] | None = None,
        link: Mapping[str, Any] | None = None,
    ) -> ItemAccessChangeResponse:
        data = await self._client.put(
            f"artifacts/{artifact_id}/access",
            json=item_access_body(share=share, remove=remove, link=link),
        )
        return ItemAccessChangeResponse.model_validate(data)

    async def set_password(self, artifact_id: str, password: str) -> ArtifactPasswordResponse:
        data = await self._client.put(f"artifacts/{artifact_id}/password", json={"password": password})
        return ArtifactPasswordResponse.model_validate(data)
