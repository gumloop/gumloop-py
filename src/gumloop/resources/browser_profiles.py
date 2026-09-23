from __future__ import annotations

from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import BrowserProfileImportResponse
from gumloop.types import BrowserProfilesResponse

DEFAULT_PROFILE = "default"


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

    def import_cookies(
        self,
        profile_id: str,
        *,
        url: str | None = None,
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

    async def import_cookies(
        self,
        profile_id: str,
        *,
        url: str | None = None,
        cookies: list[dict[str, Any]],
        project_id: str | None = None,
    ) -> BrowserProfileImportResponse:
        return BrowserProfileImportResponse.model_validate(
            await self._client.post(
                f"browser-profiles/{profile_id}/cookies",
                json=_body(project_id, url=url, cookies=cookies),
            )
        )
