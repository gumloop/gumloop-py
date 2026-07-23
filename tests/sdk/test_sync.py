from __future__ import annotations

import httpx
import pytest
import respx

from gumloop._http import HttpClient
from gumloop._version import __version__
from gumloop.errors import APIStatusError
from gumloop.resources.sync import SYNC_BUNDLE_CONTENT_TYPE
from gumloop.resources.sync import SYNC_CLI_VERSION_HEADER
from gumloop.resources.sync import Sync
from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.errors import SyncError
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import auth_header
from tests.sdk.helpers import request_json
from tests.skill_sync_fixtures import load_json

PLAN_URL = f"{API_BASE}/skills/sync/plan"
DOWNLOAD_URL = f"{API_BASE}/skills/sync/download"


@pytest.fixture
def api_key_client() -> HttpClient:
    return HttpClient(
        base_url=API_BASE,
        stream_base_url=API_BASE,
        access_token="personal-token",
        user_id="user_fixture",
        timeout=30.0,
        stream_timeout=30.0,
    )


@pytest.fixture
def oauth_client() -> HttpClient:
    return HttpClient(
        base_url=API_BASE,
        stream_base_url=API_BASE,
        access_token="oauth-token",
        user_id=None,
        timeout=30.0,
        stream_timeout=30.0,
    )


@pytest.fixture
def api_key_sync(api_key_client: HttpClient) -> Sync:
    return Sync(api_key_client)


@pytest.fixture
def oauth_sync(oauth_client: HttpClient) -> Sync:
    return Sync(oauth_client)


def _sync_response_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }
    headers.update(overrides)
    return headers


def _download_response_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "Content-Type": SYNC_BUNDLE_CONTENT_TYPE,
    }
    headers.update(overrides)
    return headers


class TestPlan:
    @respx.mock
    def test_plan_sends_cli_version_header_auth_and_body_for_api_key(self, api_key_sync: Sync) -> None:
        """A personal API key plan request carries auth, CLI version, and the plan body."""
        route = respx.post(PLAN_URL).mock(
            return_value=httpx.Response(
                200, json=load_json("responses/normal-plan.json"), headers=_sync_response_headers()
            )
        )

        result = api_key_sync.plan(organization_id="org_fixture")

        assert result.organization.organization_id == "org_fixture"
        request = route.calls[0].request
        assert auth_header(request) == "Bearer personal-token"
        assert request.headers["x-auth-key"] == "user_fixture"
        assert request.headers[SYNC_CLI_VERSION_HEADER] == __version__
        assert request_json(request) == {"organization_id": "org_fixture"}

    @respx.mock
    def test_plan_omits_organization_id_when_not_provided(self, api_key_sync: Sync) -> None:
        """A plan request omits organization_id when the caller leaves it unset."""
        route = respx.post(PLAN_URL).mock(
            return_value=httpx.Response(
                200, json=load_json("responses/normal-plan.json"), headers=_sync_response_headers()
            )
        )

        api_key_sync.plan()

        body = request_json(route.calls[0].request)
        assert body == {}

    @respx.mock
    def test_plan_oauth_uses_bearer_without_x_auth_key(self, oauth_sync: Sync) -> None:
        """An OAuth plan request sends only the bearer token."""
        route = respx.post(PLAN_URL).mock(
            return_value=httpx.Response(
                200, json=load_json("responses/normal-plan.json"), headers=_sync_response_headers()
            )
        )

        oauth_sync.plan()

        request = route.calls[0].request
        assert auth_header(request) == "Bearer oauth-token"
        assert "x-auth-key" not in request.headers

    @respx.mock
    def test_plan_parses_valid_response_and_accepts_additive_fields(self, api_key_sync: Sync) -> None:
        """A valid plan response parses into the typed plan model."""
        payload = load_json("responses/normal-plan.json")
        payload["future_field"] = {"safe": True}
        respx.post(PLAN_URL).mock(return_value=httpx.Response(200, json=payload, headers=_sync_response_headers()))

        result = api_key_sync.plan()

        assert result.skill_count == 1
        assert result.model_extra == {"future_field": {"safe": True}}

    @respx.mock
    def test_plan_malformed_json_raises_invalid_desired_state(self, api_key_sync: Sync) -> None:
        """Malformed plan JSON becomes a stable invalid_desired_state sync error."""
        respx.post(PLAN_URL).mock(
            return_value=httpx.Response(200, content=b"not-json", headers=_sync_response_headers())
        )

        with pytest.raises(SyncError) as exc_info:
            api_key_sync.plan()

        assert exc_info.value.code == "invalid_desired_state"

    @respx.mock
    def test_plan_invalid_model_raises_invalid_desired_state(self, api_key_sync: Sync) -> None:
        """An invalid successful plan payload becomes invalid_desired_state."""
        payload = load_json("responses/normal-plan.json")
        payload["skill_count"] = 99
        respx.post(PLAN_URL).mock(return_value=httpx.Response(200, json=payload, headers=_sync_response_headers()))

        with pytest.raises(SyncError) as exc_info:
            api_key_sync.plan()

        assert exc_info.value.code == "invalid_desired_state"

    @respx.mock
    def test_plan_api_error_preserves_api_status_error(self, api_key_sync: Sync) -> None:
        """HTTP plan failures remain APIStatusError for orchestration."""
        error_body = load_json("responses/lost-membership.json")
        respx.post(PLAN_URL).mock(return_value=httpx.Response(403, json=error_body))

        with pytest.raises(APIStatusError) as exc_info:
            api_key_sync.plan()

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "insufficient_organization_permissions"

    @respx.mock
    def test_plan_transport_failure_preserves_httpx_error(self, api_key_sync: Sync) -> None:
        """Transport failures during plan remain httpx errors."""
        respx.post(PLAN_URL).mock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(httpx.ConnectError):
            api_key_sync.plan()


