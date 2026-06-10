"""Tests for the error hierarchy and retry logic."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import APIStatusError
from gumloop.errors import BadRequestError
from gumloop.errors import NotFoundError
from gumloop.errors import PermissionDeniedError
from gumloop.errors import RateLimitError
from gumloop.errors import ServerError
from gumloop.errors import UnprocessableEntityError
from gumloop.errors import to_api_error
from tests.sdk.helpers import API_BASE


# ---------------------------------------------------------------------------
# to_api_error dispatch
# ---------------------------------------------------------------------------


def _fake_response(status: int, body: dict | None = None) -> httpx.Response:
    import json

    content = json.dumps(body).encode() if body else b""
    return httpx.Response(status, content=content, headers={"content-type": "application/json"})


@pytest.mark.parametrize(
    ("status", "expected_cls"),
    [
        (400, BadRequestError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (422, UnprocessableEntityError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (418, APIStatusError),  # unknown 4xx falls back to base class
    ],
)
def test_to_api_error_dispatches_correct_subclass(status: int, expected_cls: type) -> None:
    exc = to_api_error(_fake_response(status))
    assert isinstance(exc, expected_cls)
    assert exc.status_code == status


def test_to_api_error_extracts_message_from_envelope() -> None:
    body = {"error": {"message": "quota exceeded", "code": "rate_limit"}}
    exc = to_api_error(_fake_response(429, body))
    assert "quota exceeded" in str(exc)
    assert exc.code == "rate_limit"


def test_to_api_error_falls_back_to_generic_message_when_no_envelope() -> None:
    exc = to_api_error(_fake_response(503))
    assert "503" in str(exc)


def test_api_status_error_is_catchable_as_base_class() -> None:
    exc = to_api_error(_fake_response(404))
    assert isinstance(exc, APIStatusError)


# ---------------------------------------------------------------------------
# Retry logic — sync
# ---------------------------------------------------------------------------


@respx.mock
def test_retries_on_500_then_succeeds(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    route = respx.get(f"{API_BASE}/agents").mock(
        side_effect=[
            httpx.Response(500, json={"error": {"message": "internal error"}}),
            httpx.Response(200, json={"agents": []}),
        ]
    )

    result = client.agents.list()

    assert result.agents == []
    assert route.call_count == 2


@respx.mock
def test_retries_on_429_and_honours_retry_after(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    route = respx.get(f"{API_BASE}/agents").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "1"}, json={}),
            httpx.Response(200, json={"agents": []}),
        ]
    )

    result = client.agents.list()

    assert result.agents == []
    assert route.call_count == 2
    assert slept == [1.0]


@respx.mock
def test_raises_after_max_retries_exhausted(client: Gumloop, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    respx.get(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(500, json={"error": {"message": "still broken"}})
    )

    with pytest.raises(ServerError):
        client.agents.list()


@respx.mock
def test_does_not_retry_on_client_errors(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(404, json={})
    )

    with pytest.raises(NotFoundError):
        client.agents.list()

    assert route.call_count == 1


@respx.mock
def test_no_retry_client_zero_max_retries() -> None:
    client = Gumloop(access_token="token", max_retries=0)
    route = respx.get(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(500, json={})
    )

    with pytest.raises(ServerError):
        client.agents.list()

    assert route.call_count == 1


@respx.mock
def test_retry_after_http_date_is_parsed(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    # Use a date far in the future so the computed delta is clearly > 0.
    future_date = "Wed, 01 Jan 2099 00:00:00 GMT"
    respx.get(f"{API_BASE}/agents").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": future_date}, json={}),
            httpx.Response(200, json={"agents": []}),
        ]
    )

    client.agents.list()

    assert len(slept) == 1
    assert slept[0] > 0  # parsed as a positive delay, not silently dropped


@respx.mock
def test_post_does_not_retry_on_5xx(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    # POST is non-idempotent; a 5xx after a commit would duplicate the write.
    monkeypatch.setattr(time, "sleep", lambda _: None)

    route = respx.post(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(500, json={"error": {"message": "upstream error"}})
    )

    with pytest.raises(ServerError):
        client.agents.create(name="Test", model_name="auto")

    assert route.call_count == 1  # no retries


@respx.mock
def test_post_does_retry_on_429(monkeypatch: pytest.MonkeyPatch, client: Gumloop) -> None:
    # 429 is safe to retry even for POST — the server rejected it before processing.
    monkeypatch.setattr(time, "sleep", lambda _: None)

    route = respx.post(f"{API_BASE}/agents").mock(
        side_effect=[
            httpx.Response(429, json={}),
            httpx.Response(201, json={"agent": {"id": "a1", "name": "Test"}}),
        ]
    )

    result = client.agents.create(name="Test", model_name="auto")

    assert result.agent.id == "a1"
    assert route.call_count == 2


# ---------------------------------------------------------------------------
# Retry logic — async
# ---------------------------------------------------------------------------


@respx.mock
def test_async_retries_on_500_then_succeeds() -> None:
    respx.get(f"{API_BASE}/agents").mock(
        side_effect=[
            httpx.Response(500, json={"error": {"message": "internal error"}}),
            httpx.Response(200, json={"agents": []}),
        ]
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            result = await client.agents.list()
            assert result.agents == []

    asyncio.run(run())


@respx.mock
def test_async_raises_after_max_retries_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    respx.get(f"{API_BASE}/agents").mock(
        return_value=httpx.Response(503, json={})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            with pytest.raises(ServerError):
                await client.agents.list()

    asyncio.run(run())
