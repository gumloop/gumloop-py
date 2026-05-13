from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Any

from gumloop.types import SessionCreateRequest
from gumloop.types import SessionResponse
from gumloop.types import StreamEvent


def _session_body(
    request: Mapping[str, Any] | None = None,
    *,
    input: str | list[Any] | None = None,
    message: str | list[Any] | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    stream: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if input is not None and message is not None:
        raise ValueError("Pass only one of input or message")

    body = dict(request or {})
    body.update(
        {
            key: value
            for key, value in {
                "input": input,
                "message": message,
                "session_id": session_id,
                "metadata": metadata,
                "stream": stream,
                **kwargs,
            }.items()
            if value is not None
        }
    )
    return body


class Sessions:
    def __init__(self, client: Any) -> None:
        self._client = client

    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        *,
        input: str | list[Any] | None = None,
        message: str | list[Any] | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> SessionResponse | Iterator[StreamEvent]:
        body = _session_body(
            request,
            input=input,
            message=message,
            session_id=session_id,
            metadata=metadata,
            stream=stream,
            **kwargs,
        )
        if body.get("stream") is True:
            return self._client._stream_json("POST", f"agents/{agent_id}/sessions", json=body)
        return self._client._request_json("POST", f"agents/{agent_id}/sessions", json=body)

    def stream(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        *,
        input: str | list[Any] | None = None,
        message: str | list[Any] | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        return self._client._stream_json(
            "POST",
            f"agents/{agent_id}/sessions",
            json=_session_body(
                request,
                input=input,
                message=message,
                session_id=session_id,
                metadata=metadata,
                stream=True,
                **kwargs,
            ),
        )

    def retrieve(self, session_id: str) -> SessionResponse:
        return self._client._request_json("GET", f"sessions/{session_id}")

    def send(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        *,
        message: str | list[Any] | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> SessionResponse | Iterator[StreamEvent]:
        if input is None and message is None:
            raise ValueError("input or message is required")
        body = _session_body(input=input, message=message, stream=stream, **kwargs)
        if body.get("stream") is True:
            return self._client._stream_json("POST", f"sessions/{session_id}/messages", json=body)
        return self._client._request_json("POST", f"sessions/{session_id}/messages", json=body)

    def stream_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        *,
        message: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        if input is None and message is None:
            raise ValueError("input or message is required")
        return self._client._stream_json(
            "POST",
            f"sessions/{session_id}/messages",
            json=_session_body(input=input, message=message, stream=True, **kwargs),
        )

    def resume_stream(self, session_id: str, last_cursor: str, **kwargs: Any) -> Iterator[StreamEvent]:
        params = {"stream": "true", "last_cursor": last_cursor, **kwargs}
        return self._client._stream_json("GET", f"sessions/{session_id}", params=params)

    def cancel(self, session_id: str) -> SessionResponse:
        return self._client._request_json("POST", f"sessions/{session_id}/cancel", json={})


class AsyncSessions:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        *,
        input: str | list[Any] | None = None,
        message: str | list[Any] | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        body = _session_body(
            request,
            input=input,
            message=message,
            session_id=session_id,
            metadata=metadata,
            stream=stream,
            **kwargs,
        )
        if body.get("stream") is True:
            return self._client._astream_json("POST", f"agents/{agent_id}/sessions", json=body)
        return await self._client._request_json("POST", f"agents/{agent_id}/sessions", json=body)

    def stream(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        *,
        input: str | list[Any] | None = None,
        message: str | list[Any] | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        return self._client._astream_json(
            "POST",
            f"agents/{agent_id}/sessions",
            json=_session_body(
                request,
                input=input,
                message=message,
                session_id=session_id,
                metadata=metadata,
                stream=True,
                **kwargs,
            ),
        )

    async def retrieve(self, session_id: str) -> SessionResponse:
        return await self._client._request_json("GET", f"sessions/{session_id}")

    async def send(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        *,
        message: str | list[Any] | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        if input is None and message is None:
            raise ValueError("input or message is required")
        body = _session_body(input=input, message=message, stream=stream, **kwargs)
        if body.get("stream") is True:
            return self._client._astream_json("POST", f"sessions/{session_id}/messages", json=body)
        return await self._client._request_json("POST", f"sessions/{session_id}/messages", json=body)

    def stream_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        *,
        message: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        if input is None and message is None:
            raise ValueError("input or message is required")
        return self._client._astream_json(
            "POST",
            f"sessions/{session_id}/messages",
            json=_session_body(input=input, message=message, stream=True, **kwargs),
        )

    def resume_stream(self, session_id: str, last_cursor: str, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        params = {"stream": "true", "last_cursor": last_cursor, **kwargs}
        return self._client._astream_json("GET", f"sessions/{session_id}", params=params)

    async def cancel(self, session_id: str) -> SessionResponse:
        return await self._client._request_json("POST", f"sessions/{session_id}/cancel", json={})
