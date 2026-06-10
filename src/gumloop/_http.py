from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Any
from typing import TypeVar

import httpx
from httpx_sse import EventSource
from httpx_sse import ServerSentEvent
from pydantic import BaseModel
from pydantic import ValidationError

from gumloop.errors import APIStatusError
from gumloop.errors import AuthenticationError
from gumloop.errors import RateLimitError
from gumloop.errors import ServerError
from gumloop.errors import to_api_error
from gumloop.types import StreamEvent

logger = logging.getLogger(__name__)

_DONE_SENTINEL = "[DONE]"
_T = TypeVar("_T", bound=BaseModel)

DEFAULT_MAX_RETRIES = 2
# Base delay in seconds for exponential backoff; actual delay is base * 2^attempt + jitter.
_RETRY_BASE_DELAY = 0.5
_RETRY_MAX_DELAY = 60.0


def _auth_headers(access_token: str | None, user_id: str | None) -> dict[str, str]:
    if not access_token:
        raise AuthenticationError("access_token, api_key, or GUMLOOP_ACCESS_TOKEN is required")
    headers = {"Authorization": f"Bearer {access_token}"}
    if user_id:
        headers["x-auth-key"] = user_id
    return headers


def _omit_none_params(params: Mapping[str, Any] | None) -> dict[str, Any] | None:
    # Backend treats absent ``?foo`` and ``?foo=`` as different signals
    # ("not provided" vs "empty string"); drop None values so the wire URL
    # matches the caller's intent.
    if params is None:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _should_retry(exc: APIStatusError) -> bool:
    # Retry on rate-limit and transient server errors; never retry client errors.
    return isinstance(exc, (RateLimitError, ServerError))


def _retry_delay(attempt: int, retry_after: float | None) -> float:
    """Return how many seconds to sleep before the next attempt.

    Honours a ``Retry-After`` header when present; otherwise uses exponential
    backoff with full jitter so concurrent clients don't thunderherd.
    """
    if retry_after is not None:
        return retry_after
    cap = min(_RETRY_BASE_DELAY * (2**attempt), _RETRY_MAX_DELAY)
    return random.uniform(0, cap)


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _decode_sse(event: ServerSentEvent) -> StreamEvent:
    try:
        decoded: Any = event.json() if event.data else {}
    except ValueError:
        decoded = {"data": event.data}
    if not isinstance(decoded, dict):
        decoded = {"data": decoded}
    # Per the SSE spec ``event:`` defaults to "message", which carries no
    # signal — only surface non-default names, and never clobber a "type"
    # the JSON payload already set.
    if event.event and event.event != "message" and "type" not in decoded:
        decoded["type"] = event.event
    return StreamEvent.model_validate(decoded)


