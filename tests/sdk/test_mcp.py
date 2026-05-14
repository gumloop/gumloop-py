from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@respx.mock
def test_mcp_list_servers_and_get_server_routes(client: Gumloop) -> None:
    list_route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    get_route = respx.get(f"{API_BASE}/mcp/servers/gmail").mock(
        return_value=httpx.Response(
            200,
            json={
                "server": {"server_id": "gmail", "type": "gumcp", "status": "ok", "gumloop_auth_url": "u"},
            },
        )
    )

    assert client.mcp.list_servers(team_id="team_123").servers == []
    assert client.mcp.get_server("gmail", team_id="team_123").server.server_id == "gmail"
    assert list_route.calls[0].request.url.params["team_id"] == "team_123"
    assert get_route.calls[0].request.url.params["team_id"] == "team_123"


@respx.mock
def test_mcp_list_tools_uses_server_path(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/mcp/servers/gmail/tools").mock(
        return_value=httpx.Response(200, json={"tools": [], "server_id": "gmail", "status": "connected"})
    )

    result = client.mcp.list_tools("gmail", team_id="team_123")

    assert result.tools == []
    assert result.server_id == "gmail"
    assert result.status == "connected"
    params = route.calls[0].request.url.params
    assert params["team_id"] == "team_123"


@respx.mock
def test_mcp_execute_single_and_many_bodies(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))

    assert (
        client.mcp.execute(
            "gmail",
            "read_emails",
            {"max_results": 5},
            team_id="team_123",
        ).results
        == []
    )
    assert request_json(route.calls[0].request) == {
        "calls": [{"server_id": "gmail", "tool_name": "read_emails", "arguments": {"max_results": 5}}],
        "team_id": "team_123",
    }

    calls = [
        {
            "ref": "emails",
            "server_id": "gmail",
            "tool_name": "read_emails",
            "arguments": {"max_results": 5},
        }
    ]
    assert client.mcp.execute_many(calls, team_id="team_123").results == []
    assert request_json(route.calls[1].request) == {
        "team_id": "team_123",
        "calls": [
            {
                "ref": "emails",
                "server_id": "gmail",
                "tool_name": "read_emails",
                "arguments": {"max_results": 5},
            }
        ],
    }


@respx.mock
def test_mcp_execute_with_ref(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))

    client.mcp.execute("gmail", "read_emails", ref="my_ref")

    call_body = request_json(route.calls[0].request)
    assert call_body["calls"][0]["ref"] == "my_ref"


def test_mcp_execute_many_rejects_empty_calls(client: Gumloop) -> None:
    with pytest.raises(ValueError, match="empty"):
        client.mcp.execute_many([])


@respx.mock
def test_async_mcp_methods() -> None:
    respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    respx.get(f"{API_BASE}/mcp/servers/gmail").mock(
        return_value=httpx.Response(
            200,
            json={
                "server": {"server_id": "gmail", "type": "gumcp", "status": "ok", "gumloop_auth_url": "u"},
            },
        )
    )
    respx.get(f"{API_BASE}/mcp/servers/gmail/tools").mock(
        return_value=httpx.Response(200, json={"tools": [], "server_id": "gmail", "status": "connected"})
    )
    respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.mcp.list_servers(team_id="team_123")).servers == []
            assert (await client.mcp.get_server("gmail", team_id="team_123")).server.server_id == "gmail"
            tools_resp = await client.mcp.list_tools("gmail", team_id="team_123")
            assert tools_resp.tools == []
            assert tools_resp.server_id == "gmail"
            single = await client.mcp.execute(
                "gmail",
                "read_emails",
                {"max_results": 5},
                team_id="team_123",
            )
            assert single.results == []
            batch = await client.mcp.execute_many(
                [{"server_id": "gmail", "tool_name": "read_emails", "arguments": {}}],
                team_id="team_123",
            )
            assert batch.results == []

    asyncio.run(run())
