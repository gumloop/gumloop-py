"""Live matrix tests: every locally-routed model × every feature.

These hit a real Gumloop backend (selected via ``GUMLOOP_BASE_URL``) which
fans out to each upstream provider. The matrix is *exhaustive*: every cell
is one of

    * ``Expect.OK``       — feature runs and produces the expected output shape
    * ``Expect.ERR_400``  — backend correctly returns 400 for an unsupported combo

There is no per-cell skip mechanism. A skip would hide an env-config or
catalog-drift problem that the operator needs to see — the matrix is meant
to surface those, not paper over them. The only legitimate skip is at the
fixture level (``GUMLOOP_API_KEY`` / ``GUMLOOP_BASE_URL`` unset), which
means the matrix can't be run at all.

Inputs are always built as a typed ``ChatRequest``; outputs are always
re-validated through ``ChatResult`` / ``ChatStreamChunk`` to catch wire-shape
drift.

Run with::

    cd gumloop-py
    pytest tests/integration/test_live_chat_models.py -m live -n 8

Failing cells point to one of:
    1. A real backend bug (start there)
    2. A missing local provider key (MORPHLLM_API_KEY, OPENROUTER_API_KEY, etc.)
    3. Catalog drift (model renamed/removed) — update the matrix to match
"""

from __future__ import annotations

import json
from typing import Iterator

import pytest

from gumloop import APIStatusError
from gumloop import Gumloop
from gumloop.spec import ChatRequest
from gumloop.spec import ChatResult
from gumloop.spec import ChatStreamChunk
from tests.integration._matrix import _IMAGE_PROMPT
from tests.integration._matrix import _MODEL_MATRIX
from tests.integration._matrix import _STRUCTURED_MAX_TOKENS
from tests.integration._matrix import _STRUCTURED_PROMPT
from tests.integration._matrix import _STRUCTURED_SCHEMA
from tests.integration._matrix import _TEXT_MAX_TOKENS
from tests.integration._matrix import _TEXT_PROMPT
from tests.integration._matrix import Expect
from tests.integration._matrix import Feature
from tests.integration._matrix import ModelSpec
from tests.integration._matrix import _case_id
from tests.integration._matrix import _gen_cases
from tests.integration._matrix import is_image
from tests.integration._matrix import is_structured


def _build_request(slug: str, feature: Feature, *, stream: bool = False) -> ChatRequest:
    """Always construct ChatRequest typed; the wire body is what the matrix
    documents. Helpers below dispatch on Feature and add the right extras."""
    if is_image(feature):
        return ChatRequest(
            model=slug,
            messages=[{"role": "user", "content": _IMAGE_PROMPT}],
            modalities=["image", "text"],
            stream=stream,
        )
    if is_structured(feature):
        return ChatRequest(
            model=slug,
            messages=[{"role": "user", "content": _STRUCTURED_PROMPT}],
            max_completion_tokens=_STRUCTURED_MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "person", "strict": True, "schema": _STRUCTURED_SCHEMA},
            },
            stream=stream,
        )
    return ChatRequest(
        model=slug,
        messages=[{"role": "user", "content": _TEXT_PROMPT}],
        max_completion_tokens=_TEXT_MAX_TOKENS,
        stream=stream,
    )


# ---------------------------------------------------------------------------
# Per-feature assertions
# ---------------------------------------------------------------------------


def _assert_text_unary(client: Gumloop, slug: str) -> None:
    result = client.chat.completions.create(_build_request(slug, Feature.COMPLETIONS_UNARY))
    assert isinstance(result, ChatResult)
    content = _coerce_text(result.choices[0].message.content)
    assert content.strip(), f"{slug}: completion content empty"
    ChatResult.model_validate(result.model_dump(by_alias=True))


def _assert_text_stream(client: Gumloop, slug: str) -> None:
    stream = client.chat.completions.create(_build_request(slug, Feature.COMPLETIONS_STREAM, stream=True))
    assert _is_iterator(stream)
    text, saw_finish, count = _consume_stream(stream)
    assert count > 0, f"{slug}: zero stream chunks"
    assert saw_finish, f"{slug}: stream never emitted finish_reason"
    assert text.strip(), f"{slug}: stream produced no content"


def _assert_structured_unary(client: Gumloop, slug: str) -> None:
    result = client.chat.completions.create(_build_request(slug, Feature.STRUCTURED_UNARY))
    parsed = _parse_structured(result.choices[0].message.content, slug)
    assert isinstance(parsed["name"], str) and isinstance(parsed["age"], int)


