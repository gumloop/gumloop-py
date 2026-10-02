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
from openrouter.components import ChatToolChoice
from openrouter.components import FormatJSONObjectConfig
from openrouter.components import ImageConfig
from openrouter.components import ProviderPreferences
from openrouter.components import ResponseHealingPlugin
from openrouter.components import WebSearchPlugin

from gumloop.spec._decisions import DecisionsAnswer
from gumloop.spec._decisions import DecisionsChoiceAnswer
from gumloop.spec._decisions import DecisionsChoiceQuestion
from gumloop.spec._decisions import DecisionsNoulAnswer
from gumloop.spec._decisions import DecisionsNoulQuestion
from gumloop.spec._decisions import DecisionsNoulQuestionCriteria
from gumloop.spec._decisions import DecisionsQuestion
from gumloop.spec._decisions import DecisionsRequest
from gumloop.spec._decisions import DecisionsResponse
from gumloop.spec._decisions import DecisionsResponseUsage
from gumloop.spec._decisions import DecisionsScoreAnswer
from gumloop.spec._decisions import DecisionsScoreQuestion
from gumloop.spec._decisions import Json
from gumloop.spec._decisions import TraceConfig

# ChatStreamDelta/ChatStreamChoice/ChatStreamChunk/ChatUsage subclassed to add
# fields Speakeasy 0.9.1 drops + Gumloop-only `gumloop_extensions` bucket.
from gumloop.spec._extensions import ChatStreamChunk
from gumloop.spec._extensions import ChatStreamDelta
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
    "DecisionsAnswer",
    "DecisionsChoiceAnswer",
    "DecisionsChoiceQuestion",
    "DecisionsNoulAnswer",
    "DecisionsNoulQuestion",
    "DecisionsNoulQuestionCriteria",
    "DecisionsQuestion",
    "DecisionsRequest",
    "DecisionsResponse",
    "DecisionsResponseUsage",
    "DecisionsScoreAnswer",
    "DecisionsScoreQuestion",
    "FormatJSONObjectConfig",
    "ImageConfig",
    "Json",
    "ProviderPreferences",
    "ResponseHealingPlugin",
    "TraceConfig",
    "WebSearchPlugin",
]
