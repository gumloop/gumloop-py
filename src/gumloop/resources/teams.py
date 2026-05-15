from __future__ import annotations

from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import TeamsResponse


class Teams:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self, **kwargs: Any) -> TeamsResponse:
        return TeamsResponse.model_validate(self._client.get("teams", params=kwargs))


class AsyncTeams:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self, **kwargs: Any) -> TeamsResponse:
        return TeamsResponse.model_validate(await self._client.get("teams", params=kwargs))
