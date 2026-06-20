"""Tests for ``gumloop.errors`` — covers both error envelope shapes the
backend returns."""

from __future__ import annotations

import httpx
import pytest
import respx

from gumloop import Gumloop
from gumloop.errors import (
    APIStatusError,
    GumloopError,
    _legacy_details_from_body,
    _legacy_message,
    _synthesize_error_type,
    to_api_error,
)

API_BASE = "https://api.gumloop.com/api/v1"


@pytest.fixture
def client() -> Gumloop:
    return Gumloop(api_key="test-key")


# ---------------------------------------------------------------------------
# _synthesize_error_type — mirrors backend's api_error_type() mapping.
# ---------------------------------------------------------------------------


class TestSynthesizeErrorType:
    @pytest.mark.parametrize(
        "status_code,expected",
        [
            (401, "authentication_error"),
            (403, "permission_error"),
            (404, "not_found_error"),
            (429, "rate_limit_error"),
            (500, "api_error"),
            (502, "api_error"),
            (503, "api_error"),
            (400, "invalid_request_error"),
            (422, "invalid_request_error"),
        ],
    )
    def test_status_to_type(self, status_code: int, expected: str) -> None:
        assert _synthesize_error_type(status_code) == expected


# ---------------------------------------------------------------------------
# _legacy_details_from_body — gathers loose top-level fields.
# ---------------------------------------------------------------------------


class TestLegacyDetailsFromBody:
    def test_collects_non_reserved_fields(self) -> None:
        body = {
            "error": "policy_denied",
            "denied_keys": ["apollo_organization_enrichment"],
            "user_type": "feature-restricted",
        }
        assert _legacy_details_from_body(body) == {
            "denied_keys": ["apollo_organization_enrichment"],
            "user_type": "feature-restricted",
        }

    def test_excludes_envelope_keys(self) -> None:
        body = {
            "error": "x",
            "code": "x",
            "message": "x",
            "type": "x",
            "param": "x",
            "details": {"x": 1},
            "custom_field": "kept",
        }
        assert _legacy_details_from_body(body) == {"custom_field": "kept"}

    def test_empty_body(self) -> None:
        assert _legacy_details_from_body({}) == {}
        assert _legacy_details_from_body({"error": "code_only"}) == {}


# ---------------------------------------------------------------------------
# _legacy_message — synthesizes a meaningful exception message.
# ---------------------------------------------------------------------------


class TestLegacyMessage:
    def test_code_alone_when_no_details(self) -> None:
        assert _legacy_message("policy_denied", {}, 403) == "policy_denied"

    def test_code_with_single_detail(self) -> None:
        message = _legacy_message(
            "policy_denied",
            {"denied_keys": ["apollo_organization_enrichment"]},
            403,
        )
        assert message == "policy_denied (denied_keys=['apollo_organization_enrichment'])"

    def test_code_with_multiple_details(self) -> None:
        message = _legacy_message(
            "tier_required_enterprise",
            {"denied_keys": ["organization:manage_sso"], "minimum_tier": "enterprise"},
            403,
        )
        assert "tier_required_enterprise" in message
        assert "minimum_tier='enterprise'" in message
        assert "denied_keys=['organization:manage_sso']" in message

    def test_empty_code_falls_back_to_http_message(self) -> None:
        assert _legacy_message("", {}, 403) == "Gumloop API returned HTTP 403"


# ---------------------------------------------------------------------------
# APIStatusError — direct construction with both body shapes.
# ---------------------------------------------------------------------------


class TestAPIStatusErrorCanonicalEnvelope:
    """``body["error"]`` is a dict — the canonical api_error envelope."""

    def test_extracts_all_fields_from_envelope(self) -> None:
        body = {
            "error": {
                "code": "policy_denied",
                "message": "Access to 'x' is restricted.",
                "type": "permission_error",
                "param": None,
                "details": {"denied_keys": ["x"]},
            }
        }
        exc = APIStatusError("ignored", status_code=403, body=body)
        assert exc.code == "policy_denied"
        assert exc.type == "permission_error"
        assert exc.param is None
        assert exc.details == {"denied_keys": ["x"]}
        assert exc.body == body

    def test_missing_inner_fields_default_to_none_or_empty(self) -> None:
        body = {"error": {"code": "x"}}
        exc = APIStatusError("ignored", status_code=400, body=body)
        assert exc.code == "x"
        assert exc.type is None
        assert exc.param is None
        assert exc.details == {}


