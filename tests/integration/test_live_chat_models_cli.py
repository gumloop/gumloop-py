"""CLI mirror of test_live_chat_models.

Drives the same (model x feature) matrix as the SDK test, but via
``uv run gumloop chat completions create ...`` invoked as a subprocess.
Catches regressions in the entrypoint script, sys.argv parsing, packaging,
and the Typer/Rich output layer that the SDK-level test doesn't exercise.

Run with::

    cd gumloop-py
    pytest tests/integration/test_live_chat_models_cli.py -m live -n 8
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.integration._matrix import _IMAGE_PROMPT
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
from tests.integration._matrix import is_stream
from tests.integration._matrix import is_structured


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBPROCESS_TIMEOUT_SECS = 180


@pytest.fixture(scope="session")
def schema_file_path() -> Path:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="gumloop_schema_")
    os.close(fd)
    p = Path(path)
    p.write_text(json.dumps(_STRUCTURED_SCHEMA))
    yield p
    p.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def cli_env(api_key: str, user_id: str) -> dict[str, str]:
    """Env dict for subprocess invocation — same auth/base-url the SDK test uses.

    Inherits PATH/HOME/etc. from the parent so ``uv run`` works, but strips
    any pre-existing GUMLOOP auth vars so a stale ``gumloop login`` token in
    the user's shell can't shadow the test's API key. The CLI prefers
    ``GUMLOOP_ACCESS_TOKEN`` over ``GUMLOOP_API_KEY`` (see
    ``gumloop/cli/main.py``); a stale token surfaces as 401s here while the
    SDK test (which only takes api_key) keeps working.
    """
    base_url = os.environ.get("GUMLOOP_BASE_URL")
    if not base_url:
        pytest.fail(
            "GUMLOOP_BASE_URL is required for the CLI live matrix; "
            "populate gumloop-py/.env first",
            pytrace=False,
        )
    env = os.environ.copy()
    for stale in ("GUMLOOP_ACCESS_TOKEN", "GUMLOOP_REFRESH_TOKEN", "GUMLOOP_TEAM_ID"):
        env.pop(stale, None)
    env["GUMLOOP_API_KEY"] = api_key
    env["GUMLOOP_USER_ID"] = user_id
    env["GUMLOOP_BASE_URL"] = base_url
    # Force unbuffered IO so streaming chunks land in stdout deterministically.
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _build_cli_args(spec: ModelSpec, feature: Feature, schema_file: Path) -> list[str]:
    """Return argv tail (after `gumloop chat completions create`) for this cell.

    Always pass --json so we can parse output uniformly:
      * unary -> single JSON document on stdout
      * stream -> ndjson, one ChatStreamChunk JSON per line
    """
    stream = is_stream(feature)
    if is_image(feature):
        prompt = _IMAGE_PROMPT
        extra = ["--modality", "image", "--modality", "text"]
        max_tokens = _TEXT_MAX_TOKENS
    elif is_structured(feature):
        prompt = _STRUCTURED_PROMPT
        extra = ["--schema-file", str(schema_file), "--schema-name", "person"]
        max_tokens = _STRUCTURED_MAX_TOKENS
    else:
        prompt = _TEXT_PROMPT
        extra = []
        max_tokens = _TEXT_MAX_TOKENS

    return [
        prompt,
        "-m", spec.slug,
        "--max-completion-tokens", str(max_tokens),
        "--stream" if stream else "--no-stream",
        "--json",
        *extra,
    ]


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "gumloop", "chat", "completions", "create", *args],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECS,
        check=False,
    )


def _parse_ndjson(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _stream_text(chunks: list[dict]) -> str:
    return "".join(
        (choice.get("delta", {}) or {}).get("content", "") or ""
        for chunk in chunks
        for choice in chunk.get("choices", [])
    )


def _stream_saw_image(chunks: list[dict]) -> bool:
    for chunk in chunks:
        for choice in chunk.get("choices", []):
            for img in (choice.get("delta", {}) or {}).get("images") or []:
                url = (img.get("image_url") or {}).get("url", "")
                if url.startswith("data:image/"):
                    return True
    return False


def _unary_content(payload: dict) -> str:
    content = payload["choices"][0]["message"].get("content")
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def _unary_image_url(payload: dict) -> str:
    images = payload["choices"][0]["message"].get("images") or []
    if not images:
        return ""
    return (images[0].get("image_url") or {}).get("url", "")


_CASES = _gen_cases()


@pytest.mark.live
@pytest.mark.parametrize(
    ("spec", "feature"),
    _CASES,
    ids=[_case_id(c) for c in _CASES],
)
def test_cli_chat_completions_matrix(
    cli_env: dict[str, str],
    schema_file_path: Path,
    spec: ModelSpec,
    feature: Feature,
) -> None:
    expect = spec.expectations.get(feature, Expect.OK)
    args = _build_cli_args(spec, feature, schema_file_path)
    proc = _run_cli(args, cli_env)

    if expect is Expect.ERR_400:
        assert proc.returncode == 1, _diag(spec, feature, proc, "expected exit 1")
        # --json routes the error envelope to stderr via print_json_error.
        try:
            payload = json.loads(proc.stderr)
        except json.JSONDecodeError as exc:
            pytest.fail(
                _diag(spec, feature, proc, f"stderr was not JSON: {exc}"),
                pytrace=False,
            )
        status = payload.get("error", {}).get("status_code")
        if status == 401:
            pytest.fail(
                _diag(spec, feature, proc, "got 401 — auth env vars likely shadowed; "
                "check that GUMLOOP_ACCESS_TOKEN isn't set in your shell"),
                pytrace=False,
            )
        assert status == 400, _diag(spec, feature, proc, f"expected status_code 400, got {status}")
        return

    assert proc.returncode == 0, _diag(spec, feature, proc, f"exit {proc.returncode}")

    if is_stream(feature):
        chunks = _parse_ndjson(proc.stdout)
        assert chunks, f"{spec.slug}/{feature.value}: ndjson stream produced no lines"
        if feature is Feature.IMAGE_STREAM:
            assert _stream_saw_image(chunks), f"{spec.slug}: image stream emitted no images"
        elif feature is Feature.STRUCTURED_STREAM:
            text = _stream_text(chunks)
            parsed = _parse_structured_text(text, spec.slug)
            assert isinstance(parsed["name"], str) and isinstance(parsed["age"], int)
        else:
            text = _stream_text(chunks)
            assert text.strip(), f"{spec.slug}: stream produced no text"
        return

    payload = json.loads(proc.stdout)
    if feature is Feature.IMAGE_UNARY:
        url = _unary_image_url(payload)
        assert url.startswith("data:image/"), (
            f"{spec.slug}: image-unary response had no data-URL image (got {url[:60]!r})"
        )
    elif feature is Feature.STRUCTURED_UNARY:
        parsed = _parse_structured_text(_unary_content(payload), spec.slug)
        assert isinstance(parsed["name"], str) and isinstance(parsed["age"], int)
    else:
        assert _unary_content(payload).strip(), f"{spec.slug}: unary content empty"


def _diag(spec: ModelSpec, feature: Feature, proc: subprocess.CompletedProcess, msg: str) -> str:
    return (
        f"{spec.slug}/{feature.value}: {msg}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )


def _parse_structured_text(text: str, slug: str) -> dict:
    text = text.strip()
    assert text, f"{slug}: structured response empty"
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(text)
    assert isinstance(parsed, dict), f"{slug}: structured response not an object: {parsed!r}"
    assert {"name", "age"} <= set(parsed.keys()), f"{slug}: missing keys in {parsed}"
    return parsed
