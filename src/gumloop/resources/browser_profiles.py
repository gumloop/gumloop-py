from __future__ import annotations

from typing import Any
from typing import Literal
from urllib.parse import quote

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.errors import GumloopError
from gumloop.types import BrowserProfile
from gumloop.types import BrowserProfileCreateRequest
from gumloop.types import BrowserProfileDeleteResponse
from gumloop.types import BrowserProfileImportResponse
from gumloop.types import BrowserProfilesResponse
from gumloop.types import BrowserProfileUpdateRequest

DEFAULT_PROFILE = "default"


def _require_personal_scope(client: HttpClient | AsyncHttpClient) -> None:
    if client.team_id:
        raise GumloopError("Personal browser profile management requires a client without team_id.")


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

    def create(self, name: str) -> BrowserProfile:
        _require_personal_scope(self._client)
        body = BrowserProfileCreateRequest(name=name).model_dump(exclude_none=True)
        return BrowserProfile.model_validate(
            self._client.post("browser-profiles", json=body)
        )

    def get(self, profile_id: str) -> BrowserProfile:
        _require_personal_scope(self._client)
        return BrowserProfile.model_validate(
            self._client.get(f"browser-profiles/{quote(profile_id, safe='')}")
        )

    def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        is_default: Literal[True] | None = None,
    ) -> BrowserProfile:
        _require_personal_scope(self._client)
        body = BrowserProfileUpdateRequest(name=name, is_default=is_default).model_dump(exclude_none=True)
        return BrowserProfile.model_validate(
            self._client.patch(f"browser-profiles/{quote(profile_id, safe='')}", json=body)
        )

    def delete(self, profile_id: str) -> BrowserProfileDeleteResponse:
        _require_personal_scope(self._client)
        return BrowserProfileDeleteResponse.model_validate(
            self._client.delete(f"browser-profiles/{quote(profile_id, safe='')}")
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

    async def create(self, name: str) -> BrowserProfile:
        _require_personal_scope(self._client)
        body = BrowserProfileCreateRequest(name=name).model_dump(exclude_none=True)
        return BrowserProfile.model_validate(
            await self._client.post("browser-profiles", json=body)
        )

    async def get(self, profile_id: str) -> BrowserProfile:
        _require_personal_scope(self._client)
        return BrowserProfile.model_validate(
            await self._client.get(f"browser-profiles/{quote(profile_id, safe='')}")
        )

    async def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        is_default: Literal[True] | None = None,
    ) -> BrowserProfile:
        _require_personal_scope(self._client)
        body = BrowserProfileUpdateRequest(name=name, is_default=is_default).model_dump(exclude_none=True)
        return BrowserProfile.model_validate(
            await self._client.patch(
                f"browser-profiles/{quote(profile_id, safe='')}", json=body
            )
        )

    async def delete(self, profile_id: str) -> BrowserProfileDeleteResponse:
        _require_personal_scope(self._client)
        return BrowserProfileDeleteResponse.model_validate(
            await self._client.delete(f"browser-profiles/{quote(profile_id, safe='')}")
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
                json=_body(team_id, url=url, cookies=cookies),
            )
        )