class TestAPIStatusErrorLegacyFlatShape:
    """``body["error"]`` is a string — the legacy permission deny shape."""

    def test_policy_denied(self) -> None:
        body = {
            "error": "policy_denied",
            "denied_keys": ["apollo_organization_enrichment"],
        }
        exc = APIStatusError("ignored", status_code=403, body=body)
        assert exc.code == "policy_denied"
        assert exc.type == "permission_error"
        assert exc.param is None
        assert exc.details == {"denied_keys": ["apollo_organization_enrichment"]}

    def test_tier_required(self) -> None:
        body = {
            "error": "tier_required_enterprise",
            "minimum_tier": "enterprise",
            "denied_keys": ["organization:manage_sso"],
        }
        exc = APIStatusError("ignored", status_code=403, body=body)
        assert exc.code == "tier_required_enterprise"
        assert exc.type == "permission_error"
        assert exc.details == {
            "minimum_tier": "enterprise",
            "denied_keys": ["organization:manage_sso"],
        }

    def test_feature_restricted(self) -> None:
        body = {
            "error": "feature_restricted",
            "user_type": "feature-restricted",
            "denied_keys": ["organization:access_gumstack"],
        }
        exc = APIStatusError("ignored", status_code=403, body=body)
        assert exc.code == "feature_restricted"
        assert exc.type == "permission_error"
        assert exc.details == {
            "user_type": "feature-restricted",
            "denied_keys": ["organization:access_gumstack"],
        }

    def test_unauthorized_acl_action(self) -> None:
        body = {"error": "unauthorized_gummie_update"}
        exc = APIStatusError("ignored", status_code=403, body=body)
        assert exc.code == "unauthorized_gummie_update"
        assert exc.type == "permission_error"
        assert exc.details == {}

    def test_type_synthesized_from_status_code(self) -> None:
        body = {"error": "not_found"}
        exc = APIStatusError("ignored", status_code=404, body=body)
        assert exc.type == "not_found_error"


class TestAPIStatusErrorDefensive:
    def test_non_dict_body_yields_no_extracted_fields(self) -> None:
        exc = APIStatusError("fallback", status_code=500, body="plain text response")
        assert exc.code is None
        assert exc.type is None
        assert exc.param is None
        assert exc.details == {}

    def test_missing_error_field_yields_no_extracted_fields(self) -> None:
        exc = APIStatusError("fallback", status_code=500, body={"unrelated": "x"})
        assert exc.code is None
        assert exc.details == {}


# ---------------------------------------------------------------------------
# to_api_error — message resolution across both shapes.
# ---------------------------------------------------------------------------


class TestToApiErrorMessage:
    """Verifies the resolution order: envelope.message > legacy synth > fallback."""

    def test_canonical_envelope_message_is_used_as_exception_message(self) -> None:
        response = httpx.Response(
            403,
            json={
                "error": {
                    "code": "policy_denied",
                    "message": "Access to 'apollo' is restricted by your org policy.",
                    "type": "permission_error",
                }
            },
        )
        exc = to_api_error(response)
        assert str(exc) == "Access to 'apollo' is restricted by your org policy."

    def test_legacy_flat_synthesizes_message_with_context(self) -> None:
        response = httpx.Response(
            403,
            json={
                "error": "policy_denied",
                "denied_keys": ["apollo_organization_enrichment"],
            },
        )
        exc = to_api_error(response)
        assert "policy_denied" in str(exc)
        assert "denied_keys" in str(exc)
        assert "apollo_organization_enrichment" in str(exc)

    def test_legacy_flat_code_only_no_context(self) -> None:
        response = httpx.Response(403, json={"error": "unauthorized_gummie_update"})
        exc = to_api_error(response)
        assert str(exc) == "unauthorized_gummie_update"

    def test_non_json_body_falls_back_to_generic_message(self) -> None:
        response = httpx.Response(500, text="Internal Server Error (plain text)")
        exc = to_api_error(response)
        assert str(exc) == "Gumloop API returned HTTP 500"

    def test_empty_error_field_falls_back_to_generic(self) -> None:
        response = httpx.Response(503, json={"unrelated": "field"})
        exc = to_api_error(response)
        assert str(exc) == "Gumloop API returned HTTP 503"


# ---------------------------------------------------------------------------
# End-to-end via the SDK client — proves legacy shape no longer surfaces as
# the opaque "Gumloop API returned HTTP 403" string.
# ---------------------------------------------------------------------------


@respx.mock
def test_legacy_flat_shape_surfaces_meaningful_message_to_sdk_caller(client: Gumloop) -> None:
    """Regression guard for the GMLP-9102 visibility bug: a permission deny
    response in the legacy flat shape should produce a meaningful exception
    message and populated ``code`` / ``details``, not a generic HTTP fallback."""
    body = {
        "error": "policy_denied",
        "denied_keys": ["apollo_organization_enrichment"],
    }
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(403, json=body))

    with pytest.raises(APIStatusError) as exc_info:
        client.models.list()

    exc = exc_info.value
    assert exc.status_code == 403
    assert exc.code == "policy_denied"
    assert exc.type == "permission_error"
    assert exc.details == {"denied_keys": ["apollo_organization_enrichment"]}
    assert "policy_denied" in str(exc)
    assert "apollo_organization_enrichment" in str(exc)
    assert "Gumloop API returned HTTP" not in str(exc)


def test_gumloop_error_hierarchy() -> None:
    """Sanity check that all SDK errors share the GumloopError base, so SDK
    consumers can catch all SDK errors with a single ``except``."""
    assert issubclass(APIStatusError, GumloopError)
