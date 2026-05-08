from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.types import McpToolCall
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@respx.mock
def test_mcp_list_servers_and_get_server_routes(client: Gumloop) -> None:
    list_route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    get_route = respx.get(f"{API_BASE}/mcp/servers/gmail").mock(
        return_value=httpx.Response(200, json={"server": {"server_id": "gmail"}})
    )

    assert client.mcp.list_servers(team_id="team_123") == {"servers": []}
    assert client.mcp.get_server("gmail", team_id="team_123") == {"server": {"server_id": "gmail"}}
    assert list_route.calls[0].request.url.params["team_id"] == "team_123"
    assert get_route.calls[0].request.url.params["team_id"] == "team_123"


@respx.mock
def test_mcp_list_tools_serializes_tool_call_ids(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/mcp/tools").mock(return_value=httpx.Response(200, json={"tools": []}))

    result = client.mcp.list_tools(
        team_id="team_123",
        server_id="gmail",
        tool_call_ids=["gmail__read_emails", "slack__send_message"],
    )

    assert result == {"tools": []}
    params = route.calls[0].request.url.params
    assert params["team_id"] == "team_123"
    assert params["server_id"] == "gmail"
    assert params["tool_call_ids"] == "gmail__read_emails,slack__send_message"


@respx.mock
def test_mcp_execute_single_and_many_bodies(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/mcp/tools/execute").mock(return_value=httpx.Response(200, json={"results": []}))

    assert client.mcp.execute(
        "gmail__read_emails",
        {"max_results": 5},
        team_id="team_123",
    ) == {"results": []}
    assert request_json(route.calls[0].request) == {
        "tool_call_id": "gmail__read_emails",
        "team_id": "team_123",
        "arguments": {"max_results": 5},
    }

    tool_calls: list[McpToolCall] = [
        {
            "ref": "emails",
            "tool_call_id": "gmail__read_emails",
            "arguments": {"max_results": 5},
        }
    ]
    assert client.mcp.execute_many(tool_calls, team_id="team_123") == {"results": []}
    assert request_json(route.calls[1].request) == {
        "team_id": "team_123",
        "tool_calls": tool_calls,
    }


@respx.mock
def test_async_mcp_methods() -> None:
    respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    respx.get(f"{API_BASE}/mcp/servers/gmail").mock(
        return_value=httpx.Response(200, json={"server": {"server_id": "gmail"}})
    )
    respx.get(f"{API_BASE}/mcp/tools").mock(return_value=httpx.Response(200, json={"tools": []}))
    respx.post(f"{API_BASE}/mcp/tools/execute").mock(return_value=httpx.Response(200, json={"results": []}))

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert await client.mcp.list_servers(team_id="team_123") == {"servers": []}
            assert await client.mcp.get_server("gmail", team_id="team_123") == {"server": {"server_id": "gmail"}}
            assert await client.mcp.list_tools(server_id="gmail", team_id="team_123") == {"tools": []}
            assert await client.mcp.execute(
                "gmail__read_emails",
                {"max_results": 5},
                team_id="team_123",
            ) == {"results": []}
            assert await client.mcp.execute_many(
                [{"ref": "emails", "tool_call_id": "gmail__read_emails", "arguments": {}}],
                team_id="team_123",
            ) == {"results": []}

    asyncio.run(run())