class HttpClient:
    """Sync transport for the Gumloop API. Owns the ``httpx.Client``
    lifecycle, auth header injection, URL composition, error mapping, and
    SSE parsing. Resources call through this — they never touch httpx
    directly."""

    def __init__(
        self,
        *,
        base_url: str,
        stream_base_url: str,
        access_token: str | None,
        user_id: str | None,
        timeout: float,
        stream_timeout: float | None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.access_token = access_token
        self.user_id = user_id
        self._stream_base_url = stream_base_url.rstrip("/")
        self._stream_timeout = stream_timeout
        self._max_retries = max_retries
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=_omit_none_params(params))

    def post(
        self,
        path: str,
        *,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[tuple[str, Any]] | None = None,
    ) -> Any:
        return self._request("POST", path, json=json, data=_omit_none_params(data), files=files)

    def patch(
        self,
        path: str,
        *,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[tuple[str, Any]] | None = None,
    ) -> Any:
        return self._request("PATCH", path, json=json, data=_omit_none_params(data), files=files)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def post_to_stream_host(self, path: str, *, json: Any = None) -> Any:
        # Endpoints whose streaming variant lives on the stream host (e.g. chat
        # completions) must accept their unary counterparts at the same host —
        # the api host has no handler for them.
        headers = _auth_headers(self.access_token, self.user_id)
        headers["Content-Type"] = "application/json"
        url = f"{self._stream_base_url}/{path.lstrip('/')}"
        for attempt in range(self._max_retries + 1):
            response = self._client.post(url, headers=headers, timeout=self._stream_timeout, json=json)
            if response.status_code < 400:
                return response.json() if response.content else None
            exc = to_api_error(response)
            if attempt < self._max_retries and _should_retry(exc):
                delay = _retry_delay(attempt, _parse_retry_after(response))
                logger.debug("retrying stream-host request (attempt %d, delay %.2fs)", attempt + 1, delay)
                time.sleep(delay)
                continue
            raise exc

    def stream(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[StreamEvent]:
        headers = {**_auth_headers(self.access_token, self.user_id), "Accept": "text/event-stream"}
        with self._client.stream(
            method,
            f"{self._stream_base_url}/{path.lstrip('/')}",
            headers=headers,
            timeout=self._stream_timeout,
            json=json,
            params=_omit_none_params(params),
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise to_api_error(response)
            for event in EventSource(response).iter_sse():
                yield _decode_sse(event)

    def stream_typed(
        self,
        method: str,
        path: str,
        response_model: type[_T],
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[_T]:
        # Skips the StreamEvent envelope and honors OpenRouter's `data: [DONE]`
        # terminator. Unparseable events (keep-alives, comments) are skipped.
        headers = {**_auth_headers(self.access_token, self.user_id), "Accept": "text/event-stream"}
        with self._client.stream(
            method,
            f"{self._stream_base_url}/{path.lstrip('/')}",
            headers=headers,
            timeout=self._stream_timeout,
            json=json,
            params=_omit_none_params(params),
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise to_api_error(response)
            for event in EventSource(response).iter_sse():
                if event.data == _DONE_SENTINEL:
                    return
                if not event.data:
                    continue
                try:
                    yield response_model.model_validate_json(event.data)
                except ValidationError:
                    # Server-side mid-stream error frames or schema-drift events
                    # land here.
                    logger.debug("dropped non-%s SSE: %s", response_model.__name__, event.data)
                    continue

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        # Headers are rebuilt per request so ``access_token`` / ``user_id``
        # can be rotated on a live client without reconstructing it.
        headers = _auth_headers(self.access_token, self.user_id)
        if not kwargs.get("files"):
            headers["Content-Type"] = "application/json"
        for attempt in range(self._max_retries + 1):
            response = self._client.request(method, path, headers=headers, **kwargs)
            if response.status_code < 400:
                return response.json() if response.content else None
            exc = to_api_error(response)
            if attempt < self._max_retries and _should_retry(exc):
                delay = _retry_delay(attempt, _parse_retry_after(response))
                logger.debug("retrying %s %s (attempt %d, delay %.2fs)", method, path, attempt + 1, delay)
                time.sleep(delay)
                continue
            raise exc


class AsyncHttpClient:
    """Async mirror of :class:`HttpClient`."""

    def __init__(
        self,
        *,
        base_url: str,
        stream_base_url: str,
        access_token: str | None,
        user_id: str | None,
        timeout: float,
        stream_timeout: float | None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.access_token = access_token
        self.user_id = user_id
        self._stream_base_url = stream_base_url.rstrip("/")
        self._stream_timeout = stream_timeout
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHttpClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=_omit_none_params(params))

    async def post(
        self,
        path: str,
        *,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[tuple[str, Any]] | None = None,
    ) -> Any:
        return await self._request("POST", path, json=json, data=_omit_none_params(data), files=files)

    async def patch(
        self,
        path: str,
        *,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: list[tuple[str, Any]] | None = None,
    ) -> Any:
        return await self._request("PATCH", path, json=json, data=_omit_none_params(data), files=files)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    async def post_to_stream_host(self, path: str, *, json: Any = None) -> Any:
        headers = _auth_headers(self.access_token, self.user_id)
        headers["Content-Type"] = "application/json"
        url = f"{self._stream_base_url}/{path.lstrip('/')}"
        for attempt in range(self._max_retries + 1):
            response = await self._client.post(url, headers=headers, timeout=self._stream_timeout, json=json)
            if response.status_code < 400:
                return response.json() if response.content else None
            exc = to_api_error(response)
            if attempt < self._max_retries and _should_retry(exc):
                delay = _retry_delay(attempt, _parse_retry_after(response))
                logger.debug("retrying stream-host request (attempt %d, delay %.2fs)", attempt + 1, delay)
                await asyncio.sleep(delay)
                continue
            raise exc

    async def stream(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        headers = {**_auth_headers(self.access_token, self.user_id), "Accept": "text/event-stream"}
        async with self._client.stream(
            method,
            f"{self._stream_base_url}/{path.lstrip('/')}",
            headers=headers,
            timeout=self._stream_timeout,
            json=json,
            params=_omit_none_params(params),
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise to_api_error(response)
            async for event in EventSource(response).aiter_sse():
                yield _decode_sse(event)

    async def stream_typed(
        self,
        method: str,
        path: str,
        response_model: type[_T],
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[_T]:
        headers = {**_auth_headers(self.access_token, self.user_id), "Accept": "text/event-stream"}
        async with self._client.stream(
            method,
            f"{self._stream_base_url}/{path.lstrip('/')}",
            headers=headers,
            timeout=self._stream_timeout,
            json=json,
            params=_omit_none_params(params),
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise to_api_error(response)
            async for event in EventSource(response).aiter_sse():
                if event.data == _DONE_SENTINEL:
                    return
                if not event.data:
                    continue
                try:
                    yield response_model.model_validate_json(event.data)
                except ValidationError:
                    # Server-side mid-stream error frames or schema-drift events
                    # land here.
                    logger.debug("dropped non-%s SSE: %s", response_model.__name__, event.data)
                    continue

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = _auth_headers(self.access_token, self.user_id)
        if not kwargs.get("files"):
            headers["Content-Type"] = "application/json"
        for attempt in range(self._max_retries + 1):
            response = await self._client.request(method, path, headers=headers, **kwargs)
            if response.status_code < 400:
                return response.json() if response.content else None
            exc = to_api_error(response)
            if attempt < self._max_retries and _should_retry(exc):
                delay = _retry_delay(attempt, _parse_retry_after(response))
                logger.debug("retrying %s %s (attempt %d, delay %.2fs)", method, path, attempt + 1, delay)
                await asyncio.sleep(delay)
                continue
            raise exc
