from __future__ import annotations

import httpx

from gumloop.errors import to_api_error


def test_to_api_error_reads_flat_public_error_message_and_code() -> None:
    response = httpx.Response(
        403,
        json={
            "error": "subscription_tier_required",
            "message": "This feature isn't available on your current plan. Upgrade to continue.",
            "metadata": {"minimum_tier": "pro"},
        },
    )

    error = to_api_error(response)

    assert error.status_code == 403
    assert error.code == "subscription_tier_required"
    assert str(error) == ("This feature isn't available on your current plan. Upgrade to continue.")
    assert error.details == {"minimum_tier": "pro"}


def test_to_api_error_reads_nested_error_envelope() -> None:
    response = httpx.Response(
        403,
        json={
            "error": {
                "code": "organization_sync_requires_pro",
                "message": "Organization skill sync requires a Pro plan.",
                "type": "permission_error",
                "param": None,
                "details": {},
            }
        },
    )

    error = to_api_error(response)

    assert error.code == "organization_sync_requires_pro"
    assert str(error) == "Organization skill sync requires a Pro plan."
    assert error.type == "permission_error"


def test_to_api_error_reads_nested_details() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "code": "skill_not_found",
                "message": "Skill not found.",
                "type": "invalid_request_error",
                "param": "skill_ids",
                "details": {"skill_ids": ["sk_does_not_exist"]},
            }
        },
    )

    error = to_api_error(response)

    assert error.code == "skill_not_found"
    assert error.param == "skill_ids"
    assert error.details == {"skill_ids": ["sk_does_not_exist"]}


def test_to_api_error_exposes_legacy_bare_string_code() -> None:
    response = httpx.Response(403, json={"error": "tier_required_pro"})

    error = to_api_error(response)

    assert error.code == "tier_required_pro"
    assert str(error) == "Gumloop API returned HTTP 403: tier_required_pro"
    assert error.details == {}


def test_to_api_error_preserves_legacy_top_level_context() -> None:
    response = httpx.Response(
        403,
        json={
            "error": "tier_required_pro",
            "minimum_tier": "pro",
            "denied_keys": ["gumloop_api"],
        },
    )

    error = to_api_error(response)

    assert error.code == "tier_required_pro"
    assert error.details == {
        "minimum_tier": "pro",
        "denied_keys": ["gumloop_api"],
    }


def test_to_api_error_reads_oauth_error_description() -> None:
    response = httpx.Response(
        401,
        json={
            "error": "invalid_token",
            "error_description": "Missing subject",
        },
    )

    error = to_api_error(response)

    assert error.code == "invalid_token"
    assert str(error) == "Missing subject"
    assert error.details == {}
