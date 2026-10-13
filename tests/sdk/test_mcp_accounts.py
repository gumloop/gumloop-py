from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import Mock

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import GumloopError
from gumloop.types import McpExecuteResponse
from gumloop.types import McpToolCallRequest
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _result(ref: str) -> dict:
    return {"ref": ref, "server_id": "gmail", "tool_name": "search", "status": "success", "content": [ref]}


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
async def test_account_calls_use_http_and_preserve_mixed_order(monkeypatch, asynchronous):
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(
        return_value=httpx.Response(200, json={"results": [_result("work"), _result("2")]}),
    )
    transport = Mock()
    direct_result = McpExecuteResponse.model_validate({"results": [_result("0"), _result("last")]})
    transport.execute_many.return_value = direct_result
    transport.execute_many_async = AsyncMock(return_value=direct_result)
    client = AsyncGumloop(access_token="sdk-token") if asynchronous else Gumloop(access_token="sdk-token")
    monkeypatch.setattr(client.mcp, "_direct_transport", lambda: transport)
    calls = [
        {"server_id": "gmail", "tool_name": "search"},
        McpToolCallRequest(server_id="gmail", tool_name="search", account="work-id", ref="work"),
        {"server_id": "gmail", "tool_name": "search", "account": "home-id"},
        {"server_id": "gmail", "tool_name": "search", "ref": "last"},
    ]
    response = await client.mcp.execute_many(calls) if asynchronous else client.mcp.execute_many(calls)
    assert [result.ref for result in response.results] == ["0", "work", "2", "last"]
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer sdk-token"
    assert [call["account"] for call in request_json(request)["calls"]] == ["work-id", "home-id"]
    direct = transport.execute_many_async if asynchronous else transport.execute_many
    assert [call["ref"] for call in direct.call_args.args[0]] == ["0", "last"]
    assert "ref" not in calls[0]


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
async def test_single_account_call_and_listing(monkeypatch, asynchronous):
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(
        return_value=httpx.Response(200, json={"results": [_result("0")]})
    )
    respx.get(f"{API_BASE}/mcp/servers/gmail/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "server_id": "gmail",
                "accounts": [{"id": "work-id", "label": "Work", "in_use": True}],
            },
        )
    )
    client = AsyncGumloop(access_token="sdk-token") if asynchronous else Gumloop(access_token="sdk-token")
    transport = Mock()
    monkeypatch.setattr(client.mcp, "_direct_transport", lambda: transport)
    if asynchronous:
        await client.mcp.execute("gmail", "search", account="work-id")
        accounts = await client.mcp.list_accounts("gmail")
    else:
        client.mcp.execute("gmail", "search", account="work-id")
        accounts = client.mcp.list_accounts("gmail")
    assert request_json(route.calls[0].request)["calls"][0]["account"] == "work-id"
    assert accounts.accounts[0].id == "work-id"
    transport.execute.assert_not_called()
    transport.execute_async.assert_not_called()


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_missing_http_token_fails_before_any_batch_call(monkeypatch, asynchronous):
    client = AsyncGumloop(access_token="temporary") if asynchronous else Gumloop(access_token="temporary")
    client.mcp._client.access_token = None
    transport = Mock()
    monkeypatch.setattr(client.mcp, "_direct_transport", lambda: transport)
    with pytest.raises(GumloopError, match="GUMLOOP_ACCESS_TOKEN"):
        calls = [
            {"server_id": "gmail", "tool_name": "search"},
            {"server_id": "gmail", "tool_name": "search", "account": "work"},
        ]
        if asynchronous:
            await client.mcp.execute_many(calls)
        else:
            client.mcp.execute_many(calls)
    transport.execute_many.assert_not_called()
    transport.execute_many_async.assert_not_called()