def _assert_structured_stream(client: Gumloop, slug: str) -> None:
    stream = client.chat.completions.create(_build_request(slug, Feature.STRUCTURED_STREAM, stream=True))
    text, saw_finish, count = _consume_stream(stream)
    assert count > 0 and saw_finish, f"{slug}: stream did not terminate cleanly"
    parsed = _parse_structured(text, slug)
    assert isinstance(parsed["name"], str) and isinstance(parsed["age"], int)


def _assert_image_unary(client: Gumloop, slug: str) -> None:
    result = client.chat.completions.create(_build_request(slug, Feature.IMAGE_UNARY))
    images = getattr(result.choices[0].message, "images", None) or []
    assert images, f"{slug}: image-unary response carried no images"
    url = images[0].image_url.url if hasattr(images[0], "image_url") else images[0]["image_url"]["url"]
    assert url.startswith("data:image/"), f"{slug}: image url not a data URL: {url[:60]}..."


def _assert_image_stream(client: Gumloop, slug: str) -> None:
    stream = client.chat.completions.create(_build_request(slug, Feature.IMAGE_STREAM, stream=True))
    saw_image = False
    saw_finish = False
    for chunk in stream:
        ChatStreamChunk.model_validate(chunk.model_dump(by_alias=True))
        for choice in chunk.choices:
            delta_images = getattr(choice.delta, "images", None) or []
            if delta_images:
                saw_image = True
                url = (
                    delta_images[0].image_url.url
                    if hasattr(delta_images[0], "image_url")
                    else delta_images[0]["image_url"]["url"]
                )
                assert url.startswith("data:image/"), f"{slug}: stream image not a data URL"
            if choice.finish_reason:
                saw_finish = True
    assert saw_image, f"{slug}: image stream emitted no images"
    assert saw_finish, f"{slug}: image stream missing finish_reason"


_OK_DISPATCH = {
    Feature.COMPLETIONS_UNARY: _assert_text_unary,
    Feature.COMPLETIONS_STREAM: _assert_text_stream,
    Feature.STRUCTURED_UNARY: _assert_structured_unary,
    Feature.STRUCTURED_STREAM: _assert_structured_stream,
    Feature.IMAGE_UNARY: _assert_image_unary,
    Feature.IMAGE_STREAM: _assert_image_stream,
}


# ---------------------------------------------------------------------------
# The matrix test — every (model, feature) cell either passes a positive
# assertion or asserts the backend returns 400 for the unsupported combo.
# ---------------------------------------------------------------------------


_CASES = _gen_cases()


@pytest.mark.live
@pytest.mark.parametrize(
    ("spec", "feature"),
    _CASES,
    ids=[_case_id(c) for c in _CASES],
)
def test_chat_completions_model_matrix(dev_client: Gumloop, spec: ModelSpec, feature: Feature) -> None:
    expect = spec.expectations.get(feature, Expect.OK)

    if expect is Expect.ERR_400:
        # Run the feature and assert the SDK propagates a 400. The backend
        # guards this combo (modality mismatch, unsupported structured, etc.).
        stream_flag = feature in (Feature.COMPLETIONS_STREAM, Feature.STRUCTURED_STREAM, Feature.IMAGE_STREAM)
        request = _build_request(spec.slug, feature, stream=stream_flag)
        with pytest.raises(APIStatusError) as exc_info:
            result = dev_client.chat.completions.create(request)
            # Streaming calls only hit the wire when iterated.
            if hasattr(result, "__iter__"):
                for _ in result:
                    pass
        assert exc_info.value.status_code == 400, (
            f"{spec.slug}/{feature.value}: expected 400, got {exc_info.value.status_code}: {exc_info.value}"
        )
        return

    _OK_DISPATCH[feature](dev_client, spec.slug)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_iterator(obj: object) -> bool:
    return hasattr(obj, "__iter__") and hasattr(obj, "__next__")


def _coerce_text(content) -> str:
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def _consume_stream(stream) -> tuple[str, bool, int]:
    text_parts: list[str] = []
    saw_finish = False
    count = 0
    for chunk in stream:
        assert isinstance(chunk, ChatStreamChunk), f"non-chunk yielded: {type(chunk).__name__}"
        ChatStreamChunk.model_validate(chunk.model_dump(by_alias=True))
        count += 1
        for choice in chunk.choices:
            piece = getattr(choice.delta, "content", None)
            if piece:
                text_parts.append(piece)
            if choice.finish_reason:
                saw_finish = True
    return "".join(text_parts), saw_finish, count


def _parse_structured(content, slug: str) -> dict:
    text = _coerce_text(content).strip()
    assert text, f"{slug}: structured response empty"
    # Defensive: strip ```json fences if a model still wraps despite schema.
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(text)
    assert isinstance(parsed, dict), f"{slug}: structured response not an object: {parsed!r}"
    assert {"name", "age"} <= set(parsed.keys()), f"{slug}: missing keys in {parsed}"
    return parsed
