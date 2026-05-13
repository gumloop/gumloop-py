from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop.types import SkillDownloadResponse
from gumloop.types import SkillListResponse
from gumloop.types import SkillResponse

SkillFile = tuple[str, bytes | str] | tuple[str, bytes | str, str]


def _params(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


def _multipart_files(files: Mapping[str, bytes | str] | list[SkillFile]) -> list[tuple[str, Any]]:
    items = files.items() if isinstance(files, Mapping) else files
    multipart = []
    for item in items:
        filename, content, *rest = item
        media_type = rest[0] if rest else "application/octet-stream"
        multipart.append(("files", (filename, content, media_type)))
    return multipart


class Skills:
    def __init__(self, client: Any) -> None:
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
        gummie_id: str | None = None,
        unused: str | None = None,
        **kwargs: Any,
    ) -> SkillListResponse:
        params = _params(
            team_id=team_id,
            search_query=search_query,
            sort_order=sort_order,
            page_size=page_size,
            cursor=cursor,
            creator_user_id=creator_user_id,
            related_server_id=related_server_id,
            gummie_id=gummie_id,
            unused=unused,
            **kwargs,
        )
        return self._client._request_json("GET", "skills", params=params)

    def create(
        self,
        files: Mapping[str, bytes | str] | list[SkillFile],
        *,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> SkillResponse:
        return self._client._request_json(
            "POST",
            "skills",
            data=_params(team_id=team_id, **kwargs),
            files=_multipart_files(files),
        )

    def update(
        self,
        skill_id: str,
        files: Mapping[str, bytes | str] | list[SkillFile],
    ) -> SkillResponse:
        return self._client._request_json("PATCH", f"skills/{skill_id}", files=_multipart_files(files))

    def download(self, skill_id: str, *, version_id: str | None = None, **kwargs: Any) -> SkillDownloadResponse:
        params = _params(version_id=version_id, **kwargs)
        return self._client._request_json("GET", f"skills/{skill_id}/download", params=params)


class AsyncSkills:
    def __init__(self, client: Any) -> None:
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
        gummie_id: str | None = None,
        unused: str | None = None,
        **kwargs: Any,
    ) -> SkillListResponse:
        params = _params(
            team_id=team_id,
            search_query=search_query,
            sort_order=sort_order,
            page_size=page_size,
            cursor=cursor,
            creator_user_id=creator_user_id,
            related_server_id=related_server_id,
            gummie_id=gummie_id,
            unused=unused,
            **kwargs,
        )
        return await self._client._request_json("GET", "skills", params=params)

    async def create(
        self,
        files: Mapping[str, bytes | str] | list[SkillFile],
        *,
        team_id: str | None = None,
        **kwargs: Any,
    ) -> SkillResponse:
        return await self._client._request_json(
            "POST",
            "skills",
            data=_params(team_id=team_id, **kwargs),
            files=_multipart_files(files),
        )

    async def update(
        self,
        skill_id: str,
        files: Mapping[str, bytes | str] | list[SkillFile],
    ) -> SkillResponse:
        return await self._client._request_json("PATCH", f"skills/{skill_id}", files=_multipart_files(files))

    async def download(self, skill_id: str, *, version_id: str | None = None, **kwargs: Any) -> SkillDownloadResponse:
        params = _params(version_id=version_id, **kwargs)
        return await self._client._request_json("GET", f"skills/{skill_id}/download", params=params)
