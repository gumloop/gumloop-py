from __future__ import annotations

from typing import Any

from gumloop.types import McpExecuteResponse
from gumloop.types import McpServerResponse
from gumloop.types import McpServersResponse
from gumloop.types import McpToolCallRequest
from gumloop.types import McpToolsResponse


def _params(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


def _call_body(
    calls: list[McpToolCallRequest],
    *,
    team_id: str | None = None,
) -> dict[str, Any]:
    if not calls:
        raise ValueError("calls cannot be empty")
    body: dict[str, Any] = {"calls": [dict(c) for c in calls]}
    if team_id is not None:
        body["team_id"] = team_id
    return body


class MCP:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list_servers(self, *, team_id: str | None = None, **kwargs: Any) -> McpServersResponse:
        return self._client._request_json(
            "GET",
            "mcp/servers",
            params=_params(team_id=team_id, **kwargs),
        )

    def get_server(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpServerResponse:
        return self._client._request_json("GET", f"mcp/servers/{server_id}", params=_params(team_id=team_id, **kwargs))

    def list_tools(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpToolsResponse:
        return self._client._request_json(
            "GET",
            f"mcp/servers/{server_id}/tools",
            params=_params(team_id=team_id, **kwargs),
        )

    def execute(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        call: McpToolCallRequest = {"server_id": server_id, "tool_name": tool_name, "arguments": arguments or {}}
        if ref is not None:
            call["ref"] = ref
        return self._client._request_json(
            "POST",
            "mcp/tools/call",
            json=_call_body([call], team_id=team_id),
        )

    def execute_many(self, calls: list[McpToolCallRequest], *, team_id: str | None = None) -> McpExecuteResponse:
        return self._client._request_json(
            "POST",
            "mcp/tools/call",
            json=_call_body(calls, team_id=team_id),
        )


class AsyncMCP:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def list_servers(self, *, team_id: str | None = None, **kwargs: Any) -> McpServersResponse:
        return await self._client._request_json(
            "GET",
            "mcp/servers",
            params=_params(team_id=team_id, **kwargs),
        )

    async def get_server(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpServerResponse:
        return await self._client._request_json(
            "GET", f"mcp/servers/{server_id}", params=_params(team_id=team_id, **kwargs)
        )

    async def list_tools(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpToolsResponse:
        return await self._client._request_json(
            "GET",
            f"mcp/servers/{server_id}/tools",
            params=_params(team_id=team_id, **kwargs),
        )

    async def execute(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        call: McpToolCallRequest = {"server_id": server_id, "tool_name": tool_name, "arguments": arguments or {}}
        if ref is not None:
            call["ref"] = ref
        return await self._client._request_json(
            "POST",
            "mcp/tools/call",
            json=_call_body([call], team_id=team_id),
        )

    async def execute_many(self, calls: list[McpToolCallRequest], *, team_id: str | None = None) -> McpExecuteResponse:
        return await self._client._request_json(
            "POST",
            "mcp/tools/call",
            json=_call_body(calls, team_id=team_id),
        )
