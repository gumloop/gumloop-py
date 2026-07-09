from __future__ import annotations

from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import BrainSearchRequest
from gumloop.types import BrainSearchResponse


class Brain:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        source_type: list[str] | None = None,
        **kwargs: Any,
    ) -> BrainSearchResponse:
        return BrainSearchResponse.model_validate(
            self._client.post(
                "brain/search",
                json=BrainSearchRequest.build(query=query, limit=limit, source_type=source_type, **kwargs),
            )
        )


class AsyncBrain:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        source_type: list[str] | None = None,
        **kwargs: Any,
    ) -> BrainSearchResponse:
        data = await self._client.post(
            "brain/search",
            json=BrainSearchRequest.build(query=query, limit=limit, source_type=source_type, **kwargs),
        )
        return BrainSearchResponse.model_validate(data)
