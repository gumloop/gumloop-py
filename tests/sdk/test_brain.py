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


_SOURCE = {
    "id": "src_1",
    "name": "Docs",
    "source_type": "direct_file_uploads",
    "status": "active",
    "scope": "personal",
    "team_id": None,
    "created_at": "2026-09-25T20:00:00+00:00",
}
_FILE = {
    "id": "file_1",
    "file_name": "handbook.txt",
    "mime_type": "text/plain",
    "size_bytes": 125,
    "sha256": "9bae5b3a",
    "status": "indexed",
    "document_id": "file:file_1",
}


@respx.mock
def test_brain_list_sources_forwards_filters_and_drops_unset(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/brain/sources").mock(
        return_value=httpx.Response(200, json={"sources": [_SOURCE], "next_cursor": None})
    )

    result = client.brain.list_sources(scope="personal", page_size=10)

    assert dict(route.calls[0].request.url.params) == {"scope": "personal", "page_size": "10"}
    assert result.sources[0].id == "src_1"


@respx.mock
def test_brain_create_source_posts_only_set_fields(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/brain/sources").mock(return_value=httpx.Response(201, json={"source": _SOURCE}))

    client.brain.create_source("Docs", scope="team", team_id="team_1")

    assert request_json(route.calls[0].request) == {"name": "Docs", "scope": "team", "team_id": "team_1"}


@respx.mock
def test_brain_upload_files_posts_multipart_and_parses_rejections(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/brain/sources/src_1/files").mock(
        return_value=httpx.Response(
            201,
            json={
                "files": [_FILE],
                "rejected": [{"file_name": "bad.exe", "error": 'unsupported file type ".exe"'}],
                "sync_run_id": "run_1",
            },
        )
    )

    result = client.brain.upload_files("src_1", [("handbook.txt", b"hello", "text/plain"), ("bad.exe", b"nope")])

    body = route.calls[0].request.content
    assert b"handbook.txt" in body and b"hello" in body and b"bad.exe" in body
    assert route.calls[0].request.headers["content-type"].startswith("multipart/form-data")
    assert result.files[0].sha256 == "9bae5b3a"
    assert result.rejected[0].file_name == "bad.exe"
    assert result.sync_run_id == "run_1"


@respx.mock
def test_brain_estimate_is_null_before_first_run(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/brain/sources/src_1/estimate").mock(
        return_value=httpx.Response(200, json={"source_id": "src_1", "status": "draft", "estimate": None})
    )

    result = client.brain.get_estimate("src_1")

    assert result.status == "draft"
    assert result.estimate is None


@respx.mock
def test_brain_delete_file_and_approve_hit_item_routes(client: Gumloop) -> None:
    delete_route = respx.delete(f"{API_BASE}/brain/sources/src_1/files/file_1").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    approve_route = respx.post(f"{API_BASE}/brain/sources/src_1/approve").mock(
        return_value=httpx.Response(200, json={"source": {**_SOURCE, "status": "active"}})
    )

    assert client.brain.delete_file("src_1", "file_1").deleted is True
    assert client.brain.approve_source("src_1").source.status == "active"
    assert delete_route.called and approve_route.called


@respx.mock
def test_async_brain_list_files(async_client: AsyncGumloop) -> None:
    respx.get(f"{API_BASE}/brain/sources/src_1/files").mock(
        return_value=httpx.Response(200, json={"files": [_FILE], "next_cursor": "abc"})
    )

    result = asyncio.run(async_client.brain.list_files("src_1"))

    assert result.files[0].file_name == "handbook.txt"
    assert result.next_cursor == "abc"
