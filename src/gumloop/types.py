from __future__ import annotations

from typing import Any
from typing import Literal
from typing import TypedDict


class AgentCreateRequired(TypedDict):
    name: str
    model: str


class AgentCreateRequest(AgentCreateRequired, total=False):
    description: str | None
    instructions: str | None
    tools: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    metadata: dict[str, Any] | None
    folder_id: str | None
    is_active: bool
    agent_id: str | None
    team_id: str | None


class AgentUpdateRequest(TypedDict, total=False):
    name: str | None
    model: str | None
    description: str | None
    instructions: str | None
    tools: list[dict[str, Any]] | None
    resources: list[dict[str, Any]] | None
    metadata: dict[str, Any] | None
    is_active: bool | None
    team_id: str | None


class Agent(TypedDict, total=False):
    id: str
    object: Literal["agent"]
    name: str | None
    description: str | None
    instructions: str | None
    model: str | None
    tools: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    metadata: dict[str, Any]
    status: str
    team_id: str | None
    created_at: str | None


class Model(TypedDict, total=False):
    id: str | None
    object: Literal["model"]
    created: int
    owned_by: str | None
    metadata: dict[str, Any]


class SessionCreateRequest(TypedDict, total=False):
    session_id: str | None
    input: str | list[Any] | None
    message: str | list[Any] | None
    metadata: dict[str, Any] | None


class SessionContinueRequest(TypedDict, total=False):
    input: str | list[Any] | None
    message: str | list[Any] | None


class McpServer(TypedDict, total=False):
    server_id: str
    name: str | None
    type: Literal["gumcp_server", "mcp_server", "gumstack_server"]
    status: Literal["connected", "unauthenticated", "blocked"]
    icon_url: str | None
    description: str | None
    gumloop_auth_url: str
    mcp_url: str | None
    tool_count: int | None


class McpTool(TypedDict, total=False):
    tool_call_id: str
    server_id: str
    server_type: Literal["gumcp_server", "mcp_server", "gumstack_server"]
    name: str
    description: str | None
    input_schema: dict[str, Any]
    server: dict[str, Any]


class McpToolCall(TypedDict, total=False):
    ref: str | None
    tool_call_id: str
    arguments: dict[str, Any]


class McpToolResult(TypedDict, total=False):
    ref: str
    tool_call_id: str
    status: Literal["success", "error", "unauthenticated"]
    content: list[Any]
    error: dict[str, Any]


class Session(TypedDict, total=False):
    id: str
    object: Literal["session"]
    agent_id: str
    status: str
    created_at: int | None
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]


class Response(TypedDict, total=False):
    id: str
    object: Literal["response"]
    created_at: int | None
    status: str
    model: str | None
    output: list[dict[str, Any]]
    output_text: str | None
    error: dict[str, Any] | None
    metadata: dict[str, Any]


class AgentResponse(TypedDict):
    agent: Agent


class AgentListResponse(TypedDict):
    object: Literal["list"]
    data: list[Agent]


class ModelListResponse(TypedDict):
    object: Literal["list"]
    data: list[Model]


class SessionResponse(TypedDict):
    session: Session


class ResponseResponse(TypedDict):
    response: Response


class QueuedResponseResponse(TypedDict, total=False):
    response: Response
    queue_position: int | None


class McpServersResponse(TypedDict, total=False):
    servers: list[McpServer]


class McpServerResponse(TypedDict):
    server: McpServer


class McpToolsResponse(TypedDict, total=False):
    tools: list[McpTool]
    server_id: str | None
    status: Literal["unauthenticated", "blocked"] | None
    gumloop_auth_url: str | None


class McpExecuteResponse(TypedDict):
    results: list[McpToolResult]


class SdkError(TypedDict, total=False):
    code: str
    message: str
    type: str
    param: str | None
    details: dict[str, Any]


class SdkErrorResponse(TypedDict):
    error: SdkError
