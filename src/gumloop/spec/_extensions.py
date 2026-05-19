"""Subclasses re-adding fields Speakeasy 0.9.1 drops from the generated models."""

from __future__ import annotations

from typing import Any

from openrouter.components import ChatStreamChunk as _ChatStreamChunk
from openrouter.components import ChatUsage as _ChatUsage
from pydantic import Field


class ChatUsage(_ChatUsage):
    # `cost`, `is_byok`, `cost_details` are in the published OpenAPI but
    # missing from Speakeasy's generated ChatUsage; LLMSession reads them.
    cost: float | None = Field(default=None)
    is_byok: bool | None = Field(default=None)
    cost_details: dict[str, Any] | None = Field(default=None)


class ChatStreamChunk(_ChatStreamChunk):
    # Re-annotate so validation constructs our extended ChatUsage; pydantic
    # resolves by annotation, not isinstance, so without this the parent's
    # `usage: _ChatUsage` annotation would drop the added fields.
    usage: ChatUsage | None = None  # type: ignore[assignment]
