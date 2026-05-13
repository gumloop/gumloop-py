from __future__ import annotations

from typing import Any
from typing import TypedDict

# ---------------------------------------------------------------------------
# Shared payload types
# ---------------------------------------------------------------------------


class CreatorPayload(TypedDict, total=False):
    id: str | None
    first_name: str | None
    last_name: str | None
    email: str | None
    profile_picture: str | None


# ---------------------------------------------------------------------------
# Agent types
# ---------------------------------------------------------------------------


class AgentCreateRequest(TypedDict, total=False):
    name: str
    model_name: str
    description: str | None
    system_prompt: str | None
    tools: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    metadata: dict[str, Any] | None
    folder_id: str | None
    is_active: bool
    agent_id: str | None
    team_id: str | None


class AgentUpdateRequest(TypedDict, total=False):
    name: str | None
    model_name: str | None
    description: str | None
    system_prompt: str | None
    tools: list[dict[str, Any]] | None
    resources: list[dict[str, Any]] | None
    metadata: dict[str, Any] | None
    is_active: bool | None
    team_id: str | None


class Agent(TypedDict, total=False):
    id: str
    name: str
    description: str | None
    team_id: str | None
    is_active: bool
    tools: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    metadata: dict[str, Any]
    model_name: str | None
    system_prompt: str | None
    folder_id: str | None
    type: str | None
    created_at: str | None
    creator: CreatorPayload | None


class AgentResponse(TypedDict):
    agent: Agent


class AgentListResponse(TypedDict, total=False):
    agents: list[Agent]
    next_cursor: str | None


# ---------------------------------------------------------------------------
# Model types
# ---------------------------------------------------------------------------


class ModelListResponse(TypedDict, total=False):
    model_groups: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Team types
# ---------------------------------------------------------------------------


class Team(TypedDict, total=False):
    id: str
    name: str


class TeamsResponse(TypedDict):
    teams: list[Team]


# ---------------------------------------------------------------------------
# Session types
# ---------------------------------------------------------------------------


class SessionCreateRequest(TypedDict, total=False):
    session_id: str | None
    input: str | list[Any] | None
    message: str | list[Any] | None
    metadata: dict[str, Any] | None
    stream: bool


class SessionContinueRequest(TypedDict, total=False):
    input: str | list[Any] | None
    message: str | list[Any] | None
    stream: bool


class MessagePayload(TypedDict, total=False):
    id: str | None
    role: str | None
    content: str | None
    created_at: str | None
    creator_id: str | None
    parts: list[dict[str, Any]] | None


class Session(TypedDict, total=False):
    id: str
    agent_id: str
    state: str | None
    messages: list[dict[str, Any]]
    created_at: str | None
    agent_name: str | None
    agent_team_id: str | None
    agent_creator_user_id: str | None
    agent_icon_url: str | None
    agent_tools: list[dict[str, Any]]
    participants: dict[str, dict[str, Any]]
    creator: CreatorPayload | None


class SessionResponse(TypedDict, total=False):
    session: Session
    queue_position: int | None


class StreamEvent(TypedDict, total=False):
    type: str
    data: Any
    stream_cursor: str
    final: bool
    finishReason: str
    error: str
    errorMessage: str


# ---------------------------------------------------------------------------
# Skill types
# ---------------------------------------------------------------------------


class Skill(TypedDict, total=False):
    id: str
    name: str
    description: str
    team_id: str
    created_at: str | None
    updated_at: str | None
    metadata: dict[str, Any]
    usage_count: int | None
    view_count: int | None
    last_used_at: str | None
    version_id: str | None
    major_version: int | None
    is_deployed: bool | None
    version_created_at: str | None
    creator: CreatorPayload | None


class SkillListResponse(TypedDict, total=False):
    skills: list[Skill]
    next_cursor: str | None
    total_count: int | None


class SkillResponse(TypedDict):
    skill: Skill


class SkillDownloadResponse(TypedDict, total=False):
    download_url: str
    filename: str
    media_type: str
    size: int | None
    id: str
    version_id: str | None
    major_version: int | None


# ---------------------------------------------------------------------------
# Artifact types
# ---------------------------------------------------------------------------


class Artifact(TypedDict, total=False):
    id: str
    version_id: str | None
    major_version: int | None
    agent_id: str | None
    session_id: str | None
    filename: str | None
    created_at: str | None
    metadata: dict[str, Any]
    url: str | None
    creator: CreatorPayload | None


class ArtifactListResponse(TypedDict, total=False):
    artifacts: list[Artifact]
    next_cursor: str | None


class ArtifactDownloadResponse(TypedDict, total=False):
    download_url: str
    filename: str | None
    media_type: str | None
    size: int | None


# ---------------------------------------------------------------------------
# MCP types
# ---------------------------------------------------------------------------


class McpServer(TypedDict, total=False):
    server_id: str
    name: str | None
    type: str
    status: str
    icon_url: str | None
    description: str | None
    gumloop_auth_url: str
    mcp_url: str | None
    tool_count: int | None
    allowed_tool_call_ids: list[str] | None


class McpTool(TypedDict, total=False):
    tool_call_id: str
    server_id: str | None
    server_type: str | None
    name: str
    description: str | None
    input_schema: dict[str, Any]
    server: dict[str, Any]


class McpToolCallRequest(TypedDict, total=False):
    ref: str | None
    server_id: str
    tool_name: str
    arguments: dict[str, Any]


class McpToolCallResult(TypedDict, total=False):
    ref: str
    server_id: str | None
    tool_name: str | None
    status: str
    content: list[Any] | None
    error: dict[str, Any] | None


class McpServersResponse(TypedDict, total=False):
    servers: list[McpServer]


class McpServerResponse(TypedDict):
    server: McpServer


class McpToolsResponse(TypedDict, total=False):
    tools: list[McpTool]
    server_id: str | None
    status: str | None
    gumloop_auth_url: str | None


class McpExecuteResponse(TypedDict):
    results: list[McpToolCallResult]


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class SdkError(TypedDict, total=False):
    code: str
    message: str
    type: str
    param: str | None
    details: dict[str, Any]


class SdkErrorResponse(TypedDict):
    error: SdkError
