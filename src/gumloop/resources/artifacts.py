from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.resources._item_access import item_access_body
from gumloop.types import ArtifactContent
from gumloop.types import ArtifactDeletedResponse
from gumloop.types import ArtifactDetails
from gumloop.types import ArtifactDownloadResponse
from gumloop.types import ArtifactHosting
from gumloop.types import ArtifactListResponse
from gumloop.types import ArtifactNameResponse
from gumloop.types import ArtifactPasswordResponse
from gumloop.types import ArtifactRestoreResponse
from gumloop.types import ArtifactVersionsResponse
from gumloop.types import ItemAccessChangeResponse
from gumloop.types import ItemAccessResponse


class Artifacts:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def retrieve(self, artifact_id: str, *, version_id: str | None = None) -> ArtifactDetails:
        return ArtifactDetails.model_validate(
            self._client.get(f"artifacts/{artifact_id}", params={"version_id": version_id})
        )

    def content(
        self, artifact_id: str, *, version_id: str | None = None, max_bytes: int = 64 * 1024 * 1024
    ) -> ArtifactContent:
        content, headers = self._client.get_bytes(
            f"artifacts/{artifact_id}/content", params={"version_id": version_id}, max_bytes=max_bytes
        )
        return ArtifactContent(content=content, media_type=headers.get("Content-Type"))

    def delete(self, artifact_id: str) -> ArtifactDeletedResponse:
        return ArtifactDeletedResponse.model_validate(self._client.delete(f"artifacts/{artifact_id}"))

    def rename(self, artifact_id: str, name: str | None) -> ArtifactNameResponse:
        """Change the display name; None resets it without changing the stored filename."""
        return ArtifactNameResponse.model_validate(
            self._client.put(f"artifacts/{artifact_id}/name", json={"name": name})
        )

    def list_versions(self, artifact_id: str) -> ArtifactVersionsResponse:
        return ArtifactVersionsResponse.model_validate(self._client.get(f"artifacts/{artifact_id}/versions"))

    def restore(self, artifact_id: str, version_id: str) -> ArtifactRestoreResponse:
        """Queue append-only restore for a VFS handle; legacy files do not support restore."""
        return ArtifactRestoreResponse.model_validate(
            self._client.post(f"artifacts/{artifact_id}/restore", json={"version_id": version_id})
        )

    def get_hosting(self, artifact_id: str) -> ArtifactHosting:
        return ArtifactHosting.model_validate(self._client.get(f"artifacts/{artifact_id}/hosting"))

    def enable_hosting(self, artifact_id: str, *, alias: str | None = None) -> ArtifactHosting:
        return ArtifactHosting.model_validate(
            self._client.post(f"artifacts/{artifact_id}/hosting", json={"alias": alias})
        )

    def rename_hosting(self, artifact_id: str, alias: str) -> ArtifactHosting:
        return ArtifactHosting.model_validate(
            self._client.put(f"artifacts/{artifact_id}/hosting", json={"alias": alias})
        )

    def disable_hosting(self, artifact_id: str) -> ArtifactHosting:
        return ArtifactHosting.model_validate(self._client.delete(f"artifacts/{artifact_id}/hosting"))

    def acknowledge_integrations(self, artifact_id: str, version_id: str) -> None:
        """Record explicit per-version consent; requires personal key or OAuth."""
        self._client.post(
            f"artifacts/{artifact_id}/acknowledgements", json={"ack_type": "integrations", "version_id": version_id}
        )

    def execute_script(self, artifact_id: str, key: str, *, payload: Any = None, version_id: str | None = None) -> Any:
        """Run a declared script with current credential rules, consent, and billing."""
        return self._client.post(
            f"artifacts/{artifact_id}/execute",
            params={"version_id": version_id},
            json={"key": key, "payload": payload, "download": False},
        )

    def download_script(
        self,
        artifact_id: str,
        key: str,
        *,
        payload: Any = None,
        version_id: str | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> ArtifactContent:
        content, headers = self._client.post_bytes(
            f"artifacts/{artifact_id}/execute",
            params={"version_id": version_id, "team_id": self._client.team_id},
            json={"key": key, "payload": payload, "download": True},
            max_bytes=max_bytes,
        )
        return ArtifactContent(content=content, media_type=headers.get("Content-Type"))

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

    async def retrieve(self, artifact_id: str, *, version_id: str | None = None) -> ArtifactDetails:
        return ArtifactDetails.model_validate(
            await self._client.get(f"artifacts/{artifact_id}", params={"version_id": version_id})
        )

    async def content(
        self, artifact_id: str, *, version_id: str | None = None, max_bytes: int = 64 * 1024 * 1024
    ) -> ArtifactContent:
        content, headers = await self._client.get_bytes(
            f"artifacts/{artifact_id}/content", params={"version_id": version_id}, max_bytes=max_bytes
        )
        return ArtifactContent(content=content, media_type=headers.get("Content-Type"))

    async def delete(self, artifact_id: str) -> ArtifactDeletedResponse:
        return ArtifactDeletedResponse.model_validate(await self._client.delete(f"artifacts/{artifact_id}"))

    async def rename(self, artifact_id: str, name: str | None) -> ArtifactNameResponse:
        """Change the display name; None resets it without changing the stored filename."""
        return ArtifactNameResponse.model_validate(
            await self._client.put(f"artifacts/{artifact_id}/name", json={"name": name})
        )

    async def list_versions(self, artifact_id: str) -> ArtifactVersionsResponse:
        return ArtifactVersionsResponse.model_validate(await self._client.get(f"artifacts/{artifact_id}/versions"))

    async def restore(self, artifact_id: str, version_id: str) -> ArtifactRestoreResponse:
        """Queue append-only restore for a VFS handle; legacy files do not support restore."""
        return ArtifactRestoreResponse.model_validate(
            await self._client.post(f"artifacts/{artifact_id}/restore", json={"version_id": version_id})
        )

    async def get_hosting(self, artifact_id: str) -> ArtifactHosting:
        return ArtifactHosting.model_validate(await self._client.get(f"artifacts/{artifact_id}/hosting"))

    async def enable_hosting(self, artifact_id: str, *, alias: str | None = None) -> ArtifactHosting:
        return ArtifactHosting.model_validate(
            await self._client.post(f"artifacts/{artifact_id}/hosting", json={"alias": alias})
        )

    async def rename_hosting(self, artifact_id: str, alias: str) -> ArtifactHosting:
        return ArtifactHosting.model_validate(
            await self._client.put(f"artifacts/{artifact_id}/hosting", json={"alias": alias})
        )

    async def disable_hosting(self, artifact_id: str) -> ArtifactHosting:
        return ArtifactHosting.model_validate(await self._client.delete(f"artifacts/{artifact_id}/hosting"))

    async def acknowledge_integrations(self, artifact_id: str, version_id: str) -> None:
        """Record explicit per-version consent; requires personal key or OAuth."""
        await self._client.post(
            f"artifacts/{artifact_id}/acknowledgements", json={"ack_type": "integrations", "version_id": version_id}
        )

    async def execute_script(
        self, artifact_id: str, key: str, *, payload: Any = None, version_id: str | None = None
    ) -> Any:
        """Run a declared script with current credential rules, consent, and billing."""
        return await self._client.post(
            f"artifacts/{artifact_id}/execute",
            params={"version_id": version_id},
            json={"key": key, "payload": payload, "download": False},
        )

    async def download_script(
        self,
        artifact_id: str,
        key: str,
        *,
        payload: Any = None,
        version_id: str | None = None,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> ArtifactContent:
        content, headers = await self._client.post_bytes(
            f"artifacts/{artifact_id}/execute",
            params={"version_id": version_id, "team_id": self._client.team_id},
            json={"key": key, "payload": payload, "download": True},
            max_bytes=max_bytes,
        )
        return ArtifactContent(content=content, media_type=headers.get("Content-Type"))

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
