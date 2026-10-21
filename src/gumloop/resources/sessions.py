from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any
from typing import Literal
from typing import overload
from uuid import uuid4

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.resources._item_access import item_access_body
from gumloop.types import ItemAccessChangeResponse
from gumloop.types import ItemAccessResponse
from gumloop.types import SessionContinueRequest
from gumloop.types import SessionCreateRequest
from gumloop.types import SessionFileResponse
from gumloop.types import SessionListResponse
from gumloop.types import SessionMessageReceipt
from gumloop.types import SessionResponse
from gumloop.types import SessionUpdateRequest
from gumloop.types import StreamEvent


class Sessions:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(
        self,
        agent_id: str,
        *,
        search: str | None = None,
        state: str | None = None,
        type: str | None = None,
        creator_user_id: str | None = None,
        trigger_id: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> SessionListResponse:
        return SessionListResponse.model_validate(
            self._client.get(
                f"agents/{agent_id}/sessions",
                params={
                    "search": search,
                    "state": state,
                    "type": type,
                    "creator_user_id": creator_user_id,
                    "trigger_id": trigger_id,
                    "sort_order": sort_order,
                    "page_size": page_size,
                    "cursor": cursor,
                    **kwargs,
                },
            )
        )

    @overload
    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        extra_headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]: ...
    @overload
    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        extra_headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | Iterator[StreamEvent]:
        body = SessionCreateRequest.build(request, **kwargs)
        if body.get("stream") is True:
            return self._client.stream("POST", f"agents/{agent_id}/sessions", json=body, extra_headers=extra_headers)
        return SessionResponse.model_validate(
            self._client.post(f"agents/{agent_id}/sessions", json=body, extra_headers=extra_headers)
        )

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
        delivery: Literal["queued"],
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionMessageReceipt: ...
    @overload
    def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        delivery: Literal["immediate"] = "immediate",
        **kwargs: Any,
    ) -> Iterator[StreamEvent]: ...
    @overload
    def send(
        self,
        session_id: str,
        request: None = None,
        *,
        delivery: Literal["immediate"] = "immediate",
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    @overload
    def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any],
        *,
        delivery: Literal["immediate", "queued"] | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> SessionResponse | SessionMessageReceipt | Iterator[StreamEvent]: ...
    def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | SessionMessageReceipt | Iterator[StreamEvent]:
        body = SessionContinueRequest.build(request, **kwargs)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        if body.get("stream") is True:
            return self._client.stream("POST", f"sessions/{session_id}/messages", json=body)
        headers = None
        if body.get("delivery") == "queued":
            headers = {"Idempotency-Key": body.pop("idempotency_key", None) or str(uuid4())}
        data = self._client.post(f"sessions/{session_id}/messages", json=body, extra_headers=headers)
        if body.get("delivery") == "queued":
            return SessionMessageReceipt.model_validate(data)
        return SessionResponse.model_validate(data)

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

    def upload_file(
        self, session_id: str, file_name: str, file_content: bytes, *, media_type: str | None = None
    ) -> SessionFileResponse:
        """Upload bytes; attach the returned file_name to a follow-up message."""
        body = {"file_name": file_name, "file_content": base64.b64encode(file_content).decode("ascii")}
        if media_type is not None:
            body["media_type"] = media_type
        return SessionFileResponse.model_validate(self._client.post(f"sessions/{session_id}/files", json=body))

    def cancel(self, session_id: str) -> SessionResponse:
        return SessionResponse.model_validate(self._client.post(f"sessions/{session_id}/cancel", json={}))

    def update(
        self,
        session_id: str,
        request: SessionUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse:
        return SessionResponse.model_validate(
            self._client.patch(f"sessions/{session_id}", json=SessionUpdateRequest.build(request, **kwargs))
        )

    def get_access(self, session_id: str) -> ItemAccessResponse:
        return ItemAccessResponse.model_validate(self._client.get(f"sessions/{session_id}/access"))

    def update_access(
        self,
        session_id: str,
        *,
        share: Sequence[Mapping[str, Any]] | None = None,
        remove: Sequence[Mapping[str, Any]] | None = None,
        link: Mapping[str, Any] | None = None,
    ) -> ItemAccessChangeResponse:
        return ItemAccessChangeResponse.model_validate(
            self._client.put(
                f"sessions/{session_id}/access",
                json=item_access_body(share=share, remove=remove, link=link),
            )
        )


class AsyncSessions:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(
        self,
        agent_id: str,
        *,
        search: str | None = None,
        state: str | None = None,
        type: str | None = None,
        creator_user_id: str | None = None,
        trigger_id: str | None = None,
        sort_order: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> SessionListResponse:
        data = await self._client.get(
            f"agents/{agent_id}/sessions",
            params={
                "search": search,
                "state": state,
                "type": type,
                "creator_user_id": creator_user_id,
                "trigger_id": trigger_id,
                "sort_order": sort_order,
                "page_size": page_size,
                "cursor": cursor,
                **kwargs,
            },
        )
        return SessionListResponse.model_validate(data)

    @overload
    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        extra_headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]: ...
    @overload
    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[False] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    async def create(
        self,
        agent_id: str,
        request: SessionCreateRequest | Mapping[str, Any] | None = None,
        *,
        extra_headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        body = SessionCreateRequest.build(request, **kwargs)
        if body.get("stream") is True:
            return self._client.stream("POST", f"agents/{agent_id}/sessions", json=body, extra_headers=extra_headers)
        data = await self._client.post(f"agents/{agent_id}/sessions", json=body, extra_headers=extra_headers)
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
        delivery: Literal["queued"],
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionMessageReceipt: ...
    @overload
    async def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        *,
        stream: Literal[True],
        delivery: Literal["immediate"] = "immediate",
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]: ...
    @overload
    async def send(
        self,
        session_id: str,
        request: None = None,
        *,
        delivery: Literal["immediate"] = "immediate",
        stream: Literal[False] | None = None,
        **kwargs: Any,
    ) -> SessionResponse: ...
    @overload
    async def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any],
        *,
        delivery: Literal["immediate", "queued"] | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> SessionResponse | SessionMessageReceipt | AsyncIterator[StreamEvent]: ...
    async def send(
        self,
        session_id: str,
        request: SessionContinueRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | SessionMessageReceipt | AsyncIterator[StreamEvent]:
        body = SessionContinueRequest.build(request, **kwargs)
        if body.get("input") is None and body.get("message") is None:
            raise ValueError("input or message is required")
        if body.get("stream") is True:
            return self._client.stream("POST", f"sessions/{session_id}/messages", json=body)
        headers = None
        if body.get("delivery") == "queued":
            headers = {"Idempotency-Key": body.pop("idempotency_key", None) or str(uuid4())}
        data = await self._client.post(f"sessions/{session_id}/messages", json=body, extra_headers=headers)
        if body.get("delivery") == "queued":
            return SessionMessageReceipt.model_validate(data)
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

    async def upload_file(
        self, session_id: str, file_name: str, file_content: bytes, *, media_type: str | None = None
    ) -> SessionFileResponse:
        """Upload bytes; attach the returned file_name to a follow-up message."""
        body = {"file_name": file_name, "file_content": base64.b64encode(file_content).decode("ascii")}
        if media_type is not None:
            body["media_type"] = media_type
        data = await self._client.post(f"sessions/{session_id}/files", json=body)
        return SessionFileResponse.model_validate(data)

    async def cancel(self, session_id: str) -> SessionResponse:
        data = await self._client.post(f"sessions/{session_id}/cancel", json={})
        return SessionResponse.model_validate(data)

    async def update(
        self,
        session_id: str,
        request: SessionUpdateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse:
        data = await self._client.patch(f"sessions/{session_id}", json=SessionUpdateRequest.build(request, **kwargs))
        return SessionResponse.model_validate(data)

    async def get_access(self, session_id: str) -> ItemAccessResponse:
        return ItemAccessResponse.model_validate(await self._client.get(f"sessions/{session_id}/access"))

    async def update_access(
        self,
        session_id: str,
        *,
        share: Sequence[Mapping[str, Any]] | None = None,
        remove: Sequence[Mapping[str, Any]] | None = None,
        link: Mapping[str, Any] | None = None,
    ) -> ItemAccessChangeResponse:
        data = await self._client.put(
            f"sessions/{session_id}/access",
            json=item_access_body(share=share, remove=remove, link=link),
        )
        return ItemAccessChangeResponse.model_validate(data)
