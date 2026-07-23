from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop._gumcp_transport import GumcpTransport
from gumloop._gumcp_transport import gumcp_env_ready
from gumloop.errors import GumloopError
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json


@pytest.fixture
def gumcp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMCP_ACCESS_TOKEN", "gumcp-token-1")
    monkeypatch.setenv("GUMCP_BASE_URL", "https://mcp.example.com")
    monkeypatch.setenv("GUMCP_USER_ID", "user_1")
    monkeypatch.setenv("GUMCP_CONFIG", '{"allowed_servers": ["gmail"], "server_routes": {}}')


def test_gumcp_env_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUMCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GUMCP_BASE_URL", raising=False)
    assert gumcp_env_ready() is False
    monkeypatch.setenv("GUMCP_ACCESS_TOKEN", "t")
    assert gumcp_env_ready() is False
    monkeypatch.setenv("GUMCP_BASE_URL", "https://mcp.example.com")
    assert gumcp_env_ready() is True


@respx.mock
def test_execute_falls_back_to_http_without_gumcp_env(client: Gumloop, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUMCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GUMCP_BASE_URL", raising=False)
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))

    assert client.mcp.execute("gmail", "read_emails", {"max_results": 5}).results == []
    assert route.call_count == 1
    assert request_json(route.calls[0].request)["calls"][0]["server_id"] == "gmail"


