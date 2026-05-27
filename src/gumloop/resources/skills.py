from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import SkillDeleteResponse
from gumloop.types import SkillDownloadResponse
from gumloop.types import SkillListResponse
from gumloop.types import SkillResponse

SkillFile = tuple[str, bytes | str] | tuple[str, bytes | str, str]


def _multipart_files(files: Mapping[str, bytes | str] | list[SkillFile]) -> list[tuple[str, Any]]:
    items = files.items() if isinstance(files, Mapping) else files
    multipart = []
    for item in items:
        filename, content, *rest = item
        media_type = rest[0] if rest else "application/octet-stream"
        multipart.append(("files", (filename, content, media_type)))
    return multipart


class Skills:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(
        self,
        *,
        team_id: str | None = None,
        search_query: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        creator_user_id: str | None = None,
        related_server_id: str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> SkillListResponse:
        return SkillListResponse.model_validate(
            self._client.get(
                "skills",
                params={
                    "team_id": team_id,
                    "search_query": search_query,
                    "sort_order": sort_order,
                    "page_size": page_size,
                    "cursor": cursor,
                    "creator_user_id": creator_user_id,
                    "related_server_id": related_server_id,
                    "agent_id": agent_id,
                    **kwargs,
                },
            )
        )

    def create(
        self,
        files: Mapping[str, bytes | str] | list[SkillFile],
        *,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> SkillResponse:
        return SkillResponse.model_validate(
            self._client.post(
                "skills",
                data={"team_id": team_id, **kwargs},
                files=_multipart_files(files),
            )
        )

    def update(
        self,
        skill_id: str,
        files: Mapping[str, bytes | str] | list[SkillFile],
    ) -> SkillResponse:
        return SkillResponse.model_validate(self._client.patch(f"skills/{skill_id}", files=_multipart_files(files)))

    def download(self, skill_id: str, *, version_id: str | None = None, **kwargs: Any) -> SkillDownloadResponse:
        return SkillDownloadResponse.model_validate(
            self._client.get(f"skills/{skill_id}/download", params={"version_id": version_id, **kwargs})
        )

    def delete(self, skill_id: str) -> SkillDeleteResponse:
        return SkillDeleteResponse.model_validate(self._client.delete(f"skills/{skill_id}"))


class AsyncSkills:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(
        self,
        *,
        team_id: str | None = None,
        search_query: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        creator_user_id: str | None = None,
        related_server_id: str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> SkillListResponse:
        data = await self._client.get(
            "skills",
            params={
                "team_id": team_id,
                "search_query": search_query,
                "sort_order": sort_order,
                "page_size": page_size,
                "cursor": cursor,
                "creator_user_id": creator_user_id,
                "related_server_id": related_server_id,
                "agent_id": agent_id,
                **kwargs,
            },
        )
        return SkillListResponse.model_validate(data)

    async def create(
        self,
        files: Mapping[str, bytes | str] | list[SkillFile],
        *,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> SkillResponse:
        data = await self._client.post(
            "skills",
            data={"team_id": team_id, **kwargs},
            files=_multipart_files(files),
        )
        return SkillResponse.model_validate(data)

    async def update(
        self,
        skill_id: str,
        files: Mapping[str, bytes | str] | list[SkillFile],
    ) -> SkillResponse:
        data = await self._client.patch(f"skills/{skill_id}", files=_multipart_files(files))
        return SkillResponse.model_validate(data)

    async def download(self, skill_id: str, *, version_id: str | None = None, **kwargs: Any) -> SkillDownloadResponse:
        data = await self._client.get(f"skills/{skill_id}/download", params={"version_id": version_id, **kwargs})
        return SkillDownloadResponse.model_validate(data)

    async def delete(self, skill_id: str) -> SkillDeleteResponse:
        data = await self._client.delete(f"skills/{skill_id}")
        return SkillDeleteResponse.model_validate(data)
