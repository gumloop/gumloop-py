from __future__ import annotations

import asyncio
import json

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import APIStatusError
from tests.sdk.helpers import API_BASE

SOURCE = {"id": "source", "name": "Docs", "source_type": "google_drive", "status": "draft", "scope": "personal"}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_brain_connected_source_configuration_contract(asynchronous: bool):
    create = respx.post(f"{API_BASE}/brain/sources").respond(201, json={"source": SOURCE})
    configuration = respx.get(f"{API_BASE}/brain/sources/source/configuration").respond(
        200,
        json={
            "source": SOURCE,
            "config": {"mode": "all"},
            "credentials_to_use": {"gdrive_access_token": {"secret_id": "selector"}},
            "respect_source_permissions": True,
        },
    )
    update = respx.patch(f"{API_BASE}/brain/sources/source").respond(200, json={"source": SOURCE})
    browse = respx.post(f"{API_BASE}/brain/sources/browse").respond(
        200,
        json={
            "nodes": [{"id": "folder", "name": "Folder", "kind": "container"}],
            "next_cursor": "next",
            "truncated": False,
        },
    )
    credentials = {"gdrive_access_token": {"secret_id": "selector", "is_personal_credential": True}}

    async def run():
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            assert (
                await client.brain.create_source(
                    "Docs", source_type="google_drive", config={"mode": "all"}, credentials_to_use=credentials
                )
            ).source.status == "draft"
            assert (await client.brain.get_source_configuration("source")).config == {"mode": "all"}
            await client.brain.update_source(
                "source", config={"mode": "all", "exclusions": []}, respect_source_permissions=False
            )
            assert (
                await client.brain.browse_source(
                    "google_drive", credentials_to_use=credentials, roots=False, cursor="page"
                )
            ).nodes[0].id == "folder"

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            assert (
                client.brain.create_source(
                    "Docs", source_type="google_drive", config={"mode": "all"}, credentials_to_use=credentials
                ).source.status
                == "draft"
            )
            assert client.brain.get_source_configuration("source").config == {"mode": "all"}
            client.brain.update_source(
                "source", config={"mode": "all", "exclusions": []}, respect_source_permissions=False
            )
            assert (
                client.brain.browse_source("google_drive", credentials_to_use=credentials, roots=False, cursor="page")
                .nodes[0]
                .id
                == "folder"
            )
    assert json.loads(create.calls[0].request.content) == {
        "name": "Docs",
        "source_type": "google_drive",
        "config": {"mode": "all"},
        "credentials_to_use": credentials,
    }
    assert json.loads(update.calls[0].request.content) == {
        "config": {"mode": "all", "exclusions": []},
        "respect_source_permissions": False,
    }
    assert json.loads(browse.calls[0].request.content) == {
        "source_type": "google_drive",
        "credentials_to_use": credentials,
        "roots": False,
        "cursor": "page",
    }
    assert configuration.calls[0].request.headers["x-auth-key"] == "actor"


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("sync_state", ["preparing", "queued"])
@respx.mock
def test_brain_source_operations_and_pagination(asynchronous: bool, sync_state: str):
    sync = respx.post(f"{API_BASE}/brain/sources/source/sync").respond(
        202,
        json={"source_id": "source", "status": sync_state, "sync_run_id": "run" if sync_state == "queued" else None},
    )
    status = respx.patch(f"{API_BASE}/brain/sources/source/status").respond(200, json={"source": SOURCE})
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
            assert (await client.brain.sync_source("source")).status == sync_state
            await client.brain.pause_source("source")
            await client.brain.resume_source("source")
            assert (await client.brain.list_sync_runs("source", page_size=1, cursor="page")).items[0].require_approval
            assert (await client.brain.list_source_issues("source")).items[0].details_hidden
            assert (
                await client.brain.list_source_children("source", parent_id="parent", query="Visible", page_size=10)
            ).total_count is None

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            assert client.brain.sync_source("source").status == sync_state
            client.brain.pause_source("source")
            client.brain.resume_source("source")
            assert client.brain.list_sync_runs("source", page_size=1, cursor="page").items[0].require_approval
            assert client.brain.list_source_issues("source").items[0].details_hidden
            assert (
                client.brain.list_source_children(
                    "source", parent_id="parent", query="Visible", page_size=10
                ).total_count
                is None
            )
    assert sync.called and issues.called
    assert [json.loads(call.request.content) for call in status.calls] == [{"status": "paused"}, {"status": "active"}]
    assert dict(history.calls[0].request.url.params) == {"page_size": "1", "cursor": "page"}
    assert dict(children.calls[0].request.url.params) == {"parent_id": "parent", "query": "Visible", "page_size": "10"}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_brain_management_permission_errors_propagate(asynchronous: bool):
    respx.get(f"{API_BASE}/brain/sources/source/configuration").respond(
        403, json={"error": {"code": "insufficient_permissions", "message": "Denied"}}
    )

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            with pytest.raises(APIStatusError) as error:
                await client.brain.get_source_configuration("source")
            assert error.value.status_code == 403

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            with pytest.raises(APIStatusError) as error:
                client.brain.get_source_configuration("source")
            assert error.value.status_code == 403
