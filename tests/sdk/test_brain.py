from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

_RESULT = {
    "document_id": "notion:doc_1",
    "source": "notion",
    "title": "Onboarding",
    "content": "How we onboard new teammates.",
    "url": "https://notion.so/doc_1",
    "score": 0.87,
    "updated_at": "2026-01-02T03:04:05+00:00",
    "owner_name": "Ada",
}


@respx.mock
def test_brain_search_posts_query_and_drops_unset_fields(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": [_RESULT]}))

    result = client.brain.search("onboarding")

    assert request_json(route.calls[0].request) == {"query": "onboarding"}
    assert len(result.results) == 1
    assert result.results[0].title == "Onboarding"
    assert result.results[0].source == "notion"
    assert result.results[0].score == 0.87


@respx.mock
def test_brain_search_forwards_limit_and_source_type(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": []}))

    result = client.brain.search("pricing", limit=5, source_type=["notion", "slack"])

    assert request_json(route.calls[0].request) == {
        "query": "pricing",
        "limit": 5,
        "source_type": ["notion", "slack"],
    }
    assert result.results == []


def test_brain_search_rejects_empty_source_type(client: Gumloop) -> None:
    with pytest.raises(ValidationError):
        client.brain.search("pricing", source_type=[])


@respx.mock
def test_brain_search_passes_through_unknown_kwargs(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": []}))

    client.brain.search("q", future_param="x")

    assert request_json(route.calls[0].request) == {"query": "q", "future_param": "x"}


@respx.mock
def test_async_brain_search_mirrors_sync(async_client: AsyncGumloop) -> None:
    route = respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": [_RESULT]}))

    result = asyncio.run(async_client.brain.search("onboarding", limit=3))

    assert request_json(route.calls[0].request) == {"query": "onboarding", "limit": 3}
    assert result.results[0].document_id == "notion:doc_1"
