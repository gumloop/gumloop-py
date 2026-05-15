from __future__ import annotations

import httpx
import pytest
import respx

from gumloop import APIStatusError
from gumloop import AuthenticationError
from gumloop.cli.context import CliContext
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import load_credentials
from gumloop.cli.credentials import save_credentials
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import OAUTH_BASE


@respx.mock
def test_call_with_refresh_retries_after_401_using_refresh_token() -> None:
    models_route = respx.get(f"{API_BASE}/models").mock(
        side_effect=[
            httpx.Response(401, json={"error": {"message": "expired", "code": "invalid_token"}}),
            httpx.Response(200, json={"model_groups": [{"name": "auto"}]}),
        ]
    )
    refresh_route = respx.post(f"{OAUTH_BASE}/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "fresh_acct", "refresh_token": "fresh_refresh"})
    )

    cli = CliContext(
        credentials=Credentials(access_token="stale_acct", refresh_token="orig_refresh"),
    )

    result = cli.call_with_refresh(lambda client: client.models.list())

    assert result.model_groups == [{"name": "auto"}]
    assert models_route.call_count == 2
    assert refresh_route.call_count == 1
    assert cli.credentials.access_token == "fresh_acct"
    assert cli.credentials.refresh_token == "fresh_refresh"

    persisted = load_credentials()
    assert persisted.access_token == "fresh_acct"
    assert persisted.refresh_token == "fresh_refresh"


@respx.mock
def test_call_with_refresh_does_not_retry_without_refresh_token() -> None:
    models_route = respx.get(f"{API_BASE}/models").mock(
        return_value=httpx.Response(401, json={"error": {"message": "expired"}})
    )

    cli = CliContext(
        credentials=Credentials(access_token="stale", refresh_token=None),
    )

    with pytest.raises(APIStatusError):
        cli.call_with_refresh(lambda client: client.models.list())

    assert models_route.call_count == 1


@respx.mock
def test_call_with_refresh_does_not_attempt_refresh_for_api_key_auth() -> None:
    models_route = respx.get(f"{API_BASE}/models").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key"}})
    )
    refresh_route = respx.post(f"{OAUTH_BASE}/oauth/token")

    cli = CliContext(
        credentials=Credentials(api_key="bad_key", user_id="user_abc"),
    )

    with pytest.raises(APIStatusError):
        cli.call_with_refresh(lambda client: client.models.list())

    assert models_route.call_count == 1
    assert refresh_route.call_count == 0


@respx.mock
def test_call_with_refresh_clears_credentials_and_raises_auth_error_when_refresh_fails() -> None:
    """If the refresh endpoint rejects the refresh token, wipe stale creds
    and surface a clear AuthenticationError instead of a raw HTTP error."""
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(401, json={"error": {"message": "expired"}}))
    respx.post(f"{OAUTH_BASE}/oauth/token").mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))

    save_credentials(Credentials(access_token="stale", refresh_token="dead_refresh"))
    cli = CliContext(
        credentials=Credentials(access_token="stale", refresh_token="dead_refresh"),
    )

    with pytest.raises(AuthenticationError):
        cli.call_with_refresh(lambda client: client.models.list())

    cleared = load_credentials()
    assert cleared.access_token is None
    assert cleared.refresh_token is None


def test_effective_base_url_layers_override_over_creds_over_sdk_default() -> None:
    from gumloop._client import DEFAULT_BASE_URL

    no_state = CliContext(credentials=Credentials())
    assert no_state.effective_base_url == DEFAULT_BASE_URL

    stored = CliContext(credentials=Credentials(base_url="https://staging.api.gumloop.com/api/v1"))
    assert stored.effective_base_url == "https://staging.api.gumloop.com/api/v1"

    overridden = CliContext(
        credentials=Credentials(base_url="https://staging.api.gumloop.com/api/v1"),
        base_url_override="http://localhost:8080/api/v1",
    )
    assert overridden.effective_base_url == "http://localhost:8080/api/v1"
