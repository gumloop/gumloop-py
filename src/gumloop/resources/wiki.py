from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import WikiQueryRequest
from gumloop.types import WikiQueryResponse


class Wiki:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def query(
        self, request: WikiQueryRequest | Mapping[str, Any] | None = None, **kwargs: Any
    ) -> WikiQueryResponse:
        """Read the personal wiki, optionally filtering by type and entity_key."""
        return WikiQueryResponse.model_validate(
            self._client.post("wiki/query", json=WikiQueryRequest.build(request, **kwargs))
        )


class AsyncWiki:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def query(
        self, request: WikiQueryRequest | Mapping[str, Any] | None = None, **kwargs: Any
    ) -> WikiQueryResponse:
        """Read the personal wiki, optionally filtering by type and entity_key."""
        return WikiQueryResponse.model_validate(
            await self._client.post("wiki/query", json=WikiQueryRequest.build(request, **kwargs))
        )
