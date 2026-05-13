from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from collections.abc import Iterator
from typing import Any
from typing import cast
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import httpx

from gumloop.agents import Agents
from gumloop.agents import AsyncAgents
from gumloop.agents import AsyncModels
from gumloop.agents import Models
from gumloop.artifacts import Artifacts
from gumloop.artifacts import AsyncArtifacts
from gumloop.auth import Auth
from gumloop.errors import APIStatusError
from gumloop.errors import AuthenticationError
from gumloop.mcp import MCP
from gumloop.mcp import AsyncMCP
from gumloop.sessions import AsyncSessions
from gumloop.sessions import Sessions
from gumloop.skills import AsyncSkills
from gumloop.skills import Skills
from gumloop.teams import AsyncTeams
from gumloop.teams import Teams
from gumloop.types import AgentCreateRequest
from gumloop.types import AgentListResponse
from gumloop.types import AgentResponse
from gumloop.types import AgentUpdateRequest
from gumloop.types import ArtifactDownloadResponse
from gumloop.types import ArtifactListResponse
from gumloop.types import McpExecuteResponse
from gumloop.types import McpServerResponse
from gumloop.types import McpServersResponse
from gumloop.types import McpToolCallRequest
from gumloop.types import McpToolsResponse
from gumloop.types import ModelListResponse
from gumloop.types import SessionCreateRequest
from gumloop.types import SessionResponse
from gumloop.types import SkillDownloadResponse
from gumloop.types import SkillListResponse
from gumloop.types import SkillResponse
from gumloop.types import StreamEvent
from gumloop.types import TeamsResponse

DEFAULT_BASE_URL = "https://api.gumloop.com/api/v1"
DEFAULT_TIMEOUT = 30.0
DEFAULT_STREAM_TIMEOUT = 3600.0


def _derive_stream_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parts = urlsplit(normalized)
    host = parts.netloc
    stream_host = host

    if host == "api.gumloop.com":
        stream_host = "ws.gumloop.com"
    elif host.endswith(".api.gumloop.com"):
        stream_host = host.replace(".api.gumloop.com", ".ws.gumloop.com")
    elif host.startswith("localhost:8080"):
        stream_host = host.replace("localhost:8080", "localhost:9093", 1)

    return urlunsplit((parts.scheme, stream_host, parts.path, "", ""))


def _decode_sse_event(event_name: str | None, data: str) -> StreamEvent:
    try:
        event = json.loads(data)
    except ValueError:
        event = {"data": data}
    if not isinstance(event, dict):
        event = {"data": event}
    if event_name and "type" not in event:
        event["type"] = event_name
    return cast(StreamEvent, event)


def _iter_sse_events(lines: Iterator[str]) -> Iterator[StreamEvent]:
    event_name: str | None = None
    data_lines: list[str] = []
    for line in lines:
        if not line:
            if data_lines:
                yield _decode_sse_event(event_name, "\n".join(data_lines))
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield _decode_sse_event(event_name, "\n".join(data_lines))


async def _aiter_sse_events(lines: AsyncIterator[str]) -> AsyncIterator[StreamEvent]:
    event_name: str | None = None
    data_lines: list[str] = []
    async for line in lines:
        if not line:
            if data_lines:
                yield _decode_sse_event(event_name, "\n".join(data_lines))
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield _decode_sse_event(event_name, "\n".join(data_lines))


