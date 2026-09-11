from __future__ import annotations

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import OrganizationsResponse


class Organizations:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> OrganizationsResponse:
        return OrganizationsResponse.model_validate(self._client.get("organizations"))


class AsyncOrganizations:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self) -> OrganizationsResponse:
        return OrganizationsResponse.model_validate(await self._client.get("organizations"))
