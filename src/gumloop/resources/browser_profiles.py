from __future__ import annotations

from typing import Any
from typing import Literal
from urllib.parse import quote

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import BrowserProfile
from gumloop.types import BrowserProfileCreateRequest
from gumloop.types import BrowserProfileDeleteResponse
from gumloop.types import BrowserProfileImportResponse
from gumloop.types import BrowserProfilesResponse
from gumloop.types import BrowserProfileUpdateRequest

DEFAULT_PROFILE = "default"


def _body(team_id: str | None, **fields: Any) -> dict[str, Any]:
    body = {key: value for key, value in fields.items() if value is not None}
    if team_id:
        body["team_id"] = team_id

    return body


class BrowserProfiles:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self, *, team_id: str | None = None) -> BrowserProfilesResponse:
        return BrowserProfilesResponse.model_validate(self._client.get("browser-profiles", params={"team_id": team_id}))

    def create(self, name: str, *, team_id: str | None = None) -> BrowserProfile:
        body = BrowserProfileCreateRequest(name=name, team_id=team_id).model_dump(exclude_none=True)
        return BrowserProfile.model_validate(self._client.post("browser-profiles", json=body))

    def get(self, profile_id: str, *, team_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            self._client.get(f"browser-profiles/{quote(profile_id, safe='')}", params={"team_id": team_id})
        )

    def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        is_default: Literal[True] | None = None,
        team_id: str | None = None,
    ) -> BrowserProfile:
        body = BrowserProfileUpdateRequest(name=name, is_default=is_default, team_id=team_id).model_dump(
            exclude_none=True
        )
        return BrowserProfile.model_validate(
            self._client.patch(f"browser-profiles/{quote(profile_id, safe='')}", json=body)
        )

    def delete(self, profile_id: str, *, team_id: str | None = None) -> BrowserProfileDeleteResponse:
        return BrowserProfileDeleteResponse.model_validate(
            self._client.delete(f"browser-profiles/{quote(profile_id, safe='')}", params={"team_id": team_id})
        )

    def remove_site(self, profile_id: str, site: str, *, team_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            self._client.delete(
                f"browser-profiles/{quote(profile_id, safe='')}/sites/{quote(site, safe='')}",
                params={"team_id": team_id},
            )
        )

    def import_cookies(
        self,
        profile_id: str,
        *,
        url: str | None = None,
        cookies: list[dict[str, Any]],
        team_id: str | None = None,
    ) -> BrowserProfileImportResponse:
        return BrowserProfileImportResponse.model_validate(
            self._client.post(
                f"browser-profiles/{profile_id}/cookies",
                params={"team_id": team_id} if team_id else None,
                json=_body(team_id, url=url, cookies=cookies),
            )
        )


class AsyncBrowserProfiles:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self, *, team_id: str | None = None) -> BrowserProfilesResponse:
        return BrowserProfilesResponse.model_validate(
            await self._client.get("browser-profiles", params={"team_id": team_id})
        )

    async def create(self, name: str, *, team_id: str | None = None) -> BrowserProfile:
        body = BrowserProfileCreateRequest(name=name, team_id=team_id).model_dump(exclude_none=True)
        return BrowserProfile.model_validate(await self._client.post("browser-profiles", json=body))

    async def get(self, profile_id: str, *, team_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            await self._client.get(f"browser-profiles/{quote(profile_id, safe='')}", params={"team_id": team_id})
        )

    async def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        is_default: Literal[True] | None = None,
        team_id: str | None = None,
    ) -> BrowserProfile:
        body = BrowserProfileUpdateRequest(name=name, is_default=is_default, team_id=team_id).model_dump(
            exclude_none=True
        )
        return BrowserProfile.model_validate(
            await self._client.patch(f"browser-profiles/{quote(profile_id, safe='')}", json=body)
        )

    async def delete(self, profile_id: str, *, team_id: str | None = None) -> BrowserProfileDeleteResponse:
        return BrowserProfileDeleteResponse.model_validate(
            await self._client.delete(f"browser-profiles/{quote(profile_id, safe='')}", params={"team_id": team_id})
        )

    async def remove_site(self, profile_id: str, site: str, *, team_id: str | None = None) -> BrowserProfile:
        return BrowserProfile.model_validate(
            await self._client.delete(
                f"browser-profiles/{quote(profile_id, safe='')}/sites/{quote(site, safe='')}",
                params={"team_id": team_id},
            )
        )

    async def import_cookies(
        self,
        profile_id: str,
        *,
        url: str | None = None,
        cookies: list[dict[str, Any]],
        team_id: str | None = None,
    ) -> BrowserProfileImportResponse:
        return BrowserProfileImportResponse.model_validate(
            await self._client.post(
                f"browser-profiles/{profile_id}/cookies",
                params={"team_id": team_id} if team_id else None,
                json=_body(team_id, url=url, cookies=cookies),
            )
        )
