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


@respx.mock
def test_mcp_list_and_read_resources(client: Gumloop) -> None:
    list_route = respx.get(f"{API_BASE}/mcp/servers/gmail/resources").mock(
        return_value=httpx.Response(
            200,
            json={
                "resources": [
                    {
                        "uri": "gmail://label/INBOX",
                        "name": "Inbox",
                        "description": "Primary",
                        "mime_type": "application/json",
                        "server_id": "gmail",
                    }
                ],
                "server_id": "gmail",
                "status": "connected",
                "next_cursor": "c2",
            },
        )
    )
    read_route = respx.get(f"{API_BASE}/mcp/servers/gmail/resources/read").mock(
        return_value=httpx.Response(
            200,
            json={
                "server_id": "gmail",
                "uri": "gmail://label/INBOX",
                "contents": [{"mime_type": "text/plain", "text": "a"}, {"text": "b"}],
            },
        )
    )

    listed = client.mcp.list_resources("gmail", cursor="c1", team_id="team_123")
    assert listed.resources[0].uri == "gmail://label/INBOX"
    assert listed.resources[0].mime_type == "application/json"
    assert listed.next_cursor == "c2"
    assert list_route.calls[0].request.url.params["cursor"] == "c1"
    assert list_route.calls[0].request.url.params["team_id"] == "team_123"

    read = client.mcp.get_resource("gmail", "gmail://label/INBOX", team_id="team_123")
    assert read.text == "a\nb"  # the .text convenience joins text contents
    assert read_route.calls[0].request.url.params["uri"] == "gmail://label/INBOX"


@respx.mock
def test_mcp_list_and_get_prompts(client: Gumloop) -> None:
    list_route = respx.get(f"{API_BASE}/mcp/servers/gmail/prompts").mock(
        return_value=httpx.Response(
            200,
            json={
                "prompts": [
                    {
                        "name": "summarize",
                        "description": "d",
                        "arguments": [{"name": "thread_id", "required": True}],
                        "server_id": "gmail",
                    }
                ],
                "server_id": "gmail",
                "status": "connected",
            },
        )
    )
    get_route = respx.post(f"{API_BASE}/mcp/servers/gmail/prompts/get").mock(
        return_value=httpx.Response(
            200,
            json={
                "server_id": "gmail",
                "name": "summarize",
                "description": "d",
                "messages": [{"role": "user", "content": {"type": "text", "text": "hello"}}],
            },
        )
    )

    listed = client.mcp.list_prompts("gmail", team_id="team_123")
    assert listed.prompts[0].name == "summarize"
    assert listed.prompts[0].arguments[0].required is True
    assert list_route.calls[0].request.url.params["team_id"] == "team_123"

    got = client.mcp.get_prompt("gmail", "summarize", {"thread_id": "abc"}, team_id="team_123")
    assert got.messages[0].content["text"] == "hello"
    assert request_json(get_route.calls[0].request) == {
        "name": "summarize",
        "arguments": {"thread_id": "abc"},
        "team_id": "team_123",
    }


@respx.mock
def test_mcp_get_prompt_omits_team_id_when_absent(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/mcp/servers/gmail/prompts/get").mock(
        return_value=httpx.Response(200, json={"server_id": "gmail", "name": "summarize", "messages": []})
    )

    client.mcp.get_prompt("gmail", "summarize")

    assert request_json(route.calls[0].request) == {"name": "summarize", "arguments": {}}


@respx.mock
def test_async_mcp_resource_and_prompt_methods() -> None:
    respx.get(f"{API_BASE}/mcp/servers/gmail/resources").mock(
        return_value=httpx.Response(200, json={"resources": [], "server_id": "gmail", "status": "connected"})
    )
    respx.get(f"{API_BASE}/mcp/servers/gmail/resources/read").mock(
        return_value=httpx.Response(200, json={"server_id": "gmail", "uri": "u", "contents": [{"text": "x"}]})
    )
    respx.get(f"{API_BASE}/mcp/servers/gmail/prompts").mock(
        return_value=httpx.Response(200, json={"prompts": [], "server_id": "gmail", "status": "connected"})
    )
    respx.post(f"{API_BASE}/mcp/servers/gmail/prompts/get").mock(
        return_value=httpx.Response(200, json={"server_id": "gmail", "name": "p", "messages": []})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.mcp.list_resources("gmail", team_id="t")).resources == []
            assert (await client.mcp.get_resource("gmail", "u", team_id="t")).text == "x"
            assert (await client.mcp.list_prompts("gmail", team_id="t")).prompts == []
            assert (await client.mcp.get_prompt("gmail", "p", {"a": 1}, team_id="t")).name == "p"

    asyncio.run(run())