class TestDownload:
    @respx.mock
    def test_download_sends_cli_version_header_auth_and_body(self, api_key_sync: Sync) -> None:
        """A download request carries auth, CLI version, and the organization body."""
        bundle = b"PK\x03\x04bundle"
        route = respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=bundle, headers=_download_response_headers())
        )

        result = api_key_sync.download(organization_id="org_fixture")

        assert isinstance(result, SyncBundleDownload)
        assert result.content == bundle
        request = route.calls[0].request
        assert auth_header(request) == "Bearer personal-token"
        assert request.headers["x-auth-key"] == "user_fixture"
        assert request.headers[SYNC_CLI_VERSION_HEADER] == __version__
        assert request_json(request) == {"organization_id": "org_fixture"}

    @respx.mock
    def test_download_omits_organization_id_when_not_provided(self, api_key_sync: Sync) -> None:
        """A download request omits organization_id when the caller leaves it unset."""
        route = respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=b"PK\x03\x04", headers=_download_response_headers())
        )

        api_key_sync.download()

        assert request_json(route.calls[0].request) == {}

    @respx.mock
    def test_download_oauth_uses_bearer_without_x_auth_key(self, oauth_sync: Sync) -> None:
        """An OAuth download request sends only the bearer token."""
        route = respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=b"PK\x03\x04", headers=_download_response_headers())
        )

        oauth_sync.download()

        request = route.calls[0].request
        assert auth_header(request) == "Bearer oauth-token"
        assert "x-auth-key" not in request.headers

    @respx.mock
    def test_download_valid_bundle_returns_frozen_download(self, api_key_sync: Sync) -> None:
        """A valid bundle response returns the frozen download dataclass."""
        bundle = b"PK\x03\x04valid-bundle"
        respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=bundle, headers=_download_response_headers())
        )

        result = api_key_sync.download()

        assert result == SyncBundleDownload(
            content=bundle,
            content_type=SYNC_BUNDLE_CONTENT_TYPE,
        )

    @respx.mock
    def test_download_accepts_optional_mime_parameter_from_httpx(self, api_key_sync: Sync) -> None:
        """An optional MIME parameter on the bundle content type is accepted."""
        bundle = b"PK\x03\x04"
        respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(
                200,
                content=bundle,
                headers=_download_response_headers(**{"Content-Type": f"{SYNC_BUNDLE_CONTENT_TYPE}; charset=binary"}),
            )
        )

        result = api_key_sync.download()

        assert result.content_type == SYNC_BUNDLE_CONTENT_TYPE

    @respx.mock
    def test_download_invalid_content_type_raises_download_failed(self, api_key_sync: Sync) -> None:
        """An invalid bundle content type becomes download_failed."""
        respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(
                200,
                content=b"PK\x03\x04",
                headers=_download_response_headers(**{"Content-Type": "application/octet-stream"}),
            )
        )

        with pytest.raises(SyncError) as exc_info:
            api_key_sync.download()

        assert exc_info.value.code == "download_failed"

    @respx.mock
    def test_download_missing_content_type_raises_download_failed(self, api_key_sync: Sync) -> None:
        """A missing content type header becomes download_failed."""
        headers = _download_response_headers()
        del headers["Content-Type"]
        respx.post(DOWNLOAD_URL).mock(return_value=httpx.Response(200, content=b"PK\x03\x04", headers=headers))

        with pytest.raises(SyncError) as exc_info:
            api_key_sync.download()

        assert exc_info.value.code == "download_failed"

    @respx.mock
    @pytest.mark.implementation
    def test_download_exceeding_transfer_limit_raises_download_failed(
        self,
        api_key_sync: Sync,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A bundle larger than the configured transfer limit becomes download_failed."""
        monkeypatch.setattr("gumloop.resources.sync.SYNC_BUNDLE_MAX_BYTES", 8)
        respx.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(200, content=b"123456789", headers=_download_response_headers())
        )

        with pytest.raises(SyncError) as exc_info:
            api_key_sync.download()

        assert exc_info.value.code == "download_failed"

    @respx.mock
    def test_download_api_error_preserves_api_status_error(self, api_key_sync: Sync) -> None:
        """HTTP download failures remain APIStatusError for orchestration."""
        error_body = load_json("responses/below-pro.json")
        respx.post(DOWNLOAD_URL).mock(return_value=httpx.Response(403, json=error_body))

        with pytest.raises(APIStatusError) as exc_info:
            api_key_sync.download()

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "organization_sync_requires_pro"

    @respx.mock
    def test_download_transport_failure_preserves_httpx_error(self, api_key_sync: Sync) -> None:
        """Transport failures during download remain httpx errors."""
        respx.post(DOWNLOAD_URL).mock(side_effect=httpx.ReadTimeout("timed out"))

        with pytest.raises(httpx.ReadTimeout):
            api_key_sync.download()
