from __future__ import annotations

import asyncio
import json

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_artifact_lifecycle_wire_contract(asynchronous: bool) -> None:
    name = respx.put(f"{API_BASE}/artifacts/file/name").respond(200, json={"name": None})
    versions = respx.get(f"{API_BASE}/artifacts/file/versions").respond(
        200, json={"versions": [{"version_id": "version", "major_version": 2, "is_current": True}]}
    )
    delete = respx.delete(f"{API_BASE}/artifacts/file").respond(200, json={"deleted": True})

    async def run() -> None:
        async with AsyncGumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert (await client.artifacts.rename("file", None)).name is None
            assert (await client.artifacts.list_versions("file")).versions[0].is_current
            assert (await client.artifacts.delete("file")).deleted

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id="team") as client:
            assert client.artifacts.rename("file", None).name is None
            assert client.artifacts.list_versions("file").versions[0].is_current
            assert client.artifacts.delete("file").deleted
    assert json.loads(name.calls[0].request.content) == {"name": None}
    assert versions.called and delete.called
