"""Browser login profiles: the cookies and site storage an agent's sandbox browser restores.

Owner scope follows variables: no ``project_id`` means the caller's personal profiles.
``profile_id="default"`` addresses the caller's personal default profile.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import BrowserProfile
from gumloop.types import BrowserProfileImportResponse
from gumloop.types import BrowserProfilesResponse

DEFAULT_PROFILE = "default"


def _scoped(path: str, project_id: str | None) -> str:
    return f"{path}?{urlencode({'project_id': project_id})}" if project_id else path


def _body(project_id: str | None, **fields: Any) -> dict[str, Any]:
    body = {key: value for key, value in fields.items() if value is not None}
    if project_id:
        body["project_id"] = project_id
    return body


class BrowserProfiles:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self, *, project_id: str | None = None) -> BrowserProfilesResponse:
        return BrowserProfilesResponse.model_validate(
            self._client.get("browser-profiles", params={"project_id": project_id})
        )

    def get(self, profile_id: str, *, project_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            self._client.get(f"browser-profiles/{profile_id}", params={"project_id": project_id})
        )

    def create(self, name: str, *, project_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(self._client.post("browser-profiles", json=_body(project_id, name=name)))

    def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        is_default: bool | None = None,
        project_id: str | None = None,
    ) -> BrowserProfile:
        return BrowserProfile.model_validate(
            self._client.patch(
                f"browser-profiles/{profile_id}", json=_body(project_id, name=name, is_default=is_default)
            )
        )

    def delete(self, profile_id: str, *, project_id: str | None = None) -> None:
        self._client.delete(_scoped(f"browser-profiles/{profile_id}", project_id))

    def remove_site(self, profile_id: str, site: str, *, project_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            self._client.delete(_scoped(f"browser-profiles/{profile_id}/sites/{site}", project_id))
        )

    def import_cookies(
        self,
        profile_id: str,
        *,
        url: str,
        cookies: list[dict[str, Any]],
        project_id: str | None = None,
    ) -> BrowserProfileImportResponse:
        return BrowserProfileImportResponse.model_validate(
            self._client.post(
                f"browser-profiles/{profile_id}/cookies",
                json=_body(project_id, url=url, cookies=cookies),
            )
        )


class AsyncBrowserProfiles:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self, *, project_id: str | None = None) -> BrowserProfilesResponse:
        return BrowserProfilesResponse.model_validate(
            await self._client.get("browser-profiles", params={"project_id": project_id})
        )

    async def get(self, profile_id: str, *, project_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            await self._client.get(f"browser-profiles/{profile_id}", params={"project_id": project_id})
        )

    async def create(self, name: str, *, project_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            await self._client.post("browser-profiles", json=_body(project_id, name=name))
        )

    async def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        is_default: bool | None = None,
        project_id: str | None = None,
    ) -> BrowserProfile:
        return BrowserProfile.model_validate(
            await self._client.patch(
                f"browser-profiles/{profile_id}", json=_body(project_id, name=name, is_default=is_default)
            )
        )

    async def delete(self, profile_id: str, *, project_id: str | None = None) -> None:
        await self._client.delete(_scoped(f"browser-profiles/{profile_id}", project_id))

    async def remove_site(self, profile_id: str, site: str, *, project_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            await self._client.delete(_scoped(f"browser-profiles/{profile_id}/sites/{site}", project_id))
        )

    async def import_cookies(
        self,
        profile_id: str,
        *,
        url: str,
        cookies: list[dict[str, Any]],
        project_id: str | None = None,
    ) -> BrowserProfileImportResponse:
        return BrowserProfileImportResponse.model_validate(
            await self._client.post(
                f"browser-profiles/{profile_id}/cookies",
                json=_body(project_id, url=url, cookies=cookies),
            )
        )
