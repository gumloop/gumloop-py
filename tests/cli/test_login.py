from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import load_credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_api_key_login_persists_key_user_id_and_base_url(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    result = cli_runner.invoke(
        app,
        ["login", "--api-key", "gum_test_key", "--user-id", "user_abc", "--json"],
    )

    assert result.exit_code == 0, result.output
    creds = load_credentials()
    assert creds.api_key == "gum_test_key"
    assert creds.access_token is None
    assert creds.user_id == "user_abc"
    assert creds.auth_method == "api_key"
    # Default base URL is persisted alongside the credentials.
    assert creds.base_url


@respx.mock
def test_api_key_login_sends_user_id_as_x_auth_key_on_validation(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    cli_runner.invoke(
        app,
        ["login", "--api-key", "gum_test", "--user-id", "user_abc", "--json"],
    )

    headers = route.calls[0].request.headers
    assert headers["Authorization"] == "Bearer gum_test"
    assert headers["x-auth-key"] == "user_abc"


@respx.mock
def test_access_token_login_persists_token_as_oauth_method(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    result = cli_runner.invoke(app, ["login", "--access-token", "acct_xyz", "--json"])

    assert result.exit_code == 0, result.output
    creds = load_credentials()
    assert creds.access_token == "acct_xyz"
    assert creds.api_key is None
    assert creds.auth_method == "oauth"


@respx.mock
def test_login_validates_credential_against_models_endpoint_with_bearer_header(
    cli_runner: CliRunner,
) -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    cli_runner.invoke(app, ["login", "--api-key", "gum_test", "--user-id", "user_abc", "--json"])

    assert route.called
    assert route.calls[0].request.headers["Authorization"] == "Bearer gum_test"


@respx.mock
def test_login_with_invalid_credentials_exits_nonzero_and_does_not_save(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/models").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad token", "type": "auth"}})
    )

    result = cli_runner.invoke(app, ["login", "--api-key", "bad", "--user-id", "user_abc", "--json"])

    assert result.exit_code != 0
    assert load_credentials().api_key is None


@respx.mock
def test_login_against_custom_base_url_stores_it_in_keychain(cli_runner: CliRunner) -> None:
    custom = "https://example.com/api/v1"
    respx.get(f"{custom}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    result = cli_runner.invoke(
        app,
        ["--base-url", custom, "login", "--api-key", "gum_local", "--user-id", "u", "--json"],
    )

    assert result.exit_code == 0, result.output
    creds = load_credentials()
    assert creds.base_url == custom


def test_logout_clears_all_stored_credentials(cli_runner: CliRunner) -> None:
    save_credentials(
        Credentials(
            access_token="tok",
            refresh_token="ref",
            api_key="key",
            user_id="u",
            base_url="https://x/api/v1",
        )
    )

    result = cli_runner.invoke(app, ["logout", "--json"])

    assert result.exit_code == 0
    cleared = load_credentials()
    assert not cleared.has_any
    assert cleared.user_id is None
    assert cleared.base_url is None
