from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop._http import UploadFile
from gumloop._http import multipart_files
from gumloop.types import BrainFileDeleteResponse
from gumloop.types import BrainFileListResponse
from gumloop.types import BrainFileUploadResponse
from gumloop.types import BrainSearchRequest
from gumloop.types import BrainSearchResponse
from gumloop.types import BrainSourceCreateRequest
from gumloop.types import BrainSourceDeleteResponse
from gumloop.types import BrainSourceEstimateResponse
from gumloop.types import BrainSourceListResponse
from gumloop.types import BrainSourceResponse


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
        **kwargs: Any,
    ) -> BrainSourceResponse:
        return BrainSourceResponse.model_validate(
            self._client.post(
                "brain/sources",
                json=BrainSourceCreateRequest.build(
                    name=name, scope=scope, team_id=team_id, require_approval=require_approval, **kwargs
                ),
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
        **kwargs: Any,
    ) -> BrainSourceResponse:
        data = await self._client.post(
            "brain/sources",
            json=BrainSourceCreateRequest.build(
                name=name, scope=scope, team_id=team_id, require_approval=require_approval, **kwargs
            ),
        )
        return BrainSourceResponse.model_validate(data)

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
