"""Client-side conformance tests for the shared Skill Sync v1 hashes."""

from __future__ import annotations

import base64

import pytest

from gumloop.sync.errors import SyncError
from gumloop.sync.hashing import compute_content_hash
from gumloop.sync.hashing import compute_manifest_hash
from gumloop.types import CliSyncBundleSkill
from tests.skill_sync_fixtures import load_json

CONTENT_VECTORS = load_json("hashes/content-v1.json")["vectors"]
INVALID_PATHS = load_json("hashes/content-v1.json")["invalid_paths"]
MANIFEST_VECTORS = load_json("hashes/manifest-v1.json")["vectors"]


def _content_files(vector: dict[str, object]) -> dict[str, bytes]:
    return {
        item["path"]: base64.b64decode(item["content_base64"])
        for item in vector["files"]  # type: ignore[union-attr]
    }


def _manifest_skills(vector: dict[str, object]) -> list[CliSyncBundleSkill]:
    return [
        CliSyncBundleSkill(
            skill_id=item["skill_id"],
            install_name="ignored-by-manifest-hash",
            published_version_id=item["published_version_id"],
            content_hash=item["content_hash"],
        )
        for item in vector["skills"]  # type: ignore[union-attr]
    ]


@pytest.mark.parametrize("vector", CONTENT_VECTORS, ids=lambda vector: vector["id"])
def test_content_hash_matches_shared_v1_vector(vector: dict[str, object]) -> None:
    """Every canonical file-map vector produces the backend-owned v1 digest."""
    files = _content_files(vector)

    digest = compute_content_hash(files)

    assert digest == vector["expected_sha256"]


@pytest.mark.parametrize("vector", MANIFEST_VECTORS, ids=lambda vector: vector["id"])
def test_manifest_hash_matches_shared_v1_vector(vector: dict[str, object]) -> None:
    """Every canonical tuple vector produces the backend-owned v1 digest."""
    skills = _manifest_skills(vector)

    digest = compute_manifest_hash(skills)

    assert digest == vector["expected_sha256"]


@pytest.mark.parametrize("vector", INVALID_PATHS, ids=lambda vector: vector["id"])
def test_content_hash_rejects_shared_invalid_path(vector: dict[str, str]) -> None:
    """An unsafe shared path never becomes a local content identity."""
    files = {vector["path"]: b"content"}

    with pytest.raises(SyncError, match="path"):
        compute_content_hash(files)
