from __future__ import annotations

import json
from typing import Any
from typing import Literal

from pydantic import AliasChoices
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


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
    skill_ids: list[str] | None = None
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
    skill_ids: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_name: str | None = None
    system_prompt: str | None = None
    folder_id: str | None = None
    type: str | None = None
    created_at: str | None = None
    active_trigger_count: int | None = None
    creator: CreatorPayload | None = None


class AgentSkillsResponse(_Model):
    agent_id: str
    skill_ids: list[str] = Field(default_factory=list)
    attached: list[str] = Field(default_factory=list)
    detached: list[str] = Field(default_factory=list)
    already_attached: list[str] = Field(default_factory=list)
    already_detached: list[str] = Field(default_factory=list)


class AgentMcpServerResponse(_Model):
    agent_id: str
    mcp_server: dict[str, Any] = Field(default_factory=dict)
    created: bool = False
    auth_status: str | None = None


class AgentMcpServerDetachResponse(_Model):
    agent_id: str
    server_id: str
    detached: bool = False


class AgentMcpServersResponse(_Model):
    agent_id: str
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)


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


class SessionUsage(_Model):
    credit_cost: float | None = None
    tool_credit_cost: float | None = None
    flow_credit_cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class Session(_Model):
    id: str
    agent_id: str
    name: str | None = None
    type: str | None = None
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
    usage: SessionUsage | None = None


class SessionResponse(_Model):
    session: Session
    queue_position: int | None = None


class SessionListResponse(_Model):
    sessions: list[Session] = Field(default_factory=list)
    next_cursor: str | None = None


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
# Skill Sync response types
# ---------------------------------------------------------------------------


class CliSyncOrganization(_Model):
    organization_id: str = Field(min_length=1)
    organization_name: str = Field(min_length=1)


class CliSyncManifest(_Model):
    algorithm: Literal["sha256"]
    format_version: Literal[1]
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    skill_count: int = Field(ge=0)


class CliSyncLimits(_Model):
    files_per_skill: Literal[1000]
    bytes_per_file: Literal[26214400]
    bundle_transfer_bytes: Literal[104857600]
    total_uncompressed_bytes: Literal[209715200]


class CliSyncPlanResponse(_Model):
    organization: CliSyncOrganization
    manifest: CliSyncManifest
    limits: CliSyncLimits
    skill_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_skill_counts(self) -> CliSyncPlanResponse:
        if self.skill_count != self.manifest.skill_count:
            raise ValueError("skill_count must match manifest.skill_count")
        return self


