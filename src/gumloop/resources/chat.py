"""Chat completions resource — OpenRouter request shape."""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Any
from typing import Literal
from typing import overload

from pydantic import ValidationError

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.errors import GumloopError
from gumloop.spec import ChatRequest
from gumloop.spec import ChatResult
from gumloop.spec import ChatStreamChunk
from gumloop.spec._compat import to_wire_dict

_PATH = "chat/completions"


def _build_request(
    request: ChatRequest | Mapping[str, Any] | None,
    kwargs: dict[str, Any],
) -> ChatRequest:
    if isinstance(request, ChatRequest):
        base = to_wire_dict(request)
    elif request is None:
        base = {}
    else:
        base = dict(request)
    # Kwargs whose value is None are dropped — they're "leave existing value
    # alone" hints, not "clear this field" overrides. To clear a field, build
    # a fresh ChatRequest instead of relying on the overlay.
    base.update({k: v for k, v in kwargs.items() if v is not None})
    try:
        return ChatRequest.model_validate(base)
    except ValidationError as exc:
        raise GumloopError(f"invalid chat request: {exc}") from exc


class Completions:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    @overload
    def create(
        self,
        request: ChatRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        **kwargs: Any,
    ) -> Iterator[ChatStreamChunk]: ...
    @overload
    def create(
        self,
        request: ChatRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> ChatResult: ...
    def create(
        self,
        request: ChatRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResult | Iterator[ChatStreamChunk]:
        body = _build_request(request, kwargs)
        wire = to_wire_dict(body)
        if wire.get("stream") is True:
            return self._client.stream_typed("POST", _PATH, ChatStreamChunk, json=wire)
        return ChatResult.model_validate(self._client.post_to_stream_host(_PATH, json=wire))


class AsyncCompletions:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    @overload
    async def create(
        self,
        request: ChatRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]: ...
    @overload
    async def create(
        self,
        request: ChatRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> ChatResult: ...
    async def create(
        self,
        request: ChatRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResult | AsyncIterator[ChatStreamChunk]:
        body = _build_request(request, kwargs)
        wire = to_wire_dict(body)
        if wire.get("stream") is True:
            return self._client.stream_typed("POST", _PATH, ChatStreamChunk, json=wire)
        data = await self._client.post_to_stream_host(_PATH, json=wire)
        return ChatResult.model_validate(data)


class Chat:
    def __init__(self, client: HttpClient) -> None:
        self.completions = Completions(client)


class AsyncChat:
    def __init__(self, client: AsyncHttpClient) -> None:
        self.completions = AsyncCompletions(client)
