from __future__ import annotations

# pyright: reportTypedDictNotRequiredAccess=false
import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE


@respx.mock
def test_artifacts_list_uses_per_agent_path_and_forwards_filters(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/agents/agent_xyz/artifacts").mock(
        return_value=httpx.Response(
            200,
            json={"artifacts": [{"id": "artifact_123"}], "next_cursor": "next"},
        )
    )

    result = client.artifacts.list(
        "agent_xyz",
        interaction_id="session_999",
        page_size=10,
        cursor="prev",
    )

    assert result == {"artifacts": [{"id": "artifact_123"}], "next_cursor": "next"}
    params = route.calls[0].request.url.params
    assert params["interaction_id"] == "session_999"
    assert params["page_size"] == "10"
    assert params["cursor"] == "prev"
    assert "search_query" not in params
    assert "sort_order" not in params


@respx.mock
def test_artifacts_download_forwards_version_id_query_param(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/artifacts/artifact_123/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "download_url": "https://signed.example/payload",
                "filename": "report.pdf",
                "media_type": "application/pdf",
                "size": 4096,
            },
        )
    )

    result = client.artifacts.download("artifact_123", version_id="v_42")

    assert result["download_url"] == "https://signed.example/payload"
    assert result["filename"] == "report.pdf"
    assert result["size"] == 4096
    assert route.calls[0].request.url.params["version_id"] == "v_42"

    client.artifacts.download("artifact_123")
    assert "version_id" not in route.calls[1].request.url.params


@respx.mock
def test_async_artifacts_methods() -> None:
    respx.get(f"{API_BASE}/agents/agent_xyz/artifacts").mock(
        return_value=httpx.Response(200, json={"artifacts": [], "next_cursor": None})
    )
    respx.get(f"{API_BASE}/artifacts/artifact_123/download").mock(
        return_value=httpx.Response(
            200,
            json={
                "download_url": "https://signed.example/payload",
                "filename": "report.pdf",
                "media_type": "application/pdf",
            },
        )
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            listed = await client.artifacts.list("agent_xyz", page_size=5)
            assert listed["artifacts"] == []
            downloaded = await client.artifacts.download("artifact_123")
            assert downloaded["download_url"] == "https://signed.example/payload"

    asyncio.run(run())
