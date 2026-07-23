"""Subclasses re-adding fields Speakeasy 0.9.1 drops + Gumloop-only extensions.

Subclass field defaults need ``UNSET`` (Speakeasy's sentinel) rather than
plain ``None`` to be excluded by ``exclude_unset=True``. Pydantic treats
subclass-declared defaults as "set" during validation; the Speakeasy
``OptionalNullable[T]`` type carries an ``Unset`` sentinel default that the
generated parent serializer knows to strip, so we mirror that pattern.
"""

from __future__ import annotations

from typing import Any

from openrouter.components import ChatAssistantImages
from openrouter.components import ChatStreamChoice as _ChatStreamChoice
from openrouter.components import ChatStreamChunk as _ChatStreamChunk
from openrouter.components import ChatStreamDelta as _ChatStreamDelta
from openrouter.components import ChatUsage as _ChatUsage
from openrouter.types import UNSET
from openrouter.types import OptionalNullable


class ChatUsage(_ChatUsage):
    # `cost`, `is_byok`, `cost_details` are in the published OpenAPI but
    # missing from Speakeasy's generated ChatUsage; LLMSession reads them.
    cost: OptionalNullable[float] = UNSET
    is_byok: OptionalNullable[bool] = UNSET
    cost_details: OptionalNullable[dict[str, Any]] = UNSET


class ChatStreamDelta(_ChatStreamDelta):
    # Gumloop-only extension bucket. Today carries `tool_results` for native
    # providers that emit synthetic tool-result chunks (Gemini grounding
    # citations, MCP server-executed tool results) that don't fit the
    # OR/OpenAI Chat Completions wire shape. Consumers can read
    # `chunk.choices[0].delta.gumloop_extensions["tool_results"]`.
    gumloop_extensions: OptionalNullable[dict[str, Any]] = UNSET

    # Streaming counterpart of ChatAssistantMessage.images; carries data-URL
    # frames for image-generation models (gpt-image-* partial-image events,
    # gemini-*-image-preview, etc.). The OR spec doesn't declare images on
    # ChatStreamDelta yet — our backend emits it so partial-image streaming
    # works on the SDK consumer side.
    images: OptionalNullable[list[ChatAssistantImages]] = UNSET


class ChatStreamChoice(_ChatStreamChoice):
    # Re-annotate so the extended ChatStreamDelta carries through.
    delta: ChatStreamDelta  # type: ignore[assignment]


class ChatStreamChunk(_ChatStreamChunk):
    # Re-annotate so validation constructs our extended ChatUsage and
    # ChatStreamChoice. Pydantic resolves by annotation, not isinstance —
    # without this, parent annotations would drop the added fields.
    usage: ChatUsage | None = None  # type: ignore[assignment]
    choices: list[ChatStreamChoice]  # type: ignore[assignment]
