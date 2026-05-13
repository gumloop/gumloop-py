from __future__ import annotations

from typing import Any

from gumloop.types import TeamsResponse


class Teams:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, **kwargs: Any) -> TeamsResponse:
        return self._client._request_json("GET", "teams", params=kwargs)


class AsyncTeams:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def list(self, **kwargs: Any) -> TeamsResponse:
        return await self._client._request_json("GET", "teams", params=kwargs)
