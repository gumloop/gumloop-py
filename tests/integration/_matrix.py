"""Shared chat-models matrix used by both the SDK live test and the CLI mirror.

`test_live_chat_models.py` exercises every cell via the Python SDK;
`test_live_chat_models_cli.py` exercises the same cells via `uv run gumloop
chat completions create ...`. Keeping the matrix definitions here guarantees
the two suites never drift — any matrix change immediately covers both
entrypoints.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from dataclasses import field


# ---------------------------------------------------------------------------
# Feature x Expectation enums
# ---------------------------------------------------------------------------


class Feature(str, enum.Enum):
    COMPLETIONS_UNARY = "completions_unary"
    COMPLETIONS_STREAM = "completions_stream"
    STRUCTURED_UNARY = "structured_unary"
    STRUCTURED_STREAM = "structured_stream"
    IMAGE_UNARY = "image_unary"
    IMAGE_STREAM = "image_stream"


class Expect(str, enum.Enum):
    OK = "ok"               # feature runs and produces the expected shape
    ERR_400 = "err_400"     # backend should reject with 400


_ALL_FEATURES = tuple(Feature)


# ---------------------------------------------------------------------------
# Capability matrix
# ---------------------------------------------------------------------------


def _chat_defaults() -> dict[Feature, Expect]:
    return {
        Feature.COMPLETIONS_UNARY: Expect.OK,
        Feature.COMPLETIONS_STREAM: Expect.OK,
        Feature.STRUCTURED_UNARY: Expect.OK,
        Feature.STRUCTURED_STREAM: Expect.OK,
        Feature.IMAGE_UNARY: Expect.ERR_400,
        Feature.IMAGE_STREAM: Expect.ERR_400,
    }


def _image_gen_defaults() -> dict[Feature, Expect]:
    return {
        Feature.COMPLETIONS_UNARY: Expect.ERR_400,
        Feature.COMPLETIONS_STREAM: Expect.ERR_400,
        Feature.STRUCTURED_UNARY: Expect.ERR_400,
        Feature.STRUCTURED_STREAM: Expect.ERR_400,
        Feature.IMAGE_UNARY: Expect.OK,
        Feature.IMAGE_STREAM: Expect.OK,
    }


@dataclass(frozen=True)
class ModelSpec:
    slug: str
    client: str  # which backend model_client routes this slug
    expectations: dict[Feature, Expect] = field(default_factory=_chat_defaults)


def _spec(slug: str, client: str, **overrides: Expect) -> ModelSpec:
    """Chat-model spec with per-feature overrides."""
    e = _chat_defaults()
    e.update(overrides)
    return ModelSpec(slug=slug, client=client, expectations=e)


def _image_spec(slug: str, client: str, **overrides: Expect) -> ModelSpec:
    e = _image_gen_defaults()
    e.update(overrides)
    return ModelSpec(slug=slug, client=client, expectations=e)


# Coverage notes:
# - Morph: chat-only, no json_schema honoring → structured features assert 400.
#   Requires MORPHLLM_API_KEY in backend env; without it every Morph completions
#   cell will fail with an OpenAI 400 (the backend is falling back to the wrong
#   provider). Fix the env, don't paper over the cell.
# - OpenRouter: full chat+structured support via passthrough. Requires
#   OPENROUTER_API_KEY in backend env; same env-failure visibility.
# - Image-gen models: image_stream succeeds with real partial-image SSE on
#   OpenAI gpt-image-* (stream_image_generation method); simulated single
#   chunk for Gemini and dall-e (no upstream partial-image streaming).
# - Gemini *-flash-image-preview slugs depend on the user's Gemini API
#   region/project; if 404s, that's catalog drift to update here.
_MODEL_MATRIX: tuple[ModelSpec, ...] = (
    # ---- Anthropic (AnthropicModelClient) ------------------------------
    _spec("claude-opus-4-7", "anthropic"),
    _spec("claude-opus-4-6", "anthropic"),
    _spec("claude-sonnet-4-6", "anthropic"),
    _spec("claude-sonnet-4-5", "anthropic"),
    _spec("claude-haiku-4-5", "anthropic"),

    # ---- Google Gemini (GeminiModelClient) -----------------------------
    _spec("gemini-3.1-pro-preview", "gemini"),
    _spec("gemini-3-pro-preview", "gemini"),
    _spec("gemini-3-flash-preview", "gemini"),
    _spec("gemini-3.5-flash", "gemini"),
    _spec("gemini-2.5-pro", "gemini"),
    _spec("gemini-2.5-flash", "gemini"),

    # ---- OpenAI Responses (OpenAIResponsesClient) ----------------------
    _spec("gpt-5.5", "openai_responses"),
    _spec("gpt-5.4", "openai_responses"),
    _spec("gpt-5.4-mini", "openai_responses"),
    _spec("gpt-5.4-nano", "openai_responses"),
    _spec("gpt-5.3-codex", "openai_responses"),
    _spec("gpt-5.2", "openai_responses"),
    _spec("gpt-5.2-codex", "openai_responses"),
    _spec("gpt-5", "openai_responses"),
    _spec("gpt-5-mini", "openai_responses"),
    _spec("gpt-5-nano", "openai_responses"),
    _spec("gpt-4.1", "openai_responses"),
    _spec("gpt-4.1-mini", "openai_responses"),
    _spec("gpt-4o", "openai_responses"),
    _spec("gpt-4o-mini", "openai_responses"),
    _spec("o3", "openai_responses"),
    _spec("o3-mini", "openai_responses"),
    _spec("o4-mini", "openai_responses"),

    # ---- OpenRouter (slugs shaped <provider>/<model>) ------------------
    # OR routes any provider/model string, but the public chat-completions
    # surface only honors slugs registered in ALL_MODELS. (Morph excluded —
    # MorphLLMModelClient has plumbing but no registered model entries.)
    _spec("qwen/qwen3.5-397b-a17b", "openrouter"),
    _spec("moonshotai/kimi-k2.6", "openrouter"),

    # ---- Image-gen: OpenAI (real partial-image streaming) --------------
    _image_spec("gpt-image-2", "openai_responses"),
    _image_spec("gpt-image-1.5", "openai_responses"),
    _image_spec("gpt-image-1", "openai_responses"),

    # ---- Image-gen: Gemini (simulated single-chunk streaming) ----------
    # The *-flash-image-preview slugs depend on your Gemini API region/project.
    # If they 404, that's catalog drift — update the slug here; don't skip.
    # Actual slugs returned by client.models.list() against Gumloop's
    # gemini_free_user_key. Google's Cloud Console quota dashboard labels
    # these with shortened display names (e.g. "gemini-3.1-flash-image") that
    # are NOT the slugs the API accepts — always trust client.models.list().
    _image_spec("gemini-2.5-flash-image", "gemini"),
    _image_spec("gemini-3-pro-image-preview", "gemini"),
    _image_spec("gemini-3.1-flash-image-preview", "gemini"),
)


def _gen_cases() -> list[tuple[ModelSpec, Feature]]:
    return [(spec, feat) for spec in _MODEL_MATRIX for feat in _ALL_FEATURES]


def _case_id(spec_and_feat: tuple[ModelSpec, Feature]) -> str:
    spec, feat = spec_and_feat
    return f"{spec.slug}::{feat.value}"


# ---------------------------------------------------------------------------
# Prompts (tight, deterministic — keep cost + flake down)
# ---------------------------------------------------------------------------

_TEXT_PROMPT = "Reply with exactly one word: pong"
_STRUCTURED_PROMPT = (
    "Return a single JSON object with two keys: 'name' set to 'Alice' "
    "and 'age' set to 30. Do not include any other keys."
)
_STRUCTURED_SCHEMA: dict = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name", "age"],
    "additionalProperties": False,
}
_IMAGE_PROMPT = "A single small red circle on a white background."


# Reasoning models burn output tokens on internal reasoning when constrained
# by json_schema; 2048 gives enough headroom for the response to terminate
# with usable JSON. Plain text features can stay tight at 512.
_STRUCTURED_MAX_TOKENS = 2048
_TEXT_MAX_TOKENS = 512


_STREAM_FEATURES: frozenset[Feature] = frozenset(
    {Feature.COMPLETIONS_STREAM, Feature.STRUCTURED_STREAM, Feature.IMAGE_STREAM}
)
_IMAGE_FEATURES: frozenset[Feature] = frozenset({Feature.IMAGE_UNARY, Feature.IMAGE_STREAM})
_STRUCTURED_FEATURES: frozenset[Feature] = frozenset(
    {Feature.STRUCTURED_UNARY, Feature.STRUCTURED_STREAM}
)


def is_stream(feature: Feature) -> bool:
    return feature in _STREAM_FEATURES


def is_image(feature: Feature) -> bool:
    return feature in _IMAGE_FEATURES


def is_structured(feature: Feature) -> bool:
    return feature in _STRUCTURED_FEATURES
