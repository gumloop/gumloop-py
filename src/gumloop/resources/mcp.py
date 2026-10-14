from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gumloop._gumcp_transport import GumcpTransport
from gumloop._gumcp_transport import gumcp_env_ready
from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.errors import GumloopError
from gumloop.types import McpExecuteResponse
from gumloop.types import McpPromptResponse
from gumloop.types import McpPromptsResponse
from gumloop.types import McpResourceReadResponse
from gumloop.types import McpResourcesResponse
from gumloop.types import McpServerAccountsResponse
from gumloop.types import McpServerResponse
from gumloop.types import McpServersResponse
from gumloop.types import McpToolCallRequest
from gumloop.types import McpToolsResponse


def _call_body(calls: Sequence[McpToolCallRequest | dict[str, Any]], team_id: str | None) -> dict[str, Any]:
    if not calls:
        raise ValueError("calls cannot be empty")
    if len(calls) > 5:
        raise ValueError("calls cannot exceed 5 items per request.")
    body: dict[str, Any] = {
        "calls": [c.model_dump(exclude_none=True) if isinstance(c, McpToolCallRequest) else dict(c) for c in calls],
    }
    if team_id is not None:
        body["team_id"] = team_id
    return body


class MCP:
    def __init__(self, client: HttpClient) -> None:
        self._client = client
        self._gumcp: GumcpTransport | None = None

    def _direct_transport(self) -> GumcpTransport | None:
        if not gumcp_env_ready():
            return None
        if self._gumcp is None:
            self._gumcp = GumcpTransport()
        return self._gumcp

    def close(self) -> None:
        if self._gumcp is not None:
            self._gumcp.close()
            self._gumcp = None

    def list_servers(self, *, team_id: str | None = None, **kwargs: Any) -> McpServersResponse:
        return McpServersResponse.model_validate(self._client.get("mcp/servers", params={"team_id": team_id, **kwargs}))

    def get_server(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpServerResponse:
        return McpServerResponse.model_validate(
            self._client.get(f"mcp/servers/{server_id}", params={"team_id": team_id, **kwargs})
        )

    def list_accounts(self, server_id: str, *, team_id: str | None = None) -> McpServerAccountsResponse:
        data = self._client.get(f"mcp/servers/{server_id}/accounts", params={"team_id": team_id})
        return McpServerAccountsResponse.model_validate(data)

    def list_tools(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpToolsResponse:
        return McpToolsResponse.model_validate(
            self._client.get(f"mcp/servers/{server_id}/tools", params={"team_id": team_id, **kwargs})
        )

    def list_resources(
        self, server_id: str, *, cursor: str | None = None, team_id: str | None = None, **kwargs: Any
    ) -> McpResourcesResponse:
        return McpResourcesResponse.model_validate(
            self._client.get(
                f"mcp/servers/{server_id}/resources",
                params={"cursor": cursor, "team_id": team_id, **kwargs},
            )
        )

    def get_resource(
        self, server_id: str, uri: str, *, team_id: str | None = None, **kwargs: Any
    ) -> McpResourceReadResponse:
        return McpResourceReadResponse.model_validate(
            self._client.get(
                f"mcp/servers/{server_id}/resources/read",
                params={"uri": uri, "team_id": team_id, **kwargs},
            )
        )

    def list_prompts(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpPromptsResponse:
        return McpPromptsResponse.model_validate(
            self._client.get(f"mcp/servers/{server_id}/prompts", params={"team_id": team_id, **kwargs})
        )

    def get_prompt(
        self,
        server_id: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        team_id: str | None = None,
    ) -> McpPromptResponse:
        # team_id is read from the body here; the query-level default doesn't reach it.
        team_id = team_id if team_id is not None else self._client.team_id
        body: dict[str, Any] = {"name": name, "arguments": arguments or {}}
        if team_id is not None:
            body["team_id"] = team_id
        return McpPromptResponse.model_validate(self._client.post(f"mcp/servers/{server_id}/prompts/get", json=body))

    def execute(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
        account: str | None = None,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        call = McpToolCallRequest(
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments or {},
            ref=ref,
            account=account,
        )
        return self.execute_many([call], team_id=team_id)

    def execute_many(
        self,
        calls: Sequence[McpToolCallRequest | dict[str, Any]],
        *,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        normalized = _call_body(calls, team_id)["calls"]
        has_account = any(call.get("account") is not None for call in normalized)
        if has_account and not self._client.access_token:
            raise GumloopError("Account selection requires GUMLOOP_ACCESS_TOKEN for the backend HTTP API.")
        transport = self._direct_transport() if any(call.get("account") is None for call in normalized) else None
        if transport is not None:
            for index, call in enumerate(normalized):
                call["ref"] = call.get("ref") or str(index)
            pinned = [(index, call) for index, call in enumerate(normalized) if call.get("account") is not None]
            if not pinned:
                return transport.execute_many(calls)
            direct = [(index, call) for index, call in enumerate(normalized) if call.get("account") is None]
            team_id = team_id if team_id is not None else self._client.team_id
            data = self._client.post("mcp/tools/call", json=_call_body([call for _, call in pinned], team_id))
            response = McpExecuteResponse.model_validate(data)
            if len(response.results) != len(pinned):
                raise GumloopError("Backend returned an unexpected number of account call results.")
            indexed_results = list(zip((index for index, _ in pinned), response.results, strict=True))
            if direct:
                direct_response = transport.execute_many([call for _, call in direct])
                if len(direct_response.results) != len(direct):
                    raise GumloopError("guMCP returned an unexpected number of tool call results.")
                indexed_results.extend(zip((index for index, _ in direct), direct_response.results, strict=True))
            return McpExecuteResponse(results=[result for _, result in sorted(indexed_results)])
        team_id = team_id if team_id is not None else self._client.team_id
        return McpExecuteResponse.model_validate(self._client.post("mcp/tools/call", json=_call_body(calls, team_id)))


class AsyncMCP:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client
        self._gumcp: GumcpTransport | None = None

    def _direct_transport(self) -> GumcpTransport | None:
        if not gumcp_env_ready():
            return None
        if self._gumcp is None:
            self._gumcp = GumcpTransport()
        return self._gumcp

    async def aclose(self) -> None:
        if self._gumcp is not None:
            await self._gumcp.aclose()
            self._gumcp = None

    async def list_servers(self, *, team_id: str | None = None, **kwargs: Any) -> McpServersResponse:
        data = await self._client.get("mcp/servers", params={"team_id": team_id, **kwargs})
        return McpServersResponse.model_validate(data)

    async def get_server(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpServerResponse:
        data = await self._client.get(f"mcp/servers/{server_id}", params={"team_id": team_id, **kwargs})
        return McpServerResponse.model_validate(data)

    async def list_accounts(self, server_id: str, *, team_id: str | None = None) -> McpServerAccountsResponse:
        data = await self._client.get(f"mcp/servers/{server_id}/accounts", params={"team_id": team_id})
        return McpServerAccountsResponse.model_validate(data)

    async def list_tools(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpToolsResponse:
        data = await self._client.get(f"mcp/servers/{server_id}/tools", params={"team_id": team_id, **kwargs})
        return McpToolsResponse.model_validate(data)

    async def list_resources(
        self, server_id: str, *, cursor: str | None = None, team_id: str | None = None, **kwargs: Any
    ) -> McpResourcesResponse:
        data = await self._client.get(
            f"mcp/servers/{server_id}/resources",
            params={"cursor": cursor, "team_id": team_id, **kwargs},
        )
        return McpResourcesResponse.model_validate(data)

    async def get_resource(
        self, server_id: str, uri: str, *, team_id: str | None = None, **kwargs: Any
    ) -> McpResourceReadResponse:
        data = await self._client.get(
            f"mcp/servers/{server_id}/resources/read",
            params={"uri": uri, "team_id": team_id, **kwargs},
        )
        return McpResourceReadResponse.model_validate(data)

    async def list_prompts(self, server_id: str, *, team_id: str | None = None, **kwargs: Any) -> McpPromptsResponse:
        data = await self._client.get(f"mcp/servers/{server_id}/prompts", params={"team_id": team_id, **kwargs})
        return McpPromptsResponse.model_validate(data)

    async def get_prompt(
        self,
        server_id: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        team_id: str | None = None,
    ) -> McpPromptResponse:
        # team_id is read from the body here; the query-level default doesn't reach it.
        team_id = team_id if team_id is not None else self._client.team_id
        body: dict[str, Any] = {"name": name, "arguments": arguments or {}}
        if team_id is not None:
            body["team_id"] = team_id
        data = await self._client.post(f"mcp/servers/{server_id}/prompts/get", json=body)
        return McpPromptResponse.model_validate(data)

    async def execute(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ref: str | None = None,
        account: str | None = None,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        call = McpToolCallRequest(
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments or {},
            ref=ref,
            account=account,
        )
        return await self.execute_many([call], team_id=team_id)

    async def execute_many(
        self,
        calls: Sequence[McpToolCallRequest | dict[str, Any]],
        *,
        team_id: str | None = None,
    ) -> McpExecuteResponse:
        normalized = _call_body(calls, team_id)["calls"]
        has_account = any(call.get("account") is not None for call in normalized)
        if has_account and not self._client.access_token:
            raise GumloopError("Account selection requires GUMLOOP_ACCESS_TOKEN for the backend HTTP API.")
        transport = self._direct_transport() if any(call.get("account") is None for call in normalized) else None
        if transport is not None:
            for index, call in enumerate(normalized):
                call["ref"] = call.get("ref") or str(index)
            pinned = [(index, call) for index, call in enumerate(normalized) if call.get("account") is not None]
            if not pinned:
                return await transport.execute_many_async(calls)
            direct = [(index, call) for index, call in enumerate(normalized) if call.get("account") is None]
            team_id = team_id if team_id is not None else self._client.team_id
            data = await self._client.post("mcp/tools/call", json=_call_body([call for _, call in pinned], team_id))
            response = McpExecuteResponse.model_validate(data)
            if len(response.results) != len(pinned):
                raise GumloopError("Backend returned an unexpected number of account call results.")
            indexed_results = list(zip((index for index, _ in pinned), response.results, strict=True))
            if direct:
                direct_response = await transport.execute_many_async([call for _, call in direct])
                if len(direct_response.results) != len(direct):
                    raise GumloopError("guMCP returned an unexpected number of tool call results.")
                indexed_results.extend(zip((index for index, _ in direct), direct_response.results, strict=True))
            return McpExecuteResponse(results=[result for _, result in sorted(indexed_results)])
        team_id = team_id if team_id is not None else self._client.team_id
        data = await self._client.post("mcp/tools/call", json=_call_body(calls, team_id))
        return McpExecuteResponse.model_validate(data)
