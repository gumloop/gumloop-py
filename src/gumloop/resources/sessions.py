from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Any
from typing import Literal
from typing import overload

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import SessionContinueRequest
from gumloop.types import SessionCreateRequest
from gumloop.types import SessionResponse
from gumloop.types import StreamEvent


class Sessions:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    @overload
    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        **kwargs: Any,
    ) -> Iterator[StreamEvent]: ...
    @overload
    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | Iterator[StreamEvent]:
        body = SessionCreateRequest.build(request, **kwargs)
        if body.get("stream") is True:
            return self._client.stream("POST", f"agents/{agent_id}/sessions", json=body)
        return SessionResponse.model_validate(self._client.post(f"agents/{agent_id}/sessions", json=body))

    def stream(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        body = SessionCreateRequest.build(request, **kwargs, stream=True)
        return self._client.stream("POST", f"agents/{agent_id}/sessions", json=body)

    def retrieve(self, session_id: str) -> SessionResponse:
        return SessionResponse.model_validate(self._client.get(f"sessions/{session_id}"))

    @overload
    def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        **kwargs: Any,
    ) -> Iterator[StreamEvent]: ...
    @overload
    def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | Iterator[StreamEvent]:
        body = SessionContinueRequest.build(request, **kwargs)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        if body.get("stream") is True:
            return self._client.stream("POST", f"sessions/{session_id}/messages", json=body)
        return SessionResponse.model_validate(self._client.post(f"sessions/{session_id}/messages", json=body))

    def stream_message(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        body = SessionContinueRequest.build(request, **kwargs, stream=True)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        return self._client.stream("POST", f"sessions/{session_id}/messages", json=body)

    def resume_stream(self, session_id: str, last_cursor: str, **kwargs: Any) -> Iterator[StreamEvent]:
        return self._client.stream(
            "GET",
            f"sessions/{session_id}",
            params={"stream": "true", "last_cursor": last_cursor, **kwargs},
        )

    def cancel(self, session_id: str) -> SessionResponse:
        return SessionResponse.model_validate(self._client.post(f"sessions/{session_id}/cancel", json={}))


class AsyncSessions:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    @overload
    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]: ...
    @overload
    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        body = SessionCreateRequest.build(request, **kwargs)
        if body.get("stream") is True:
            return self._client.stream("POST", f"agents/{agent_id}/sessions", json=body)
        data = await self._client.post(f"agents/{agent_id}/sessions", json=body)
        return SessionResponse.model_validate(data)

    def stream(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        body = SessionCreateRequest.build(request, **kwargs, stream=True)
        return self._client.stream("POST", f"agents/{agent_id}/sessions", json=body)

    async def retrieve(self, session_id: str) -> SessionResponse:
        return SessionResponse.model_validate(await self._client.get(f"sessions/{session_id}"))

    @overload
    async def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]: ...
    @overload
    async def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    async def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        body = SessionContinueRequest.build(request, **kwargs)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        if body.get("stream") is True:
            return self._client.stream("POST", f"sessions/{session_id}/messages", json=body)
        data = await self._client.post(f"sessions/{session_id}/messages", json=body)
        return SessionResponse.model_validate(data)

    def stream_message(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        body = SessionContinueRequest.build(request, **kwargs, stream=True)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        return self._client.stream("POST", f"sessions/{session_id}/messages", json=body)

    def resume_stream(self, session_id: str, last_cursor: str, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        return self._client.stream(
            "GET",
            f"sessions/{session_id}",
            params={"stream": "true", "last_cursor": last_cursor, **kwargs},
        )

    async def cancel(self, session_id: str) -> SessionResponse:
        data = await self._client.post(f"sessions/{session_id}/cancel", json={})
        return SessionResponse.model_validate(data)