def test_missing_gumcp_client_package_raises(gumcp_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # sys.modules[name] = None forces a real ImportError on import.
    monkeypatch.setitem(sys.modules, "gumcp_client", None)
    transport = GumcpTransport()

    with pytest.raises(GumloopError, match="gumcp_client is not installed"):
        transport.execute("gmail", "read_emails", {})
    transport.close()


def test_two_executes_reuse_one_client(gumcp_env: None) -> None:
    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(return_value=['{"ok": true}'])
    mock_client.close = AsyncMock()

    construct_count = {"n": 0}

    def _factory(**kwargs: Any) -> Any:
        construct_count["n"] += 1
        assert kwargs["access_token"] == "gumcp-token-1"
        assert kwargs["base_url"] == "https://mcp.example.com"
        assert kwargs["server_id"] is None
        assert kwargs["auto_connect"] is False
        return mock_client

    with patch("gumloop._gumcp_transport._import_async_client", return_value=_factory):
        with Gumloop(access_token="http-token") as client:
            first = client.mcp.execute("gmail", "read_emails", {"max_results": 1})
            second = client.mcp.execute("gmail", "send_email", {"to": "a@b.com"})

    assert construct_count["n"] == 1
    assert mock_client.call_tool.await_count == 2
    assert mock_client.call_tool.await_args_list[0].args[0] == "gmail__read_emails"
    assert mock_client.call_tool.await_args_list[1].args[0] == "gmail__send_email"
    assert first.results[0].status == "success"
    assert second.results[0].status == "success"
    assert first.results[0].decoded_content == [{"ok": True}]
    mock_client.close.assert_awaited()


def test_token_env_change_rebuilds_client(gumcp_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[Any] = []

    def _factory(**_kwargs: Any) -> Any:
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(return_value=["ok"])
        mock_client.close = AsyncMock()
        clients.append(mock_client)
        return mock_client

    with patch("gumloop._gumcp_transport._import_async_client", return_value=_factory):
        client = Gumloop(access_token="http-token")
        client.mcp.execute("gmail", "read_emails", {})
        monkeypatch.setenv("GUMCP_ACCESS_TOKEN", "gumcp-token-2")
        client.mcp.execute("gmail", "read_emails", {})
        client.close()

    assert len(clients) == 2
    clients[0].close.assert_awaited()
    clients[1].close.assert_awaited()


def test_execute_many_maps_parallel_results(gumcp_env: None) -> None:
    mock_client = MagicMock()

    async def _call_tool(tool_name: str, arguments: dict[str, Any], **_kwargs: Any) -> list[str]:
        return [tool_name]

    mock_client.call_tool = AsyncMock(side_effect=_call_tool)
    mock_client.close = AsyncMock()

    with patch("gumloop._gumcp_transport._import_async_client", return_value=lambda **_: mock_client):
        client = Gumloop(access_token="http-token")
        resp = client.mcp.execute_many(
            [
                {"server_id": "gmail", "tool_name": "a", "arguments": {}, "ref": "r1"},
                {"server_id": "slack", "tool_name": "b", "arguments": {}, "ref": "r2"},
            ]
        )
        client.close()

    assert [r.ref for r in resp.results] == ["r1", "r2"]
    assert [r.content for r in resp.results] == [["gmail__a"], ["slack__b"]]
    assert mock_client.call_tool.await_count == 2


def test_execute_many_rejects_more_than_five(gumcp_env: None) -> None:
    with patch("gumloop._gumcp_transport._import_async_client", return_value=MagicMock):
        client = Gumloop(access_token="http-token")
        with pytest.raises(ValueError, match="cannot exceed 5"):
            client.mcp.execute_many([{"server_id": "gmail", "tool_name": f"t{i}", "arguments": {}} for i in range(6)])


def test_error_mapping_auth_and_not_allowed(gumcp_env: None) -> None:
    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    async def _fail(tool_name: str, arguments: dict[str, Any], **_kwargs: Any) -> list[str]:
        if tool_name.endswith("auth"):
            raise RuntimeError("credentials_not_found for gmail")
        if tool_name.endswith("deny"):
            raise RuntimeError("Server not permitted for this sandbox session")
        if tool_name.endswith("http"):
            raise RuntimeError("upstream HTTP 503 from mcp")
        if tool_name.endswith("conn"):
            err = type("ConnectionError", (Exception,), {})("Failed to connect to guMCP server: boom")
            raise err
        raise RuntimeError("mystery failure")

    mock_client.call_tool = AsyncMock(side_effect=_fail)

    with patch("gumloop._gumcp_transport._import_async_client", return_value=lambda **_: mock_client):
        client = Gumloop(access_token="http-token")
        auth = client.mcp.execute("gmail", "auth").results[0]
        deny = client.mcp.execute("gmail", "deny").results[0]
        http_err = client.mcp.execute("gmail", "http").results[0]
        conn = client.mcp.execute("gmail", "conn").results[0]
        other = client.mcp.execute("gmail", "other").results[0]
        client.close()

    assert auth.status == "unauthenticated"
    assert auth.error is not None and auth.error["code"] == "auth_required"
    assert deny.status == "error"
    assert deny.error is not None and deny.error["code"] == "tool_not_allowed"
    assert http_err.error is not None and http_err.error["code"] == "mcp_server_http_error"
    assert conn.error is not None and conn.error["code"] == "mcp_server_connection_failed"
    assert other.error is not None and other.error["code"] == "tool_execution_failed"


def test_async_execute_uses_direct_transport(gumcp_env: None) -> None:
    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(return_value=["async-ok"])
    mock_client.close = AsyncMock()

    async def run() -> None:
        with patch("gumloop._gumcp_transport._import_async_client", return_value=lambda **_: mock_client):
            async with AsyncGumloop(access_token="http-token") as client:
                resp = await client.mcp.execute("gmail", "read_emails", {})
                assert resp.results[0].content == ["async-ok"]
                # No Flask hop — respx would fail if we posted.
                batch = await client.mcp.execute_many(
                    [{"server_id": "gmail", "tool_name": "read_emails", "arguments": {}}]
                )
                assert batch.results[0].status == "success"

    asyncio.run(run())
    assert mock_client.call_tool.await_count == 2
    mock_client.close.assert_awaited()


@respx.mock
def test_http_path_still_used_when_gumcp_env_absent_for_execute_many(
    client: Gumloop, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GUMCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GUMCP_BASE_URL", raising=False)
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))

    client.mcp.execute_many([{"server_id": "gmail", "tool_name": "read_emails", "arguments": {}}])
    assert route.call_count == 1


def test_cancel_scope_error_maps_and_keeps_session(gumcp_env: None) -> None:
    """Cancel-scope failures map to results; the session is kept."""
    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(side_effect=[asyncio.CancelledError("cancel scope corrupted"), ["ok"]])
    mock_client.close = AsyncMock()
    construct_count = {"n": 0}

    def _factory(**_kwargs: Any) -> Any:
        construct_count["n"] += 1
        return mock_client

    with patch("gumloop._gumcp_transport._import_async_client", return_value=_factory):
        client = Gumloop(access_token="http-token")
        first = client.mcp.execute("gmail", "read_emails", {}).results[0]
        second = client.mcp.execute("gmail", "read_emails", {}).results[0]
        client.close()

    assert first.status == "error"
    assert first.error is not None and first.error["code"] == "mcp_server_connection_failed"
    assert second.status == "success"
    assert construct_count["n"] == 1  # same session served both calls


def test_real_cancellation_is_reraised(gumcp_env: None) -> None:
    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(side_effect=asyncio.CancelledError())
    mock_client.close = AsyncMock()

    async def run() -> None:
        transport = GumcpTransport()
        with patch("gumloop._gumcp_transport._import_async_client", return_value=lambda **_: mock_client):
            with pytest.raises(asyncio.CancelledError):
                await transport.call_one("gmail", "read_emails", {})
        await transport.aclose()

    asyncio.run(run())


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_system_exit_kills_loop_and_transport_recovers(gumcp_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """SystemExit escapes the loop thread; the caller gets an error (not a
    hang) and the next call gets a fresh loop."""
    import gumloop._gumcp_transport as transport_mod

    monkeypatch.setattr(transport_mod, "_LIVENESS_POLL_SECONDS", 0.05)
    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(side_effect=[SystemExit(1), ["recovered"]])
    mock_client.close = AsyncMock()

    with patch("gumloop._gumcp_transport._import_async_client", return_value=lambda **_: mock_client):
        client = Gumloop(access_token="http-token")
        with pytest.raises(RuntimeError, match="loop thread died"):
            client.mcp.execute("gmail", "read_emails", {})
        result = client.mcp.execute("gmail", "read_emails", {}).results[0]
        client.close()

    assert result.status == "success"
    assert result.content == ["recovered"]


def test_sync_calls_share_one_event_loop(gumcp_env: None) -> None:
    """Every sync execute drives the same loop, so connections never outlive it."""
    seen_loops: list[int] = []

    class LoopRecordingClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def call_tool(self, _tool: str, _args: dict[str, Any]) -> list[str]:
            seen_loops.append(id(asyncio.get_running_loop()))
            return ["ok"]

        async def close(self) -> None:
            pass

    with patch("gumloop._gumcp_transport._import_async_client", return_value=LoopRecordingClient):
        client = Gumloop(access_token="http-token")
        client.mcp.execute("gmail", "a", {})
        client.mcp.execute("gmail", "b", {})
        client.close()

    assert len(seen_loops) == 2
    assert seen_loops[0] == seen_loops[1]


def test_factory_receives_gumcp_config(gumcp_env: None) -> None:
    """GUMCP_CONFIG carries server_routes; dropping it breaks gumstack/custom MCP."""
    captured: dict[str, Any] = {}

    def _factory(**kwargs: Any) -> Any:
        captured.update(kwargs)
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(return_value=["ok"])
        mock_client.close = AsyncMock()
        return mock_client

    with patch("gumloop._gumcp_transport._import_async_client", return_value=_factory):
        client = Gumloop(access_token="http-token")
        client.mcp.execute("gmail", "read_emails", {})
        client.close()

    assert captured["config"] == {"allowed_servers": ["gmail"], "server_routes": {}}


def test_sync_execute_inside_running_loop(gumcp_env: None) -> None:
    """Chat kernels call sync execute from within a running loop (Jupyter):
    the calling thread blocks while the transport thread does the work —
    no nest_asyncio needed."""
    mock_client = MagicMock()
    mock_client.call_tool = AsyncMock(return_value=["nested-ok"])
    mock_client.close = AsyncMock()

    async def kernel_cell() -> Any:
        with patch("gumloop._gumcp_transport._import_async_client", return_value=lambda **_: mock_client):
            client = Gumloop(access_token="http-token")
            resp = client.mcp.execute("gmail", "read_emails", {})
            client.close()
            return resp

    resp = asyncio.run(kernel_cell())
    assert resp.results[0].content == ["nested-ok"]


def test_threaded_fanout_shares_one_session_safely(gumcp_env: None) -> None:
    """Legacy generated scripts parallelize with ThreadPoolExecutor: all
    threads must share one client on one loop with no RuntimeError."""
    from concurrent.futures import ThreadPoolExecutor

    seen_loops: list[int] = []
    construct_count = {"n": 0}

    class LoopRecordingClient:
        def __init__(self, **_kwargs: Any) -> None:
            construct_count["n"] += 1

        async def call_tool(self, tool: str, _args: dict[str, Any]) -> list[str]:
            seen_loops.append(id(asyncio.get_running_loop()))
            await asyncio.sleep(0.01)  # force overlap between threads
            return [tool]

        async def close(self) -> None:
            pass

    with patch("gumloop._gumcp_transport._import_async_client", return_value=LoopRecordingClient):
        client = Gumloop(access_token="http-token")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(client.mcp.execute, "gmail", f"tool_{i}", {}) for i in range(8)]
            results = [f.result().results[0] for f in futures]
        client.close()

    assert all(r.status == "success" for r in results)
    assert construct_count["n"] == 1  # one shared session
    assert len(set(seen_loops)) == 1  # everything ran on the transport loop


def test_close_on_unused_transport_is_a_noop(gumcp_env: None) -> None:
    transport = GumcpTransport()
    transport.close()
    transport.close()  # idempotent
    assert transport._loop is None

    async def run() -> None:
        fresh = GumcpTransport()
        await fresh.aclose()

    asyncio.run(run())


def test_auth_failure_after_env_rotation_rebuilds_and_retries(gumcp_env: None) -> None:
    """Mid-flight env token rotation triggers one rebuild+retry."""
    import os

    clients: list[Any] = []

    def _factory(**kwargs: Any) -> Any:
        mock_client = MagicMock()
        if not clients:

            async def _fail(_tool: str, _args: dict[str, Any]) -> list[str]:
                os.environ["GUMCP_ACCESS_TOKEN"] = "gumcp-token-rotated"
                raise RuntimeError("credentials_not_found: Authentication required")

            mock_client.call_tool = AsyncMock(side_effect=_fail)
        else:
            assert kwargs["access_token"] == "gumcp-token-rotated"
            mock_client.call_tool = AsyncMock(return_value=["ok-after-rotate"])
        mock_client.close = AsyncMock()
        clients.append(mock_client)
        return mock_client

    with patch("gumloop._gumcp_transport._import_async_client", return_value=_factory):
        client = Gumloop(access_token="http-token")
        result = client.mcp.execute("gmail", "read_emails", {}).results[0]
        client.close()

    assert result.status == "success"
    assert result.content == ["ok-after-rotate"]
    assert len(clients) == 2
    clients[0].close.assert_awaited()


def test_auth_failure_without_rotation_is_not_retried(gumcp_env: None) -> None:
    call_count = {"n": 0}

    def _factory(**_kwargs: Any) -> Any:
        mock_client = MagicMock()

        async def _fail(_tool: str, _args: dict[str, Any]) -> list[str]:
            call_count["n"] += 1
            raise RuntimeError("credentials_not_found")

        mock_client.call_tool = AsyncMock(side_effect=_fail)
        mock_client.close = AsyncMock()
        return mock_client

    with patch("gumloop._gumcp_transport._import_async_client", return_value=_factory):
        client = Gumloop(access_token="http-token")
        result = client.mcp.execute("gmail", "read_emails", {}).results[0]
        client.close()

    assert result.status == "unauthenticated"
    assert call_count["n"] == 1  # no blind retry loop
