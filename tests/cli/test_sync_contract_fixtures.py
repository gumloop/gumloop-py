"""Behavioral contract tests for CLI parsing of Skill Sync v1 responses."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from gumloop.errors import to_api_error
from gumloop.types import CliSyncPlanResponse
from tests.skill_sync_fixtures import load_json

PLAN_CASES = [
    pytest.param("responses/normal-plan.json", 1, id="normal"),
    pytest.param("responses/normal-empty-plan.json", 0, id="normal-empty"),
]
ERROR_CASES = [
    pytest.param(
        "responses/lost-membership.json",
        403,
        "insufficient_organization_permissions",
        id="lost-membership",
    ),
    pytest.param(
        "responses/below-pro.json",
        403,
        "organization_sync_requires_pro",
        id="below-pro",
    ),
    pytest.param(
        "responses/cli-upgrade-required.json",
        426,
        "cli_upgrade_required",
        id="upgrade-required",
    ),
]
DELETE_FIELD = object()
INVALID_NESTED_CASES = [
    pytest.param(
        "responses/normal-plan.json",
        ("skill_count",),
        -1,
        id="negative-top-level-count",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("skill_count",),
        2,
        id="top-level-manifest-count-mismatch",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("manifest", "algorithm"),
        "sha512",
        id="invalid-manifest-algorithm",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("manifest", "format_version"),
        2,
        id="invalid-manifest-version",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("manifest", "skill_count"),
        -1,
        id="negative-manifest-count",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("limits", "files_per_skill"),
        1001,
        id="invalid-files-per-skill-limit",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("limits", "bytes_per_file"),
        26_214_401,
        id="invalid-bytes-per-file-limit",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("limits", "bundle_transfer_bytes"),
        104_857_601,
        id="invalid-transfer-limit",
    ),
    pytest.param(
        "responses/normal-plan.json",
        ("limits", "total_uncompressed_bytes"),
        209_715_201,
        id="invalid-uncompressed-limit",
    ),
]


@pytest.mark.parametrize(("fixture_path", "expected_skill_count"), PLAN_CASES)
def test_cli_parses_complete_success_plan(
    fixture_path: str,
    expected_skill_count: int,
) -> None:
    """A valid shared plan parses with its hard-coded complete skill count."""
    payload = load_json(fixture_path)

    response = CliSyncPlanResponse.model_validate(payload)

    assert response.skill_count == expected_skill_count
    assert response.manifest.skill_count == expected_skill_count


@pytest.mark.parametrize(
    ("fixture_path", "status_code", "expected_code"),
    ERROR_CASES,
)
def test_cli_error_translation_preserves_sync_code(
    fixture_path: str,
    status_code: int,
    expected_code: str,
) -> None:
    """A shared public error becomes the exact stable CLI-facing error code."""
    response = httpx.Response(status_code, json=load_json(fixture_path))

    error = to_api_error(response)

    assert error.code == expected_code


def test_cli_normal_empty_is_valid_replacement_plan() -> None:
    """The CLI accepts normal-empty replacement state with the v1 empty hash."""
    payload = load_json("responses/normal-empty-plan.json")

    response = CliSyncPlanResponse.model_validate(payload)

    assert response.skill_count == 0
    assert response.manifest.hash == "4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a"


def test_cli_ignores_unknown_additive_success_field() -> None:
    """An additive success field remains available without breaking typed parsing."""
    payload = load_json("responses/normal-plan.json")
    payload["future_field"] = {"safe": True}

    response = CliSyncPlanResponse.model_validate(payload)

    assert response.model_extra == {"future_field": {"safe": True}}


def test_cli_rejects_invalid_manifest_hash() -> None:
    """An invalid successful manifest hash rejects the complete response."""
    payload = load_json("responses/normal-plan.json")
    payload["manifest"]["hash"] = "invalid"

    with pytest.raises(ValidationError):
        CliSyncPlanResponse.model_validate(payload)


@pytest.mark.parametrize(
    ("fixture_path", "field_path", "invalid_value"),
    INVALID_NESTED_CASES,
)
def test_cli_rejects_invalid_nested_contract_field(
    fixture_path: str,
    field_path: tuple[str | int, ...],
    invalid_value: object,
) -> None:
    """Each invalid nested count, version, or limit is rejected."""
    payload = load_json(fixture_path)
    _mutate_nested_field(payload, field_path, invalid_value)

    with pytest.raises(ValidationError):
        CliSyncPlanResponse.model_validate(payload)


def _mutate_nested_field(
    payload: dict[str, Any],
    field_path: tuple[str | int, ...],
    value: object,
) -> None:
    parent: Any = payload
    for part in field_path[:-1]:
        parent = parent[part]
    field = field_path[-1]
    if value is DELETE_FIELD:
        del parent[field]
    else:
        parent[field] = value
