from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop._http import ResponseSizeExceededError
from gumloop.resources.workflows import WorkflowExecutionError
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("oauth", [False, True])
@respx.mock
def test_personal_workflow_auth_and_legacy_responses(asynchronous: bool, oauth: bool) -> None:
    start = respx.post(f"{API_BASE}/start_pipeline").respond(200, json={"run_id": "run", "url": "https://example/run"})
    state = respx.get(f"{API_BASE}/get_pl_run").respond(200, json={"state": "DONE", "outputs": {"Output": "ok"}})

    async def run() -> None:
        async with AsyncGumloop(
            access_token="oauth_token" if oauth else None,
            api_key=None if oauth else "key",
            user_id=None if oauth else "actor",
        ) as client:
            started = await client.workflows.start("tab")
            assert started.saved_item_id == "tab" and started.run_id == "run"
            assert (await client.workflows.wait(started.run_id)).run_id == "run"

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(
            access_token="oauth_token" if oauth else None,
            api_key=None if oauth else "key",
            user_id=None if oauth else "actor",
        ) as client:
            started = client.workflows.start("tab")
            assert started.saved_item_id == "tab" and started.run_id == "run"
            assert client.workflows.wait(started.run_id).run_id == "run"
    for route in (start, state):
        headers = route.calls[0].request.headers
        assert headers["authorization"] == f"Bearer {'oauth_token' if oauth else 'key'}"
        assert headers.get("x-auth-key") == (None if oauth else "actor")
    assert "user_id" not in json.loads(start.calls[0].request.content)
    assert "user_id" not in state.calls[0].request.url.params


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_workflow_discovery_run_and_scope(asynchronous: bool) -> None:
    listings = respx.get(f"{API_BASE}/list_saved_items").respond(
        200, json={"saved_items": [{"saved_item_id": "tab", "name": "Echo"}]}
    )
    books = respx.get(f"{API_BASE}/list_workbooks").respond(
        200,
        json={
            "workbooks": [
                {"workbook_id": "book", "name": "Workbook", "saved_items": [{"saved_item_id": "tab", "name": "Echo"}]}
            ]
        },
    )
    inputs = respx.get(f"{API_BASE}/get_inputs").respond(200, json={"inputs": [{"name": "Input", "type": "string"}]})
    start = respx.post(f"{API_BASE}/start_pipeline").respond(200, json={"run_id": "run", "saved_item_id": "tab"})
    state = respx.get(f"{API_BASE}/get_pl_run").mock(
        side_effect=[
            httpx.Response(200, json={"run_id": "run", "state": "RUNNING"}),
            httpx.Response(200, json={"run_id": "run", "state": "DONE", "outputs": {"Output": "hello"}}),
        ]
    )
    cancel = respx.post(f"{API_BASE}/kill_pipeline").respond(200, json={"success": True, "run_id": "run"})

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert (await client.workflows.list(project_id="project")).saved_items[0].saved_item_id == "tab"
            assert (await client.workflows.list_workbooks(project_id="project")).workbooks[0].saved_items[
                0
            ].name == "Echo"
            assert (await client.workflows.inputs("tab", project_id="project")).inputs[0]["name"] == "Input"
            assert (
                await client.workflows.run("tab", {"Input": "hello"}, project_id="project", poll_interval=0)
            ).outputs == {"Output": "hello"}
            assert (await client.workflows.cancel_run("run", project_id="project")).success

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert client.workflows.list(project_id="project").saved_items[0].saved_item_id == "tab"
            assert client.workflows.list_workbooks(project_id="project").workbooks[0].saved_items[0].name == "Echo"
            assert client.workflows.inputs("tab", project_id="project").inputs[0]["name"] == "Input"
            assert client.workflows.run("tab", {"Input": "hello"}, project_id="project", poll_interval=0).outputs == {
                "Output": "hello"
            }
            assert client.workflows.cancel_run("run", project_id="project").success
    for route in (listings, books, inputs, state):
        assert route.calls[0].request.url.params["project_id"] == "project"
    assert json.loads(start.calls[0].request.content) == {
        "saved_item_id": "tab",
        "pipeline_inputs": [{"input_name": "Input", "value": "hello"}],
        "project_id": "project",
    }
    assert json.loads(cancel.calls[0].request.content)["project_id"] == "project"
    assert start.calls[0].request.url.params["team_id"] == "team"


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("state", ["FAILED", "TERMINATING", "TERMINATED"])
@respx.mock
def test_workflow_wait_terminal_error_and_immediate_timeout(asynchronous: bool, state: str) -> None:
    route = respx.get(f"{API_BASE}/get_pl_run").respond(200, json={"run_id": "run", "state": state})

    async def run() -> None:
        async with AsyncGumloop(api_key="key") as client:
            with pytest.raises(WorkflowExecutionError) as error:
                await client.workflows.wait("run")
            assert error.value.run.state == state
            with pytest.raises(TimeoutError):
                await client.workflows.wait("run", timeout=0)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            with pytest.raises(WorkflowExecutionError) as error:
                client.workflows.wait("run")
            assert error.value.run.state == state
            with pytest.raises(TimeoutError):
                client.workflows.wait("run", timeout=0)
    assert route.call_count == 1


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_workflow_files_roundtrip_partial_and_bounded_download(asynchronous: bool) -> None:
    content = b"binary\x00\xff"
    upload = respx.post(f"{API_BASE}/upload_file").respond(200, json={"success": True, "file_name": "stored"})
    bulk_upload = respx.post(f"{API_BASE}/upload_files").respond(
        207, json={"partial_success": True, "uploaded_files": ["stored"], "failed_files": ["bad"]}
    )
    download = respx.post(f"{API_BASE}/download_file").respond(
        200, content=content, headers={"Content-Type": "application/octet-stream"}
    )
    archive = respx.post(f"{API_BASE}/download_files").respond(
        200, content=b"ZIP", headers={"Content-Type": "application/zip"}
    )

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert (
                await client.workflows.upload_file("input.bin", content, project_id="project")
            ).file_name == "stored"
            assert (await client.workflows.upload_files({"input.bin": content}, project_id="project")).failed_files == [
                "bad"
            ]
            assert (
                await client.workflows.download_file("stored", project_id="project", run_id="run")
            ).content == content
            assert (await client.workflows.download_files(["a", "b"], project_id="project")).content == b"ZIP"
            with pytest.raises(ResponseSizeExceededError):
                await client.workflows.download_file("stored", max_bytes=1)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert client.workflows.upload_file("input.bin", content, project_id="project").file_name == "stored"
            assert client.workflows.upload_files({"input.bin": content}, project_id="project").failed_files == ["bad"]
            assert client.workflows.download_file("stored", project_id="project", run_id="run").content == content
            assert client.workflows.download_files(["a", "b"], project_id="project").content == b"ZIP"
            with pytest.raises(ResponseSizeExceededError):
                client.workflows.download_file("stored", max_bytes=1)
    assert base64.b64decode(json.loads(upload.calls[0].request.content)["file_content"]) == content
    assert json.loads(bulk_upload.calls[0].request.content)["project_id"] == "project"
    assert download.calls[0].request.url.params["team_id"] == "team"
    assert json.loads(download.calls[0].request.content)["run_id"] == "run"
    assert json.loads(archive.calls[0].request.content)["file_names"] == ["a", "b"]
