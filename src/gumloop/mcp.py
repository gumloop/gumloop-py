from __future__ import annotations

from typing import Any

from gumloop.types import McpExecuteResponse
from gumloop.types import McpServerResponse
from gumloop.types import McpServersResponse
from gumloop.types import McpToolCall
from gumloop.types import McpToolsResponse


def _params(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


def _tool_call_body(
    *,
    tool_call_id: str | None = None,
    arguments: dict[str, Any] | None = None,
    tool_calls: list[McpToolCall] | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    if tool_call_id and tool_calls:
        raise ValueError("Pass either tool_call_id or tool_calls, not both")
    if not tool_call_id and not tool_calls:
        raise ValueError("tool_call_id or tool_calls is required")
    body = _params(tool_call_id=tool_call_id, team_id=team_id)
    if tool_call_id:
        body["arguments"] = arguments or {}
    if tool_calls is not None:
        body["tool_calls"] = tool_calls
    return body


class MCP:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list_servers(
        self,
        *,
        team_id: str | None = None,
    ) -> McpServersResponse:
        return self._client._request_json(
            "GET",
            "mcp/servers",
            params=_params(team_id=team_id),
        )

    def get_server(self, server_id: str, *, team_id: str | None = None) -> McpServerResponse:
        return self._client._request_json("GET", f"mcp/servers/{server_id}", params=_params(team_id=team_id))

    def list_tools(
        self,
        *,
        team_id: str | None = None,
        server_id: str | None = None,
        tool_call_ids: list[str] | None = None,
    ) -> McpToolsResponse:
        return self._client._request_json(
            "GET",
            "mcp/tools",
            params=_params(
                team_id=team_id,
                server_id=server_id,
                tool_call_ids=",".join(tool_call_ids) if tool_call_ids else None,
            ),
        )

    def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any] | None = None,
        *,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        return self._client._request_json(
            "POST",
            "mcp/tools/execute",
            json=_tool_call_body(tool_call_id=tool_call_id, arguments=arguments, team_id=team_id),
        )

    def execute_many(self, tool_calls: list[McpToolCall], *, team_id: str | None = None) -> McpExecuteResponse:
        return self._client._request_json(
            "POST",
            "mcp/tools/execute",
            json=_tool_call_body(tool_calls=tool_calls, team_id=team_id),
        )


class AsyncMCP:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def list_servers(
        self,
        *,
        team_id: str | None = None,
    ) -> McpServersResponse:
        return await self._client._request_json(
            "GET",
            "mcp/servers",
            params=_params(team_id=team_id),
        )

    async def get_server(self, server_id: str, *, team_id: str | None = None) -> McpServerResponse:
        return await self._client._request_json("GET", f"mcp/servers/{server_id}", params=_params(team_id=team_id))

    async def list_tools(
        self,
        *,
        team_id: str | None = None,
        server_id: str | None = None,
        tool_call_ids: list[str] | None = None,
    ) -> McpToolsResponse:
        return await self._client._request_json(
            "GET",
            "mcp/tools",
            params=_params(
                team_id=team_id,
                server_id=server_id,
                tool_call_ids=",".join(tool_call_ids) if tool_call_ids else None,
            ),
        )

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any] | None = None,
        *,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        return await self._client._request_json(
            "POST",
            "mcp/tools/execute",
            json=_tool_call_body(tool_call_id=tool_call_id, arguments=arguments, team_id=team_id),
        )

    async def execute_many(self, tool_calls: list[McpToolCall], *, team_id: str | None = None) -> McpExecuteResponse:
        return await self._client._request_json(
            "POST",
            "mcp/tools/execute",
            json=_tool_call_body(tool_calls=tool_calls, team_id=team_id),
        )
