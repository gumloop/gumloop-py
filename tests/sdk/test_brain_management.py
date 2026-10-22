from __future__ import annotations

import asyncio

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import APIStatusError
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_brain_source_operations_and_pagination(asynchronous: bool):
    sync = respx.post(f"{API_BASE}/brain/sources/source/sync").respond(
        202,
        json={"source_id": "source", "status": "queued", "sync_run_id": "run"},
    )
    history = respx.get(f"{API_BASE}/brain/sources/source/sync-runs").respond(
        200,
        json={
            "items": [
                {
                    "sync_run_id": "run",
                    "connector_id": "source",
                    "status": "queued",
                    "trigger": "manual",
                    "sync_mode": "delta",
                    "coverage_status": "unknown",
                    "budget_status": "within_budget",
                    "require_approval": True,
                }
            ],
            "next_cursor": "more",
        },
    )
    issues = respx.get(f"{API_BASE}/brain/sources/source/issues").respond(
        200, json={"items": [{"source_item_key": "opaque", "status": "skipped", "details_hidden": True}]}
    )
    children = respx.get(f"{API_BASE}/brain/sources/source/children").respond(
        200,
        json={
            "connector_id": "source",
            "items": [
                {"document_id": "doc", "title": "Visible", "kind": "leaf", "is_document": True, "status": "indexed"}
            ],
            "total_count": None,
        },
    )

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            assert (await client.brain.sync_source("source")).status == "queued"
            assert (await client.brain.list_sync_runs("source", page_size=1, cursor="page")).items[0].require_approval
            assert (await client.brain.list_source_issues("source")).items[0].details_hidden
            assert (
                await client.brain.list_source_children("source", parent_id="parent", query="Visible", page_size=10)
            ).total_count is None

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            assert client.brain.sync_source("source").status == "queued"
            assert client.brain.list_sync_runs("source", page_size=1, cursor="page").items[0].require_approval
            assert client.brain.list_source_issues("source").items[0].details_hidden
            assert (
                client.brain.list_source_children(
                    "source", parent_id="parent", query="Visible", page_size=10
                ).total_count
                is None
            )
    assert sync.called and issues.called
    assert dict(history.calls[0].request.url.params) == {"page_size": "1", "cursor": "page"}
    assert dict(children.calls[0].request.url.params) == {"parent_id": "parent", "query": "Visible", "page_size": "10"}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_brain_management_permission_errors_propagate(asynchronous: bool):
    respx.get(f"{API_BASE}/brain/sources/source/sync-runs").respond(
        403, json={"error": {"code": "insufficient_permissions", "message": "Denied"}}
    )

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            with pytest.raises(APIStatusError) as error:
                await client.brain.list_sync_runs("source")
            assert error.value.status_code == 403

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            with pytest.raises(APIStatusError) as error:
                client.brain.list_sync_runs("source")
            assert error.value.status_code == 403
