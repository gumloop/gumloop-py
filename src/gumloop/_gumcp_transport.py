"""Direct guMCP transport for sandbox ``mcp.execute`` calls.

When ``GUMCP_ACCESS_TOKEN`` and ``GUMCP_BASE_URL`` are set (artifact / agent
sandboxes), tool calls go through a long-lived ``gumcp_client`` session instead
of ``POST /mcp/tools/call``. That amortizes connect+initialize across many
``execute`` calls on the same :class:`Gumloop` instance.

External SDK users without those env vars keep the Flask HTTP path.
``gumcp_client`` is an optional import — sandboxes already install it.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Sequence
from typing import Any

from gumloop.errors import GumloopError
from gumloop.types import McpExecuteResponse
from gumloop.types import McpToolCallRequest
from gumloop.types import McpToolCallResult

_MAX_BATCH = 5
_HTTP_STATUS_RE = re.compile(r"HTTP\s+(\d{3})")


def gumcp_env_ready() -> bool:
    """True when sandbox direct-mode credentials are present."""
    return bool(os.environ.get("GUMCP_ACCESS_TOKEN") and os.environ.get("GUMCP_BASE_URL"))


def _import_async_client() -> Any:
    try:
        from gumcp_client import AsyncClient
    except ImportError as exc:
        raise GumloopError(
            "GUMCP_ACCESS_TOKEN is set but gumcp_client is not installed. "
            "Install gumcp-client in the sandbox, or unset GUMCP_* to use the HTTP API."
        ) from exc
    return AsyncClient


def _load_config() -> dict[str, Any]:
    raw = os.environ.get("GUMCP_CONFIG")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_calls(
    calls: Sequence[McpToolCallRequest | dict[str, Any]],
) -> list[McpToolCallRequest]:
    if not calls:
        raise ValueError("calls cannot be empty")
    if len(calls) > _MAX_BATCH:
        raise ValueError("calls cannot exceed 5 items per request.")
    out: list[McpToolCallRequest] = []
    for call in calls:
        if isinstance(call, McpToolCallRequest):
            out.append(call)
        else:
            out.append(McpToolCallRequest.model_validate(call))
    return out


def _api_error_type(http_status: int) -> str:
    if http_status == 401:
        return "authentication_error"
    if http_status == 403:
        return "permission_error"
    if http_status == 404:
        return "not_found_error"
    if http_status == 429:
        return "rate_limit_error"
    if 400 <= http_status < 500:
        return "invalid_request_error"
    return "api_error"


def _error_result(
    *,
    ref: str,
    server_id: str,
    tool_name: str,
    status: str,
    code: str,
    message: str,
    error_type: str,
    details: dict[str, Any] | None = None,
    param: str | None = None,
) -> McpToolCallResult:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "type": error_type,
    }
    if param is not None:
        error["param"] = param
    if details:
        error["details"] = details
    return McpToolCallResult(
        ref=ref,
        server_id=server_id,
        tool_name=tool_name,
        status=status,
        error=error,
    )


def _map_exception(exc: BaseException, *, ref: str, server_id: str, tool_name: str) -> McpToolCallResult:
    message = str(exc)
    lower = message.lower()

    if "credentials_not_found" in message or "authentication required" in lower:
        return _error_result(
            ref=ref,
            server_id=server_id,
            tool_name=tool_name,
            status="unauthenticated",
            code="auth_required",
            message=f"Connect {server_id} before using this tool.",
            error_type="permission_error",
            param="tool_name",
            details={"server_id": server_id, "tool_name": tool_name},
        )

    if (
        "not permitted" in lower
        or "not allowed" in lower
        or "tool_not_allowed" in lower
        or "scoped_allowed_tools" in lower
    ):
        return _error_result(
            ref=ref,
            server_id=server_id,
            tool_name=tool_name,
            status="error",
            code="tool_not_allowed",
            message=(
                "This tool isn't in this run's allowed set. If you believe this "
                "tool should be allowed, ensure you are passing literal server and "
                "tool names to client.mcp.execute('server', 'tool', {...}), running "
                "scripts with `python <script.py>`, and pulling in other files with a "
                "direct `import` (not runpy, subprocess, or exec)."
            ),
            error_type="permission_error",
            details={"server_id": server_id, "tool_name": tool_name},
        )

    if "cancel scope" in lower or isinstance(exc, asyncio.CancelledError):
        return _error_result(
            ref=ref,
            server_id=server_id,
            tool_name=tool_name,
            status="error",
            code="mcp_server_connection_failed",
            message=(
                "MCP server connection failed. Check the MCP server URL, authentication, and credentials."
            ),
            error_type="api_error",
            details={"server_id": server_id},
        )

    http_matches = _HTTP_STATUS_RE.findall(message)
    if http_matches:
        http_status = int(http_matches[-1])
        return _error_result(
            ref=ref,
            server_id=server_id,
            tool_name=tool_name,
            status="error",
            code="mcp_server_http_error",
            message=(
                f"MCP server returned HTTP {http_status}. "
                "Check the MCP server URL, authentication, and credentials."
            ),
            error_type=_api_error_type(http_status),
            details={"server_id": server_id, "status_code": http_status},
        )

    # Connection-class failures from gumcp_client.
    exc_name = type(exc).__name__
    if exc_name in {"ConnectionError", "SessionError"} or "failed to connect" in lower:
        return _error_result(
            ref=ref,
            server_id=server_id,
            tool_name=tool_name,
            status="error",
            code="mcp_server_connection_failed",
            message=(
                "MCP server connection failed. Check the MCP server URL, authentication, and credentials."
            ),
            error_type="api_error",
            details={"server_id": server_id},
        )

    return _error_result(
        ref=ref,
        server_id=server_id,
        tool_name=tool_name,
        status="error",
        code="tool_execution_failed",
        message="Tool execution failed.",
        error_type="api_error",
        details={"server_id": server_id},
    )


class GumcpTransport:
    """Owns one multi-server ``AsyncClient`` keyed by the current GUMCP env fingerprint."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._fingerprint: tuple[str, str, str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _current_fingerprint(self) -> tuple[str, str, str]:
        token = os.environ.get("GUMCP_ACCESS_TOKEN") or ""
        base_url = (os.environ.get("GUMCP_BASE_URL") or "").rstrip("/")
        config_raw = os.environ.get("GUMCP_CONFIG") or ""
        return (token, base_url, config_raw)

    async def _close_client(self) -> None:
        client = self._client
        self._client = None
        self._fingerprint = None
        if client is None:
            return
        try:
            await client.close()
        except Exception:
            pass

    async def _ensure_client(self) -> Any:
        fingerprint = self._current_fingerprint()
        token, base_url, _config_raw = fingerprint
        if not token or not base_url:
            raise GumloopError("GUMCP_ACCESS_TOKEN and GUMCP_BASE_URL are required for direct MCP transport")

        if self._client is not None and self._fingerprint == fingerprint:
            return self._client

        await self._close_client()

        AsyncClient = _import_async_client()
        user_id = os.environ.get("GUMCP_USER_ID")
        self._client = AsyncClient(
            server_id=None,
            user_id=user_id,
            access_token=token,
            base_url=base_url,
            config=_load_config(),
            auto_connect=False,
            client_name="gumloop",
        )
        self._fingerprint = fingerprint
        return self._client

    async def call_one(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
        fallback_ref: str = "0",
        _retried: bool = False,
    ) -> McpToolCallResult:
        result_ref = ref or fallback_ref
        try:
            client = await self._ensure_client()
            content = await client.call_tool(
                f"{server_id}__{tool_name}",
                arguments or {},
            )
            return McpToolCallResult(
                ref=result_ref,
                server_id=server_id,
                tool_name=tool_name,
                status="success",
                content=content if isinstance(content, list) else [content],
            )
        except GumloopError:
            raise
        except asyncio.CancelledError as exc:
            # Real cancellation propagates; only the anyio cancel-scope failure maps.
            if "cancel scope" not in str(exc):
                raise
            return _map_exception(exc, ref=result_ref, server_id=server_id, tool_name=tool_name)
        except Exception as exc:
            result = _map_exception(exc, ref=result_ref, server_id=server_id, tool_name=tool_name)
            if (
                not _retried
                and result.status == "unauthenticated"
                and self._current_fingerprint() != self._fingerprint
            ):
                # Env token rotated mid-flight: rebuild once and retry.
                await self._close_client()
                return await self.call_one(
                    server_id,
                    tool_name,
                    arguments,
                    ref=ref,
                    fallback_ref=fallback_ref,
                    _retried=True,
                )
            return result

    async def execute_many_async(
        self,
        calls: Sequence[McpToolCallRequest | dict[str, Any]],
    ) -> McpExecuteResponse:
        normalized = _normalize_calls(calls)
        results = await asyncio.gather(
            *(
                self.call_one(
                    call.server_id,
                    call.tool_name,
                    call.arguments,
                    ref=call.ref,
                    fallback_ref=str(index),
                )
                for index, call in enumerate(normalized)
            )
        )
        return McpExecuteResponse(results=list(results))

    async def execute_async(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
    ) -> McpExecuteResponse:
        result = await self.call_one(server_id, tool_name, arguments, ref=ref, fallback_ref="0")
        return McpExecuteResponse(results=[result])

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run(self, coro: Any) -> Any:
        # Sync callers own one loop; inside a running loop (Jupyter),
        # nest_asyncio must patch THIS loop — no-arg apply() patches the running one.
        loop = self._get_loop()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return loop.run_until_complete(coro)
        try:
            import nest_asyncio
        except ImportError as import_exc:
            coro.close()
            raise GumloopError(
                "Direct MCP transport needs nest_asyncio inside a running event loop "
                "(e.g. Jupyter). Install nest_asyncio or call from AsyncGumloop."
            ) from import_exc
        nest_asyncio.apply(loop)
        return loop.run_until_complete(coro)

    def execute(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
    ) -> McpExecuteResponse:
        return self._run(self.execute_async(server_id, tool_name, arguments, ref=ref))

    def execute_many(
        self,
        calls: Sequence[McpToolCallRequest | dict[str, Any]],
    ) -> McpExecuteResponse:
        return self._run(self.execute_many_async(calls))

    def close(self) -> None:
        if self._client is None and self._loop is None:
            return
        try:
            self._run(self._close_client())
        except Exception:
            pass
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
        self._loop = None

    async def aclose(self) -> None:
        if self._client is None and self._loop is None:
            return
        await self._close_client()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
        self._loop = None
