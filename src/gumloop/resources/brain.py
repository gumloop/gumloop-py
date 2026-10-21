from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop._http import UploadFile
from gumloop._http import multipart_files
from gumloop.types import BrainBrowseRequest
from gumloop.types import BrainBrowseResponse
from gumloop.types import BrainFileDeleteResponse
from gumloop.types import BrainFileListResponse
from gumloop.types import BrainFileUploadResponse
from gumloop.types import BrainSearchRequest
from gumloop.types import BrainSearchResponse
from gumloop.types import BrainSourceChildrenResponse
from gumloop.types import BrainSourceConfiguration
from gumloop.types import BrainSourceCreateRequest
from gumloop.types import BrainSourceDeleteResponse
from gumloop.types import BrainSourceEstimateResponse
from gumloop.types import BrainSourceHistoryResponse
from gumloop.types import BrainSourceIssuesResponse
from gumloop.types import BrainSourceListResponse
from gumloop.types import BrainSourceResponse
from gumloop.types import BrainSourceSyncResponse
from gumloop.types import BrainSourceUpdateRequest


class Brain:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        source_type: list[str] | None = None,
        **kwargs: Any,
    ) -> BrainSearchResponse:
        return BrainSearchResponse.model_validate(
            self._client.post(
                "brain/search",
                json=BrainSearchRequest.build(query=query, limit=limit, source_type=source_type, **kwargs),
            )
        )

    def list_sources(
        self,
        *,
        source_type: str | None = None,
        scope: str | None = None,
        team_id: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> BrainSourceListResponse:
        return BrainSourceListResponse.model_validate(
            self._client.get(
                "brain/sources",
                params={
                    "source_type": source_type,
                    "scope": scope,
                    "team_id": team_id,
                    "page_size": page_size,
                    "cursor": cursor,
                    **kwargs,
                },
            )
        )

    def create_source(
        self,
        name: str,
        *,
        scope: str | None = None,
        team_id: str | None = None,
        require_approval: bool | None = None,
        source_type: str | None = None,
        config: Mapping[str, Any] | None = None,
        credentials_to_use: Mapping[str, Any] | None = None,
        credential_name: str | None = None,
        respect_source_permissions: bool | None = None,
        **kwargs: Any,
    ) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            self._client.post(
                "brain/sources",
                json=BrainSourceCreateRequest.build(
                    name=name,
                    scope=scope,
                    team_id=team_id,
                    require_approval=require_approval,
                    source_type=source_type,
                    config=config,
                    credentials_to_use=credentials_to_use,
                    credential_name=credential_name,
                    respect_source_permissions=respect_source_permissions,
                    **kwargs,
                ),
            )
        )

    def get_source_configuration(self, source_id: str) -> BrainSourceConfiguration:
        """Read editable settings and credential selectors; requires source management permission."""
        return BrainSourceConfiguration.model_validate(self._client.get(f"brain/sources/{source_id}/configuration"))

    def update_source(
        self,
        source_id: str,
        *,
        name: str | None = None,
        config: Mapping[str, Any] | None = None,
        credentials_to_use: Mapping[str, Any] | None = None,
        respect_source_permissions: bool | None = None,
        scope: str | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            self._client.patch(
                f"brain/sources/{source_id}",
                json=BrainSourceUpdateRequest.build(
                    name=name,
                    config=config,
                    credentials_to_use=credentials_to_use,
                    respect_source_permissions=respect_source_permissions,
                    scope=scope,
                    team_id=team_id,
                    **kwargs,
                ),
            )
        )

    def browse_source(
        self,
        source_type: str,
        *,
        credentials_to_use: Mapping[str, Any] | None = None,
        scope: str | None = None,
        team_id: str | None = None,
        roots: bool | None = None,
        root_id: str | None = None,
        parent_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        query: str | None = None,
        **kwargs: Any,
    ) -> BrainBrowseResponse:
        """Browse a connected account or internal source using verified setup and scope rules."""
        return BrainBrowseResponse.model_validate(
            self._client.post(
                "brain/sources/browse",
                json=BrainBrowseRequest.build(
                    source_type=source_type,
                    credentials_to_use=credentials_to_use,
                    scope=scope,
                    team_id=team_id,
                    roots=roots,
                    root_id=root_id,
                    parent_id=parent_id,
                    cursor=cursor,
                    limit=limit,
                    query=query,
                    **kwargs,
                ),
            )
        )

    def sync_source(self, source_id: str) -> BrainSourceSyncResponse:
        """Request sync or retry setup; draft sources remain behind their estimate approval gate."""
        return BrainSourceSyncResponse.model_validate(self._client.post(f"brain/sources/{source_id}/sync"))

    def pause_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            self._client.patch(f"brain/sources/{source_id}/status", json={"status": "paused"})
        )

    def resume_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            self._client.patch(f"brain/sources/{source_id}/status", json={"status": "active"})
        )

    def list_sync_runs(
        self, source_id: str, *, page_size: int | None = None, cursor: str | None = None
    ) -> BrainSourceHistoryResponse:
        return BrainSourceHistoryResponse.model_validate(
            self._client.get(f"brain/sources/{source_id}/sync-runs", params={"page_size": page_size, "cursor": cursor})
        )

    def list_source_issues(
        self, source_id: str, *, page_size: int | None = None, cursor: str | None = None
    ) -> BrainSourceIssuesResponse:
        return BrainSourceIssuesResponse.model_validate(
            self._client.get(f"brain/sources/{source_id}/issues", params={"page_size": page_size, "cursor": cursor})
        )

    def list_source_children(
        self,
        source_id: str,
        *,
        parent_id: str | None = None,
        query: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> BrainSourceChildrenResponse:
        return BrainSourceChildrenResponse.model_validate(
            self._client.get(
                f"brain/sources/{source_id}/children",
                params={"parent_id": parent_id, "query": query, "page_size": page_size, "cursor": cursor},
            )
        )

    def get_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(self._client.get(f"brain/sources/{source_id}"))

    def delete_source(self, source_id: str) -> BrainSourceDeleteResponse:
        return BrainSourceDeleteResponse.model_validate(self._client.delete(f"brain/sources/{source_id}"))

    def get_estimate(self, source_id: str) -> BrainSourceEstimateResponse:
        return BrainSourceEstimateResponse.model_validate(self._client.get(f"brain/sources/{source_id}/estimate"))

    def approve_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(self._client.post(f"brain/sources/{source_id}/approve"))

    def list_files(
        self,
        source_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> BrainFileListResponse:
        return BrainFileListResponse.model_validate(
            self._client.get(
                f"brain/sources/{source_id}/files", params={"page_size": page_size, "cursor": cursor, **kwargs}
            )
        )

    def upload_files(
        self,
        source_id: str,
        files: Mapping[str, bytes | str] | list[UploadFile],
    ) -> BrainFileUploadResponse:
        return BrainFileUploadResponse.model_validate(
            self._client.post(f"brain/sources/{source_id}/files", files=multipart_files(files))
        )

    def delete_file(self, source_id: str, file_id: str) -> BrainFileDeleteResponse:
        return BrainFileDeleteResponse.model_validate(self._client.delete(f"brain/sources/{source_id}/files/{file_id}"))


class AsyncBrain:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        source_type: list[str] | None = None,
        **kwargs: Any,
    ) -> BrainSearchResponse:
        data = await self._client.post(
            "brain/search",
            json=BrainSearchRequest.build(query=query, limit=limit, source_type=source_type, **kwargs),
        )
        return BrainSearchResponse.model_validate(data)

    async def list_sources(
        self,
        *,
        source_type: str | None = None,
        scope: str | None = None,
        team_id: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> BrainSourceListResponse:
        data = await self._client.get(
            "brain/sources",
            params={
                "source_type": source_type,
                "scope": scope,
                "team_id": team_id,
                "page_size": page_size,
                "cursor": cursor,
                **kwargs,
            },
        )
        return BrainSourceListResponse.model_validate(data)

    async def create_source(
        self,
        name: str,
        *,
        scope: str | None = None,
        team_id: str | None = None,
        require_approval: bool | None = None,
        source_type: str | None = None,
        config: Mapping[str, Any] | None = None,
        credentials_to_use: Mapping[str, Any] | None = None,
        credential_name: str | None = None,
        respect_source_permissions: bool | None = None,
        **kwargs: Any,
    ) -> BrainSourceResponse:
        data = await self._client.post(
            "brain/sources",
            json=BrainSourceCreateRequest.build(
                name=name,
                scope=scope,
                team_id=team_id,
                require_approval=require_approval,
                source_type=source_type,
                config=config,
                credentials_to_use=credentials_to_use,
                credential_name=credential_name,
                respect_source_permissions=respect_source_permissions,
                **kwargs,
            ),
        )
        return BrainSourceResponse.model_validate(data)

    async def get_source_configuration(self, source_id: str) -> BrainSourceConfiguration:
        """Read editable settings and credential selectors; requires source management permission."""
        return BrainSourceConfiguration.model_validate(
            await self._client.get(f"brain/sources/{source_id}/configuration")
        )

    async def update_source(
        self,
        source_id: str,
        *,
        name: str | None = None,
        config: Mapping[str, Any] | None = None,
        credentials_to_use: Mapping[str, Any] | None = None,
        respect_source_permissions: bool | None = None,
        scope: str | None = None,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            await self._client.patch(
                f"brain/sources/{source_id}",
                json=BrainSourceUpdateRequest.build(
                    name=name,
                    config=config,
                    credentials_to_use=credentials_to_use,
                    respect_source_permissions=respect_source_permissions,
                    scope=scope,
                    team_id=team_id,
                    **kwargs,
                ),
            )
        )

    async def browse_source(
        self,
        source_type: str,
        *,
        credentials_to_use: Mapping[str, Any] | None = None,
        scope: str | None = None,
        team_id: str | None = None,
        roots: bool | None = None,
        root_id: str | None = None,
        parent_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        query: str | None = None,
        **kwargs: Any,
    ) -> BrainBrowseResponse:
        """Browse a connected account or internal source using verified setup and scope rules."""
        return BrainBrowseResponse.model_validate(
            await self._client.post(
                "brain/sources/browse",
                json=BrainBrowseRequest.build(
                    source_type=source_type,
                    credentials_to_use=credentials_to_use,
                    scope=scope,
                    team_id=team_id,
                    roots=roots,
                    root_id=root_id,
                    parent_id=parent_id,
                    cursor=cursor,
                    limit=limit,
                    query=query,
                    **kwargs,
                ),
            )
        )

    async def sync_source(self, source_id: str) -> BrainSourceSyncResponse:
        """Request sync or retry setup; draft sources remain behind their estimate approval gate."""
        return BrainSourceSyncResponse.model_validate(await self._client.post(f"brain/sources/{source_id}/sync"))

    async def pause_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            await self._client.patch(f"brain/sources/{source_id}/status", json={"status": "paused"})
        )

    async def resume_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            await self._client.patch(f"brain/sources/{source_id}/status", json={"status": "active"})
        )

    async def list_sync_runs(
        self, source_id: str, *, page_size: int | None = None, cursor: str | None = None
    ) -> BrainSourceHistoryResponse:
        return BrainSourceHistoryResponse.model_validate(
            await self._client.get(
                f"brain/sources/{source_id}/sync-runs", params={"page_size": page_size, "cursor": cursor}
            )
        )

    async def list_source_issues(
        self, source_id: str, *, page_size: int | None = None, cursor: str | None = None
    ) -> BrainSourceIssuesResponse:
        return BrainSourceIssuesResponse.model_validate(
            await self._client.get(
                f"brain/sources/{source_id}/issues", params={"page_size": page_size, "cursor": cursor}
            )
        )

    async def list_source_children(
        self,
        source_id: str,
        *,
        parent_id: str | None = None,
        query: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> BrainSourceChildrenResponse:
        return BrainSourceChildrenResponse.model_validate(
            await self._client.get(
                f"brain/sources/{source_id}/children",
                params={"parent_id": parent_id, "query": query, "page_size": page_size, "cursor": cursor},
            )
        )

    async def get_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(await self._client.get(f"brain/sources/{source_id}"))

    async def delete_source(self, source_id: str) -> BrainSourceDeleteResponse:
        return BrainSourceDeleteResponse.model_validate(await self._client.delete(f"brain/sources/{source_id}"))

    async def get_estimate(self, source_id: str) -> BrainSourceEstimateResponse:
        data = await self._client.get(f"brain/sources/{source_id}/estimate")
        return BrainSourceEstimateResponse.model_validate(data)

    async def approve_source(self, source_id: str) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(await self._client.post(f"brain/sources/{source_id}/approve"))

    async def list_files(
        self,
        source_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> BrainFileListResponse:
        data = await self._client.get(
            f"brain/sources/{source_id}/files", params={"page_size": page_size, "cursor": cursor, **kwargs}
        )
        return BrainFileListResponse.model_validate(data)

    async def upload_files(
        self,
        source_id: str,
        files: Mapping[str, bytes | str] | list[UploadFile],
    ) -> BrainFileUploadResponse:
        data = await self._client.post(f"brain/sources/{source_id}/files", files=multipart_files(files))
        return BrainFileUploadResponse.model_validate(data)

    async def delete_file(self, source_id: str, file_id: str) -> BrainFileDeleteResponse:
        data = await self._client.delete(f"brain/sources/{source_id}/files/{file_id}")
        return BrainFileDeleteResponse.model_validate(data)
