"""MCP request/response models; leaf module so ``mcp.execute`` never builds the full ``gumloop.types`` catalog."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from gumloop._types_base import _Model

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
    account: str | None = None
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


class McpServerAccount(_Model):
    id: str
    label: str | None = None
    is_default: bool = False
    in_use: bool = False


class McpServerAccountsResponse(_Model):
    server_id: str
    accounts: list[McpServerAccount] = Field(default_factory=list)


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
