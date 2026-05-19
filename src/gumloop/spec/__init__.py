"""OpenRouter chat completions spec — shared wire format for SDK + backend."""

from __future__ import annotations

from openrouter.components import ChatFinishReasonEnum
from openrouter.components import ChatFormatJSONSchemaConfig
from openrouter.components import ChatFormatTextConfig
from openrouter.components import ChatFunctionTool
from openrouter.components import ChatJSONSchemaConfig
from openrouter.components import ChatMessages
from openrouter.components import ChatRequest
from openrouter.components import ChatResult
from openrouter.components import ChatStreamDelta
from openrouter.components import ChatToolChoice
from openrouter.components import FormatJSONObjectConfig
from openrouter.components import ImageConfig
from openrouter.components import ProviderPreferences
from openrouter.components import ResponseHealingPlugin
from openrouter.components import WebSearchPlugin

# ChatUsage/ChatStreamChunk subclassed to add fields Speakeasy 0.9.1 drops.
from gumloop.spec._extensions import ChatStreamChunk
from gumloop.spec._extensions import ChatUsage

__all__ = [
    "ChatFinishReasonEnum",
    "ChatFormatJSONSchemaConfig",
    "ChatFormatTextConfig",
    "ChatFunctionTool",
    "ChatJSONSchemaConfig",
    "ChatMessages",
    "ChatRequest",
    "ChatResult",
    "ChatStreamChunk",
    "ChatStreamDelta",
    "ChatToolChoice",
    "ChatUsage",
    "FormatJSONObjectConfig",
    "ImageConfig",
    "ProviderPreferences",
    "ResponseHealingPlugin",
    "WebSearchPlugin",
]
