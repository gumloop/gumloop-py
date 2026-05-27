from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class _Model(BaseModel):
    """Base for all SDK models. ``extra="allow"`` lets the SDK transparently
    pass through fields the backend adds in future versions without an SDK
    bump — both on parsed responses and on user-supplied request kwargs."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @classmethod
    def build(cls, request: Any = None, /, **kwargs: Any) -> dict[str, Any]:
        """Merge a (model | dict | None) request with caller kwargs and return
        a JSON-ready dict. ``exclude_unset`` is used so unspecified fields
        keep their backend-side defaults instead of being overwritten by the
        SDK's local default values."""
        base = request.model_dump(exclude_unset=True) if isinstance(request, cls) else dict(request or {})
        base.update({k: v for k, v in kwargs.items() if v is not None})
        return cls.model_validate(base).model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------
# Shared payload types
# ---------------------------------------------------------------------------


class CreatorPayload(_Model):
    id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    profile_picture: str | None = None


# ---------------------------------------------------------------------------
# Agent types
# ---------------------------------------------------------------------------


class AgentCreateRequest(_Model):
    name: str
    model_name: str
    description: str | None = None
    system_prompt: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    folder_id: str | None = None
    is_active: bool = True
    agent_id: str | None = None
    team_id: str | None = None


class AgentUpdateRequest(_Model):
    name: str | None = None
    model_name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools: list[dict[str, Any]] | None = None
    resources: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None
    team_id: str | None = None


class Agent(_Model):
    id: str
    name: str
    description: str | None = None
    team_id: str | None = None
    is_active: bool = False
    tools: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_name: str | None = None
    system_prompt: str | None = None
    folder_id: str | None = None
    type: str | None = None
    created_at: str | None = None
    active_trigger_count: int | None = None
    creator: CreatorPayload | None = None


class AgentResponse(_Model):
    agent: Agent


class AgentListResponse(_Model):
    agents: list[Agent] = Field(default_factory=list)
    next_cursor: str | None = None


# ---------------------------------------------------------------------------
# Model types
# ---------------------------------------------------------------------------


class ModelListResponse(_Model):
    model_groups: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Team types
# ---------------------------------------------------------------------------


class Team(_Model):
    id: str
    name: str


class TeamsResponse(_Model):
    teams: list[Team] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session types
# ---------------------------------------------------------------------------


class SessionCreateRequest(_Model):
    input: str | list[Any] | None = None
    message: str | list[Any] | None = None
    session_id: str | None = None
    metadata: dict[str, Any] | None = None
    stream: bool = False


class SessionContinueRequest(_Model):
    input: str | list[Any] | None = None
    message: str | list[Any] | None = None
    stream: bool = False


class MessagePayload(_Model):
    id: str | None = None
    role: str | None = None
    content: str | None = None
    created_at: str | None = None
    creator_id: str | None = None
    parts: list[dict[str, Any]] | None = None


class Session(_Model):
    id: str
    agent_id: str
    state: str | None = None
    messages: list[MessagePayload] = Field(default_factory=list)
    created_at: str | None = None
    agent_name: str | None = None
    agent_team_id: str | None = None
    agent_creator_user_id: str | None = None
    agent_icon_url: str | None = None
    agent_tools: list[dict[str, Any]] = Field(default_factory=list)
    participants: dict[str, dict[str, Any]] = Field(default_factory=dict)
    creator: CreatorPayload | None = None


class SessionResponse(_Model):
    session: Session
    queue_position: int | None = None


class StreamEvent(_Model):
    type: str | None = None
    data: Any = None
    stream_cursor: str | None = None
    final: bool | None = None
    # Wire format uses camelCase on these two; surface snake_case attributes
    # to callers while still accepting the wire names on deserialize.
    finish_reason: str | None = Field(default=None, validation_alias="finishReason")
    error: str | None = None
    error_message: str | None = Field(default=None, validation_alias="errorMessage")


# ---------------------------------------------------------------------------
# Skill types
# ---------------------------------------------------------------------------


class Skill(_Model):
    id: str
    name: str
    description: str
    team_id: str
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    usage_count: int | None = None
    view_count: int | None = None
    last_used_at: str | None = None
    version_id: str | None = None
    major_version: int | None = None
    is_deployed: bool | None = None
    version_created_at: str | None = None
    creator: CreatorPayload | None = None


class SkillListResponse(_Model):
    skills: list[Skill] = Field(default_factory=list)
    next_cursor: str | None = None
    total_count: int | None = None


class SkillResponse(_Model):
    skill: Skill


class SkillDeleteResponse(_Model):
    deleted: bool


class SkillDownloadResponse(_Model):
    download_url: str
    filename: str
    media_type: Literal["application/zip"]
    size: int | None = None
    id: str
    version_id: str | None = None
    major_version: int | None = None


# ---------------------------------------------------------------------------
# Artifact types
# ---------------------------------------------------------------------------


class Artifact(_Model):
    id: str
    version_id: str | None = None
    major_version: int | None = None
    agent_id: str | None = None
    session_id: str | None = None
    filename: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None
    creator: CreatorPayload | None = None


class ArtifactListResponse(_Model):
    artifacts: list[Artifact] = Field(default_factory=list)
    next_cursor: str | None = None


class ArtifactDownloadResponse(_Model):
    download_url: str
    filename: str | None = None
    media_type: str | None = None
    size: int | None = None


# ---------------------------------------------------------------------------
# MCP types
# ---------------------------------------------------------------------------


class McpServer(_Model):
    server_id: str
    name: str | None = None
    type: str
    status: str
    icon_url: str | None = None
    description: str | None = None
    gumloop_auth_url: str
    mcp_url: str | None = None
    tool_count: int | None = None
    allowed_tool_call_ids: list[str] | None = None


class McpTool(_Model):
    tool_call_id: str
    server_id: str | None = None
    server_type: str | None = None
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    server: dict[str, Any] = Field(default_factory=dict)


class McpToolCallRequest(_Model):
    ref: str | None = None
    server_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpToolCallResult(_Model):
    ref: str
    server_id: str | None = None
    tool_name: str | None = None
    status: str
    content: list[Any] | None = None
    error: dict[str, Any] | None = None


class McpServersResponse(_Model):
    servers: list[McpServer] = Field(default_factory=list)


class McpServerResponse(_Model):
    server: McpServer


class McpToolsResponse(_Model):
    tools: list[McpTool] = Field(default_factory=list)
    server_id: str | None = None
    status: str | None = None
    gumloop_auth_url: str | None = None


class McpExecuteResponse(_Model):
    results: list[McpToolCallResult] = Field(default_factory=list)