class Gumloop:
    DEFAULT_BASE_URL = DEFAULT_BASE_URL

    def __init__(
        self,
        api_key: str | None = None,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        stream_base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float | None = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token or api_key or os.environ.get("GUMLOOP_ACCESS_TOKEN")
        # Personal Gumloop API key auth requires the user_id of the key owner so
        # the backend can look up the stored secret. Sent as the x-auth-key
        # header; OAuth callers omit it.
        self.user_id = user_id or os.environ.get("GUMLOOP_USER_ID")
        self.base_url = base_url.rstrip("/")
        self.stream_base_url = (stream_base_url or _derive_stream_base_url(self.base_url)).rstrip("/")
        self.timeout = timeout
        self.stream_timeout = stream_timeout

        self.agents = Agents(self)
        self.sessions = Sessions(self)
        self.models = Models(self)
        self.mcp = MCP(self)
        self.teams = Teams(self)
        self.skills = Skills(self)
        self.artifacts = Artifacts(self)
        self.auth = Auth(base_url=self.base_url, timeout=self.timeout)

        self.headers = {"Authorization": f"Bearer {self.access_token or self.api_key or ''}"}
        if self.user_id:
            self.headers["x-auth-key"] = self.user_id

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = httpx.request(
            method,
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(content_type="files" not in kwargs),
            timeout=self.timeout,
            **kwargs,
        )
        return self._json_or_error(response)

    def _stream_json(self, method: str, path: str, **kwargs: Any) -> Iterator[StreamEvent]:
        headers = {**self._headers(), "Accept": "text/event-stream"}
        with httpx.stream(
            method,
            f"{self.stream_base_url}/{path.lstrip('/')}",
            headers=headers,
            timeout=self.stream_timeout,
            **kwargs,
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                response.read()
                self._raise_for_status(response)
            yield from _iter_sse_events(response.iter_lines())

    def _headers(self, *, content_type: bool = True) -> dict[str, str]:
        token = self._credential()
        headers = {"Authorization": f"Bearer {token}"}
        if self.user_id:
            headers["x-auth-key"] = self.user_id
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

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

    def list_models(self, **kwargs: Any) -> ModelListResponse:
        return self.models.list(**kwargs)

    def list_agents(self, **kwargs: Any) -> AgentListResponse:
        return self.agents.list(**kwargs)

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
    ) -> SessionResponse | Iterator[StreamEvent]:
        return self.sessions.create(agent_id, request, **kwargs)

    def get_session(self, session_id: str) -> SessionResponse:
        return self.sessions.retrieve(session_id)

    def send_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | Iterator[StreamEvent]:
        return self.sessions.send(session_id, input, **kwargs)

    def stream_session(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        return self.sessions.stream(agent_id, request, **kwargs)

    def stream_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        return self.sessions.stream_message(session_id, input, **kwargs)

    def resume_session_stream(self, session_id: str, last_cursor: str, **kwargs: Any) -> Iterator[StreamEvent]:
        return self.sessions.resume_stream(session_id, last_cursor, **kwargs)

    def cancel_session(self, session_id: str) -> SessionResponse:
        return self.sessions.cancel(session_id)

    def list_mcp_servers(self, **kwargs: Any) -> McpServersResponse:
        return self.mcp.list_servers(**kwargs)

    def get_mcp_server(self, server_id: str, **kwargs: Any) -> McpServerResponse:
        return self.mcp.get_server(server_id, **kwargs)

    def list_mcp_tools(self, server_id: str, **kwargs: Any) -> McpToolsResponse:
        return self.mcp.list_tools(server_id, **kwargs)

    def execute_mcp_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> McpExecuteResponse:
        return self.mcp.execute(server_id, tool_name, arguments, **kwargs)

    def execute_mcp_tools(self, calls: list[McpToolCallRequest], **kwargs: Any) -> McpExecuteResponse:
        return self.mcp.execute_many(calls, **kwargs)

    def list_teams(self, **kwargs: Any) -> TeamsResponse:
        return self.teams.list(**kwargs)

    def list_skills(self, **kwargs: Any) -> SkillListResponse:
        return self.skills.list(**kwargs)

    def create_skill(self, files: Any, **kwargs: Any) -> SkillResponse:
        return self.skills.create(files, **kwargs)

    def update_skill(self, skill_id: str, files: Any) -> SkillResponse:
        return self.skills.update(skill_id, files)

    def download_skill(self, skill_id: str, **kwargs: Any) -> SkillDownloadResponse:
        return self.skills.download(skill_id, **kwargs)

    def list_artifacts(self, agent_id: str, **kwargs: Any) -> ArtifactListResponse:
        return self.artifacts.list(agent_id, **kwargs)

    def download_artifact(self, artifact_id: str, **kwargs: Any) -> ArtifactDownloadResponse:
        return self.artifacts.download(artifact_id, **kwargs)

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
        user_id: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        stream_base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float | None = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token or api_key or os.environ.get("GUMLOOP_ACCESS_TOKEN")
        self.user_id = user_id or os.environ.get("GUMLOOP_USER_ID")
        self.base_url = base_url.rstrip("/")
        self.stream_base_url = (stream_base_url or _derive_stream_base_url(self.base_url)).rstrip("/")
        self.timeout = timeout
        self.stream_timeout = stream_timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

        self.agents = AsyncAgents(self)
        self.sessions = AsyncSessions(self)
        self.models = AsyncModels(self)
        self.mcp = AsyncMCP(self)
        self.teams = AsyncTeams(self)
        self.skills = AsyncSkills(self)
        self.artifacts = AsyncArtifacts(self)

        self.headers = {"Authorization": f"Bearer {self.access_token or self.api_key or ''}"}
        if self.user_id:
            self.headers["x-auth-key"] = self.user_id

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
            headers=self._headers(content_type="files" not in kwargs),
            **kwargs,
        )
        return self._json_or_error(response)

    async def _astream_json(self, method: str, path: str, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        headers = {**self._headers(), "Accept": "text/event-stream"}
        async with self._client.stream(
            method,
            f"{self.stream_base_url}/{path.lstrip('/')}",
            headers=headers,
            timeout=self.stream_timeout,
            **kwargs,
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                await response.aread()
                self._raise_for_status(response)
            async for event in _aiter_sse_events(response.aiter_lines()):
                yield event

    def _headers(self, *, content_type: bool = True) -> dict[str, str]:
        token = self._credential()
        headers = {"Authorization": f"Bearer {token}"}
        if self.user_id:
            headers["x-auth-key"] = self.user_id
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

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

    async def list_models(self, **kwargs: Any) -> ModelListResponse:
        return await self.models.list(**kwargs)

    async def list_agents(self, **kwargs: Any) -> AgentListResponse:
        return await self.agents.list(**kwargs)

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
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        return await self.sessions.create(agent_id, request, **kwargs)

    async def get_session(self, session_id: str) -> SessionResponse:
        return await self.sessions.retrieve(session_id)

    async def send_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> SessionResponse | AsyncIterator[StreamEvent]:
        return await self.sessions.send(session_id, input, **kwargs)

    def stream_session(
        self,
        agent_id: str,
        request: SessionCreateRequest | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        return self.sessions.stream(agent_id, request, **kwargs)

    def stream_message(
        self,
        session_id: str,
        input: str | list[Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        return self.sessions.stream_message(session_id, input, **kwargs)

    def resume_session_stream(self, session_id: str, last_cursor: str, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        return self.sessions.resume_stream(session_id, last_cursor, **kwargs)

    async def cancel_session(self, session_id: str) -> SessionResponse:
        return await self.sessions.cancel(session_id)

    async def list_mcp_servers(self, **kwargs: Any) -> McpServersResponse:
        return await self.mcp.list_servers(**kwargs)

    async def get_mcp_server(self, server_id: str, **kwargs: Any) -> McpServerResponse:
        return await self.mcp.get_server(server_id, **kwargs)

    async def list_mcp_tools(self, server_id: str, **kwargs: Any) -> McpToolsResponse:
        return await self.mcp.list_tools(server_id, **kwargs)

    async def execute_mcp_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> McpExecuteResponse:
        return await self.mcp.execute(server_id, tool_name, arguments, **kwargs)

    async def execute_mcp_tools(self, calls: list[McpToolCallRequest], **kwargs: Any) -> McpExecuteResponse:
        return await self.mcp.execute_many(calls, **kwargs)

    async def list_teams(self, **kwargs: Any) -> TeamsResponse:
        return await self.teams.list(**kwargs)

    async def list_skills(self, **kwargs: Any) -> SkillListResponse:
        return await self.skills.list(**kwargs)

    async def create_skill(self, files: Any, **kwargs: Any) -> SkillResponse:
        return await self.skills.create(files, **kwargs)

    async def update_skill(self, skill_id: str, files: Any) -> SkillResponse:
        return await self.skills.update(skill_id, files)

    async def download_skill(self, skill_id: str, **kwargs: Any) -> SkillDownloadResponse:
        return await self.skills.download(skill_id, **kwargs)

    async def list_artifacts(self, agent_id: str, **kwargs: Any) -> ArtifactListResponse:
        return await self.artifacts.list(agent_id, **kwargs)

    async def download_artifact(self, artifact_id: str, **kwargs: Any) -> ArtifactDownloadResponse:
        return await self.artifacts.download(artifact_id, **kwargs)


AsyncGumloopClient = AsyncGumloop
