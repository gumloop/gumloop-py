from __future__ import annotations

import os
from typing import Any

import httpx

from gumloop.agents import Agents
from gumloop.agents import AsyncAgents
from gumloop.agents import AsyncModels
from gumloop.agents import Models
from gumloop.auth import Auth
from gumloop.errors import APIStatusError
from gumloop.errors import AuthenticationError
from gumloop.mcp import MCP
from gumloop.mcp import AsyncMCP
from gumloop.sessions import AsyncSessions
from gumloop.sessions import Sessions
from gumloop.types import AgentCreateRequest
from gumloop.types import AgentListResponse
from gumloop.types import AgentResponse
from gumloop.types import AgentUpdateRequest
from gumloop.types import McpExecuteResponse
from gumloop.types import McpServerResponse
from gumloop.types import McpServersResponse
from gumloop.types import McpToolCall
from gumloop.types import McpToolsResponse
from gumloop.types import ModelListResponse
from gumloop.types import QueuedResponseResponse
from gumloop.types import ResponseResponse
from gumloop.types import SessionCreateRequest
from gumloop.types import SessionResponse

DEFAULT_BASE_URL = "https://api.gumloop.com/api/v1"
DEFAULT_TIMEOUT = 30.0


class Gumloop:
    DEFAULT_BASE_URL = DEFAULT_BASE_URL

    def __init__(
        self,
        api_key: str | None = None,
        *,
        access_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token or api_key or os.environ.get("GUMLOOP_ACCESS_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.agents = Agents(self)
        self.sessions = Sessions(self)
        self.models = Models(self)
        self.mcp = MCP(self)
        self.auth = Auth(base_url=self.base_url, timeout=self.timeout)

        self.headers = {"Authorization": f"Bearer {self.access_token or self.api_key or ''}"}

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = httpx.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs,
        )
        return self._json_or_error(response)

    def _headers(self) -> dict[str, str]:
        token = self._credential()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _credential(self) -> str:
        if not self.access_token:
            raise AuthenticationError("access_token, api_key, or GUMLOOP_ACCESS_TOKEN is required")
        return self.access_token

    def _json_or_error(self, response: httpx.Response) -> Any:
        self._raise_for_status(response)
        return response.json()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 200 or response.status_code >= 300:
            try:
                body: Any = response.json()
            except ValueError:
                body = response.text
            error = body.get("error") if isinstance(body, dict) else None
            message = (
                str(error.get("message") or f"Gumloop API returned HTTP {response.status_code}")
                if isinstance(error, dict)
                else f"Gumloop API returned HTTP {response.status_code}"
            )
            raise APIStatusError(
                message,
                status_code=response.status_code,
                body=body,
            )

    def list_models(self) -> ModelListResponse:
        return self.models.list()

    def list_agents(self, search: str | None = None, limit: int | None = None) -> AgentListResponse:
        return self.agents.list(search=search, limit=limit)

    def create_agent(self, request: AgentCreateRequest | None = None, **kwargs: Any) -> AgentResponse:
        return self.agents.create(request, **kwargs)

    def get_agent(self, agent_id: str) -> AgentResponse:
        return self.agents.retrieve(agent_id)

    def update_agent(self, agent_id: str, request: AgentUpdateRequest | None = None, **kwargs: Any) -> AgentResponse:
        return self.agents.update(agent_id, request, **kwargs)

    def create_session(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        **kwargs: Any,
    ) -> SessionResponse | ResponseResponse | QueuedResponseResponse:
        return self.sessions.create(agent_id, request, **kwargs)

    def get_session(self, session_id: str) -> SessionResponse:
        return self.sessions.retrieve(session_id)

    def send_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseResponse | QueuedResponseResponse:
        return self.sessions.send(session_id, input, **kwargs)

    def cancel_session(self, session_id: str) -> ResponseResponse | dict[str, str]:
        return self.sessions.cancel(session_id)

    def list_mcp_servers(self, **kwargs: Any) -> McpServersResponse:
        return self.mcp.list_servers(**kwargs)

    def get_mcp_server(self, server_id: str, **kwargs: Any) -> McpServerResponse:
        return self.mcp.get_server(server_id, **kwargs)

    def list_mcp_tools(self, **kwargs: Any) -> McpToolsResponse:
        return self.mcp.list_tools(**kwargs)

    def execute_mcp_tool(
        self,
        tool_call_id: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> McpExecuteResponse:
        return self.mcp.execute(tool_call_id, arguments, **kwargs)

    def execute_mcp_tools(self, tool_calls: list[McpToolCall], **kwargs: Any) -> McpExecuteResponse:
        return self.mcp.execute_many(tool_calls, **kwargs)

    @staticmethod
    def register_oauth_client(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return Auth(base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT).register_client(*args, **kwargs)

    @staticmethod
    def build_authorization_url(*args: Any, **kwargs: Any) -> tuple[str, str, str]:
        return Auth(base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT).build_authorization_url(*args, **kwargs)

    @staticmethod
    def exchange_oauth_code(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return Auth(base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT).exchange_code(*args, **kwargs)

    @staticmethod
    def refresh_oauth_token(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return Auth(base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT).refresh_token(*args, **kwargs)


class AsyncGumloop:
    DEFAULT_BASE_URL = DEFAULT_BASE_URL

    def __init__(
        self,
        api_key: str | None = None,
        *,
        access_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token or api_key or os.environ.get("GUMLOOP_ACCESS_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

        self.agents = AsyncAgents(self)
        self.sessions = AsyncSessions(self)
        self.models = AsyncModels(self)
        self.mcp = AsyncMCP(self)

        self.headers = {"Authorization": f"Bearer {self.access_token or self.api_key or ''}"}

    async def __aenter__(self) -> AsyncGumloop:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            **kwargs,
        )
        return self._json_or_error(response)

    def _headers(self) -> dict[str, str]:
        token = self._credential()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _credential(self) -> str:
        if not self.access_token:
            raise AuthenticationError("access_token, api_key, or GUMLOOP_ACCESS_TOKEN is required")
        return self.access_token

    def _json_or_error(self, response: httpx.Response) -> Any:
        self._raise_for_status(response)
        return response.json()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 200 or response.status_code >= 300:
            try:
                body: Any = response.json()
            except ValueError:
                body = response.text
            error = body.get("error") if isinstance(body, dict) else None
            message = (
                str(error.get("message") or f"Gumloop API returned HTTP {response.status_code}")
                if isinstance(error, dict)
                else f"Gumloop API returned HTTP {response.status_code}"
            )
            raise APIStatusError(
                message,
                status_code=response.status_code,
                body=body,
            )

    async def list_models(self) -> ModelListResponse:
        return await self.models.list()

    async def list_agents(self, search: str | None = None, limit: int | None = None) -> AgentListResponse:
        return await self.agents.list(search=search, limit=limit)

    async def create_agent(self, request: AgentCreateRequest | None = None, **kwargs: Any) -> AgentResponse:
        return await self.agents.create(request, **kwargs)

    async def get_agent(self, agent_id: str) -> AgentResponse:
        return await self.agents.retrieve(agent_id)

    async def update_agent(
        self,
        agent_id: str,
        request: AgentUpdateRequest | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        return await self.agents.update(agent_id, request, **kwargs)

    async def create_session(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        **kwargs: Any,
    ) -> SessionResponse | ResponseResponse | QueuedResponseResponse:
        return await self.sessions.create(agent_id, request, **kwargs)

    async def get_session(self, session_id: str) -> SessionResponse:
        return await self.sessions.retrieve(session_id)

    async def send_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseResponse | QueuedResponseResponse:
        return await self.sessions.send(session_id, input, **kwargs)

    async def cancel_session(self, session_id: str) -> ResponseResponse | dict[str, str]:
        return await self.sessions.cancel(session_id)

    async def list_mcp_servers(self, **kwargs: Any) -> McpServersResponse:
        return await self.mcp.list_servers(**kwargs)

    async def get_mcp_server(self, server_id: str, **kwargs: Any) -> McpServerResponse:
        return await self.mcp.get_server(server_id, **kwargs)

    async def list_mcp_tools(self, **kwargs: Any) -> McpToolsResponse:
        return await self.mcp.list_tools(**kwargs)

    async def execute_mcp_tool(
        self,
        tool_call_id: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> McpExecuteResponse:
        return await self.mcp.execute(tool_call_id, arguments, **kwargs)

    async def execute_mcp_tools(self, tool_calls: list[McpToolCall], **kwargs: Any) -> McpExecuteResponse:
        return await self.mcp.execute_many(tool_calls, **kwargs)


AsyncGumloopClient = AsyncGumloop
