from __future__ import annotations

import asyncio
import json

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop._http import ResponseSizeExceededError
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_artifact_lifecycle_wire_contract(asynchronous: bool) -> None:
    metadata = respx.get(f"{API_BASE}/artifacts/file").respond(
        200,
        json={
            "id": "file",
            "version_id": "version",
            "size": 123,
            "media_type": "text/plain",
        },
    )
    name = respx.put(f"{API_BASE}/artifacts/file/name").respond(200, json={"name": None})
    versions = respx.get(f"{API_BASE}/artifacts/file/versions").respond(
        200, json={"versions": [{"version_id": "version", "major_version": 2, "is_current": True}]}
    )
    delete = respx.delete(f"{API_BASE}/artifacts/file").respond(200, json={"deleted": True})

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            detail = await client.artifacts.retrieve("file", version_id="version")
            assert detail.size == 123
            assert detail.media_type == "text/plain"
            assert (await client.artifacts.rename("file", None)).name is None
            assert (await client.artifacts.list_versions("file")).versions[0].is_current
            assert (await client.artifacts.delete("file")).deleted

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            detail = client.artifacts.retrieve("file", version_id="version")
            assert detail.size == 123
            assert detail.media_type == "text/plain"
            assert client.artifacts.rename("file", None).name is None
            assert client.artifacts.list_versions("file").versions[0].is_current
            assert client.artifacts.delete("file").deleted
    assert metadata.calls[0].request.url.params["version_id"] == "version"
    assert json.loads(name.calls[0].request.content) == {"name": None}
    assert versions.called and delete.called


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_artifact_binary_scope_and_limits(asynchronous: bool) -> None:
    content = respx.get(f"{API_BASE}/artifacts/file/content").respond(200, content=b"binary\x00\xff")

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert (await client.artifacts.content("file", version_id="version")).content == b"binary\x00\xff"
            with pytest.raises(ResponseSizeExceededError):
                await client.artifacts.content("file", max_bytes=1)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert client.artifacts.content("file", version_id="version").content == b"binary\x00\xff"
            with pytest.raises(ResponseSizeExceededError):
                client.artifacts.content("file", max_bytes=1)
    assert content.calls[0].request.url.params["team_id"] == "team"
    assert content.calls[0].request.url.params["version_id"] == "version"
    assert content.calls[0].request.headers["Authorization"] == "Bearer key"
