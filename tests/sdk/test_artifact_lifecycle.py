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
            "consent_version_id": "consent-version",
            "scripts": {"data": {"tools": []}},
        },
    )
    name = respx.put(f"{API_BASE}/artifacts/file/name").respond(200, json={"name": None})
    versions = respx.get(f"{API_BASE}/artifacts/file/versions").respond(
        200, json={"versions": [{"version_id": "version", "major_version": 2, "is_current": True}]}
    )
    restore = respx.post(f"{API_BASE}/artifacts/file/restore").respond(
        202, json={"status": "queued", "version_id": "version", "publish_id": "publish"}
    )
    hosting_get = respx.get(f"{API_BASE}/artifacts/file/hosting").respond(200, json={"enabled": False, "alias": None})
    hosting_post = respx.post(f"{API_BASE}/artifacts/file/hosting").respond(
        200, json={"enabled": True, "alias": "alias"}
    )
    hosting_put = respx.put(f"{API_BASE}/artifacts/file/hosting").respond(200, json={"enabled": True, "alias": "new"})
    hosting_delete = respx.delete(f"{API_BASE}/artifacts/file/hosting").respond(
        200, json={"enabled": False, "alias": "new"}
    )
    acknowledge = respx.post(f"{API_BASE}/artifacts/file/acknowledgements").respond(204)
    execute = respx.post(f"{API_BASE}/artifacts/file/execute").respond(200, json=[1, 2])
    delete = respx.delete(f"{API_BASE}/artifacts/file").respond(200, json={"deleted": True})

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            detail = await client.artifacts.retrieve("file", version_id="version")
            assert detail.scripts == {"data": {"tools": []}}
            assert detail.consent_version_id == "consent-version"
            assert (await client.artifacts.rename("file", None)).name is None
            assert (await client.artifacts.list_versions("file")).versions[0].is_current
            assert (await client.artifacts.restore("file", "version")).status == "queued"
            assert not (await client.artifacts.get_hosting("file")).enabled
            assert (await client.artifacts.enable_hosting("file", alias="alias")).enabled
            assert (await client.artifacts.rename_hosting("file", "new")).alias == "new"
            assert not (await client.artifacts.disable_hosting("file")).enabled
            await client.artifacts.acknowledge_integrations("file", "version")
            assert await client.artifacts.execute_script("file", "data", payload=[3], version_id="version") == [1, 2]
            assert (await client.artifacts.delete("file")).deleted

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            detail = client.artifacts.retrieve("file", version_id="version")
            assert detail.scripts == {"data": {"tools": []}}
            assert detail.consent_version_id == "consent-version"
            assert client.artifacts.rename("file", None).name is None
            assert client.artifacts.list_versions("file").versions[0].is_current
            assert client.artifacts.restore("file", "version").status == "queued"
            assert not client.artifacts.get_hosting("file").enabled
            assert client.artifacts.enable_hosting("file", alias="alias").enabled
            assert client.artifacts.rename_hosting("file", "new").alias == "new"
            assert not client.artifacts.disable_hosting("file").enabled
            client.artifacts.acknowledge_integrations("file", "version")
            assert client.artifacts.execute_script("file", "data", payload=[3], version_id="version") == [1, 2]
            assert client.artifacts.delete("file").deleted
    assert metadata.calls[0].request.url.params["version_id"] == "version"
    assert json.loads(name.calls[0].request.content) == {"name": None}
    assert versions.called and restore.called and delete.called
    assert all(route.called for route in (hosting_get, hosting_post, hosting_put, hosting_delete))
    assert json.loads(acknowledge.calls[0].request.content) == {"ack_type": "integrations", "version_id": "version"}
    assert json.loads(execute.calls[0].request.content) == {"key": "data", "payload": [3], "download": False}
    assert execute.calls[0].request.url.params["version_id"] == "version"
    assert execute.calls[0].request.headers["x-auth-key"] == "actor"


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_artifact_binary_scope_and_limits(asynchronous: bool) -> None:
    content = respx.get(f"{API_BASE}/artifacts/file/content").respond(200, content=b"binary\x00\xff")
    output = respx.post(f"{API_BASE}/artifacts/file/execute").respond(200, content=b"export\x00\xff")

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert (await client.artifacts.content("file", version_id="version")).content == b"binary\x00\xff"
            assert (
                await client.artifacts.download_script("file", "export", version_id="version")
            ).content == b"export\x00\xff"
            with pytest.raises(ResponseSizeExceededError):
                await client.artifacts.content("file", max_bytes=1)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert client.artifacts.content("file", version_id="version").content == b"binary\x00\xff"
            assert client.artifacts.download_script("file", "export", version_id="version").content == b"export\x00\xff"
            with pytest.raises(ResponseSizeExceededError):
                client.artifacts.content("file", max_bytes=1)
    for route in (content, output):
        assert route.calls[0].request.url.params["team_id"] == "team"
        assert route.calls[0].request.url.params["version_id"] == "version"
        assert route.calls[0].request.headers["Authorization"] == "Bearer key"
    assert json.loads(output.calls[0].request.content)["download"] is True
