"""Implementation smoke tests for the CLI mirror of the Skill Sync v1 corpus."""

from __future__ import annotations

from tests.skill_sync_fixtures import EXPECTED_CORPUS_SHA256
from tests.skill_sync_fixtures import calculate_corpus_sha256
from tests.skill_sync_fixtures import load_json


def test_cli_calculated_corpus_fingerprint_matches_pinned_value() -> None:
    """The complete CLI mirror matches the canonical shared corpus fingerprint."""
    calculated = calculate_corpus_sha256()

    assert calculated == EXPECTED_CORPUS_SHA256


def test_cli_loads_unsupported_response_version_fixture() -> None:
    """The CLI transport fixture identifies contract version two as unsupported."""
    fixture = load_json("responses/unsupported-response-version.json")

    response_version = fixture["headers"]["X-Gumloop-Sync-Contract-Version"]

    assert response_version == "2"


def test_cli_parses_shared_content_vector_file() -> None:
    """The CLI mirror exposes a parseable v1 content-vector document."""
    fixture = load_json("hashes/content-v1.json")

    format_version = fixture["format_version"]

    assert format_version == 1


def test_cli_parses_shared_manifest_vector_file() -> None:
    """The CLI mirror exposes a parseable v1 manifest-vector document."""
    fixture = load_json("hashes/manifest-v1.json")

    format_version = fixture["format_version"]

    assert format_version == 1
