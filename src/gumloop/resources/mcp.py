from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import McpExecuteResponse
from gumloop.types import McpServerResponse
from gumloop.types import McpServersResponse
from gumloop.types import McpToolCallRequest
from gumloop.types import McpToolsResponse


def _call_body(calls: Sequence[McpToolCallRequest | dict[str, Any]], team_id: str | None) -> dict[str, Any]:
    # Backend enforces 1–5 calls; the lower bound is checked client-side so
    # an empty list fails without a network round-trip.
    if not calls:
        raise ValueError("calls cannot be empty")
    body: dict[str, Any] = {
        "calls": [c.model_dump(exclude_none=True) if isinstance(c, McpToolCallRequest) else dict(c) for c in calls],
    }
    if team_id is not None:
        body["team_id"] = team_id
    return body


class MCP:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list_servers(self, *, team_id: str | None = None, **kwargs: Any) -> McpServersResponse:
        return McpServersResponse.model_validate(self._client.get("mcp/servers", params={"team_id": team_id, **kwargs}))

    def get_server(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpServerResponse:
        return McpServerResponse.model_validate(
            self._client.get(f"mcp/servers/{server_id}", params={"team_id": team_id, **kwargs})
        )

    def list_tools(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpToolsResponse:
        return McpToolsResponse.model_validate(
            self._client.get(f"mcp/servers/{server_id}/tools", params={"team_id": team_id, **kwargs})
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
        call = McpToolCallRequest(
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments or {},
            ref=ref,
        )
        return McpExecuteResponse.model_validate(self._client.post("mcp/tools/call", json=_call_body([call], team_id)))

    def execute_many(
        self,
        calls: Sequence[McpToolCallRequest | dict[str, Any]],
        *,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        return McpExecuteResponse.model_validate(self._client.post("mcp/tools/call", json=_call_body(calls, team_id)))


class AsyncMCP:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list_servers(self, *, team_id: str | None = None, **kwargs: Any) -> McpServersResponse:
        data = await self._client.get("mcp/servers", params={"team_id": team_id, **kwargs})
        return McpServersResponse.model_validate(data)

    async def get_server(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpServerResponse:
        data = await self._client.get(f"mcp/servers/{server_id}", params={"team_id": team_id, **kwargs})
        return McpServerResponse.model_validate(data)

    async def list_tools(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpToolsResponse:
        data = await self._client.get(f"mcp/servers/{server_id}/tools", params={"team_id": team_id, **kwargs})
        return McpToolsResponse.model_validate(data)

    async def execute(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        call = McpToolCallRequest(
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments or {},
            ref=ref,
        )
        data = await self._client.post("mcp/tools/call", json=_call_body([call], team_id))
        return McpExecuteResponse.model_validate(data)

    async def execute_many(
        self,
        calls: Sequence[McpToolCallRequest | dict[str, Any]],
        *,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        data = await self._client.post("mcp/tools/call", json=_call_body(calls, team_id))
        return McpExecuteResponse.model_validate(data)
