from __future__ import annotations

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop import __version__
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import load_credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


def test_version_long_flag_prints_version_and_exits_cleanly(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_version_short_flag_prints_version_and_exits_cleanly(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["-V"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_short_alias_renders_top_level_help(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["-h"])

    assert result.exit_code == 0
    assert "Usage" in result.output


@respx.mock
def test_env_access_token_overrides_stored_api_key(cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    save_credentials(Credentials(api_key="stored_key", user_id="u"))
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env_token")

    cli_runner.invoke(app, ["mcp", "list", "--json"])

    assert route.calls[0].request.headers["Authorization"] == "Bearer env_token"
    # x-auth-key must NOT be sent when env access_token is in play - the
    # stored api_key + user_id should be ignored entirely.
    assert "x-auth-key" not in route.calls[0].request.headers


@respx.mock
def test_env_api_key_is_used_when_no_access_token_or_stored_creds(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    monkeypatch.setenv("GUMLOOP_API_KEY", "env_api_key")

    cli_runner.invoke(app, ["mcp", "list", "--json"])

    assert route.calls[0].request.headers["Authorization"] == "Bearer env_api_key"


@respx.mock
def test_env_api_key_plus_user_id_sends_x_auth_key_header(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    monkeypatch.setenv("GUMLOOP_API_KEY", "env_api_key")
    monkeypatch.setenv("GUMLOOP_USER_ID", "env_user_id")

    cli_runner.invoke(app, ["mcp", "list", "--json"])

    sent = route.calls[0].request.headers
    assert sent["Authorization"] == "Bearer env_api_key"
    assert sent["x-auth-key"] == "env_user_id"


@respx.mock
def test_env_api_key_clears_stored_oauth_so_we_dont_send_a_stale_bearer(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the user sets GUMLOOP_API_KEY but has a stored OAuth token,
    the env var wins outright - we don't keep sending the stored oauth bearer."""
    route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    save_credentials(Credentials(access_token="stale_oauth", refresh_token="stale_refresh"))
    monkeypatch.setenv("GUMLOOP_API_KEY", "env_api_key")
    monkeypatch.setenv("GUMLOOP_USER_ID", "u")

    cli_runner.invoke(app, ["mcp", "list", "--json"])

    assert route.calls[0].request.headers["Authorization"] == "Bearer env_api_key"
    # And the stored OAuth token wasn't mutated on disk - env override is in-memory only.
    persisted = load_credentials()
    assert persisted.access_token == "stale_oauth"


@respx.mock
def test_base_url_flag_overrides_stored_base_url_for_this_invocation(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key", user_id="u", base_url="https://stored.example/api/v1"))
    custom = "https://custom.example/api/v1"
    route = respx.get(f"{custom}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))

    cli_runner.invoke(app, ["--base-url", custom, "mcp", "list", "--json"])

    assert route.called
    # And the stored base_url isn't mutated.
    assert load_credentials().base_url == "https://stored.example/api/v1"


@respx.mock
def test_env_team_id_is_applied_for_the_current_invocation(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    route = respx.get(f"{API_BASE}/mcp/servers").mock(return_value=httpx.Response(200, json={"servers": []}))
    save_credentials(Credentials(api_key="key", user_id="u"))
    monkeypatch.setenv("GUMLOOP_TEAM_ID", "transient_team")

    cli_runner.invoke(app, ["mcp", "list", "--json"])

    assert route.calls[0].request.url.params["team_id"] == "transient_team"


def test_non_tty_login_without_method_flag_errors_clearly(cli_runner: CliRunner) -> None:
    """Scripted/CI callers should get a clear error instead of a silent OAuth attempt."""
    result = cli_runner.invoke(app, ["login", "--json"], input="")

    assert result.exit_code != 0
    assert "non-interactive" in result.output or "non-interactive" in (result.stderr or "")