class CliSyncBundleSkill(_Model):
    skill_id: str = Field(min_length=1)
    install_name: str = Field(min_length=1)
    published_version_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CliSyncBundleManifest(_Model):
    organization: CliSyncOrganization
    manifest: CliSyncManifest
    limits: CliSyncLimits
    skills: list[CliSyncBundleSkill]

    @model_validator(mode="after")
    def validate_skill_inventory(self) -> CliSyncBundleManifest:
        if self.manifest.skill_count != len(self.skills):
            raise ValueError("manifest.skill_count must match skills")
        if self.skills != sorted(self.skills, key=lambda skill: skill.skill_id):
            raise ValueError("skills must be sorted by skill_id")

        skill_ids = [skill.skill_id for skill in self.skills]
        install_names = [skill.install_name for skill in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("skill identities must be unique")
        if len(install_names) != len(set(install_names)):
            raise ValueError("install names must be unique")
        return self


# ---------------------------------------------------------------------------
# Brain types
# ---------------------------------------------------------------------------


class BrainSearchRequest(_Model):
    query: str
    limit: int | None = None
    source_type: list[str] | None = Field(default=None, min_length=1)


class BrainSearchResult(_Model):
    document_id: str | None = None
    source: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    score: float | None = None
    updated_at: str | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    parent_title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrainSearchResponse(_Model):
    results: list[BrainSearchResult] = Field(default_factory=list)


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

    @property
    def decoded_content(self) -> list[Any] | None:
        """Each content string JSON-decoded; plain text passes through. guMCP returns
        one string per TextContent, usually a JSON dump but sometimes plain text."""
        if self.content is None:
            return None
        decoded: list[Any] = []
        for item in self.content:
            try:
                decoded.append(json.loads(item) if isinstance(item, str) else item)
            except json.JSONDecodeError:
                decoded.append(item)
        return decoded


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

    def model_dump_decoded_content(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        results = payload.get("results")
        if not isinstance(results, list):
            return payload
        for index, result in enumerate(self.results):
            if index < len(results) and isinstance(results[index], dict):
                results[index]["content"] = result.decoded_content
        return payload


# ---------------------------------------------------------------------------
# MCP resource types
# ---------------------------------------------------------------------------


class McpResource(_Model):
    uri: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    size: int | None = None
    server_id: str | None = None


class McpResourcesResponse(_Model):
    resources: list[McpResource] = Field(default_factory=list)
    server_id: str | None = None
    status: str | None = None
    gumloop_auth_url: str | None = None
    next_cursor: str | None = None


class McpResourceContent(_Model):
    uri: str | None = None
    mime_type: str | None = None
    # A content item is either text or a base64 blob.
    text: str | None = None
    blob: str | None = None


class McpResourceReadResponse(_Model):
    server_id: str | None = None
    uri: str | None = None
    contents: list[McpResourceContent] = Field(default_factory=list)

    @property
    def text(self) -> str | None:
        """All text contents joined with newlines, or None if the resource is
        binary/empty. Most resources are a single text blob, so this is the value
        callers usually want — parallels ``McpToolCallResult.decoded_content``."""
        parts = [content.text for content in self.contents if content.text]
        return "\n".join(parts) if parts else None


# ---------------------------------------------------------------------------
# MCP prompt types
# ---------------------------------------------------------------------------


class McpPromptArgument(_Model):
    name: str
    description: str | None = None
    required: bool | None = None


class McpPrompt(_Model):
    name: str
    description: str | None = None
    arguments: list[McpPromptArgument] = Field(default_factory=list)
    server_id: str | None = None


class McpPromptsResponse(_Model):
    prompts: list[McpPrompt] = Field(default_factory=list)
    server_id: str | None = None
    status: str | None = None
    gumloop_auth_url: str | None = None


class McpPromptMessage(_Model):
    role: str | None = None
    # content is {type, text, resource?, ...} — kept open across MCP content variants.
    content: dict[str, Any] = Field(default_factory=dict)


class McpPromptResponse(_Model):
    server_id: str | None = None
    name: str | None = None
    description: str | None = None
    messages: list[McpPromptMessage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluation types
# ---------------------------------------------------------------------------


class EvaluationConfig(_Model):
    agent_id: str
    enabled: bool = False
    is_active: bool = True
    model_name: str | None = None
    frequency: str | None = None
    language: str | None = None
    include_auto_tags: bool = False
    interaction_types: list[Any] = Field(default_factory=list)
    criteria: list[Any] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)
    data_points: list[Any] = Field(default_factory=list)
    sentiment: dict[str, Any] | None = None
    updated_ts: str | None = None


class EvaluationConfigResponse(_Model):
    config: EvaluationConfig


class EvaluationConfigUpdateRequest(_Model):
    enabled: bool | None = None
    model_name: str | None = None
    frequency: str | None = None
    language: str | None = None
    include_auto_tags: bool | None = None
    interaction_types: list[Any] | None = None
    criteria: list[Any] | None = None
    tags: list[Any] | None = None
    data_points: list[Any] | None = None
    sentiment: dict[str, Any] | None = None


class EvaluationResult(_Model):
    evaluation_id: str
    session_id: str = Field(validation_alias=AliasChoices("interaction_id", "session_id"))
    agent_id: str
    created_ts: str | None = None
    # "completed" | "failed"; grade/call_successful are null when failed.
    status: str | None = None
    grade: str | None = None
    call_successful: str | None = None
    sentiment: str | None = None
    summary: str | None = None
    criteria_results: list[Any] = Field(default_factory=list)
    data_results: list[Any] = Field(default_factory=list)
    applied_tags: list[Any] = Field(default_factory=list)


class EvaluationResultResponse(_Model):
    evaluation: EvaluationResult | None = None


class EvaluationResultListResponse(_Model):
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    next_cursor: str | None = None
