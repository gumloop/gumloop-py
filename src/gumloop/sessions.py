from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gumloop.types import QueuedResponseResponse
from gumloop.types import ResponseResponse
from gumloop.types import SessionCreateRequest
from gumloop.types import SessionResponse


def _session_body(
    request: Mapping[str, Any] | None = None,
    *,
    input: str | list[Any] | None = None,
    message: str | list[Any] | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
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
    ) -> SessionResponse | ResponseResponse | QueuedResponseResponse:
        body = _session_body(
            request,
            input=input,
            message=message,
            session_id=session_id,
            metadata=metadata,
        )
        return self._client._request_json("POST", f"agents/{agent_id}/sessions", json=body)

    def retrieve(self, session_id: str) -> SessionResponse:
        return self._client._request_json("GET", f"sessions/{session_id}")

    def send(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        *,
        message: str | list[Any] | None = None,
    ) -> ResponseResponse | QueuedResponseResponse:
        body = _session_body(input=input, message=message)
        if not body:
            raise ValueError("input or message is required")
        return self._client._request_json("POST", f"sessions/{session_id}", json=body)

    def cancel(self, session_id: str) -> ResponseResponse | dict[str, str]:
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
    ) -> SessionResponse | ResponseResponse | QueuedResponseResponse:
        body = _session_body(
            request,
            input=input,
            message=message,
            session_id=session_id,
            metadata=metadata,
        )
        return await self._client._request_json("POST", f"agents/{agent_id}/sessions", json=body)

    async def retrieve(self, session_id: str) -> SessionResponse:
        return await self._client._request_json("GET", f"sessions/{session_id}")

    async def send(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        *,
        message: str | list[Any] | None = None,
    ) -> ResponseResponse | QueuedResponseResponse:
        body = _session_body(input=input, message=message)
        if not body:
            raise ValueError("input or message is required")
        return await self._client._request_json("POST", f"sessions/{session_id}", json=body)

    async def cancel(self, session_id: str) -> ResponseResponse | dict[str, str]:
        return await self._client._request_json("POST", f"sessions/{session_id}/cancel", json={})
