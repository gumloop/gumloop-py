from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from pathlib import Path

import keyring
import pytest
import respx

from gumloop.cli.credentials import KEYRING_SERVICE
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.custom_proxy_key import CustomProxyConnectionStatus
from gumloop.cli.custom_proxy_key import CustomProxyRegistration
from gumloop.cli.custom_proxy_key import load_or_create_key
from gumloop.cli.custom_proxy_key import load_registration
from gumloop.cli.custom_proxy_key import save_connection_status
from gumloop.cli.custom_proxy_key import save_registration
from gumloop.cli.custom_proxy_service import NoBackgroundService
from gumloop.cli.main import app
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignInRefused
from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.sign_in import public_key_text
from gumloop.types import CustomProxyGatewayToken
from tests.sdk.helpers import API_BASE

HOST = "api.gumloop.com"
GATEWAY_URL = "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect"


def _registration(**changes: str) -> CustomProxyRegistration:
    """What `link` saves for the keychain's key and the `service` fixture's login."""
    return CustomProxyRegistration(
        custom_proxy_id="dp-1",
        name="Ada's laptop",
        gateway_url=GATEWAY_URL,
        public_key=public_key_text(load_or_create_key(HOST)),
        user_id="actor",
    ).model_copy(update=changes)


def _access_token(user_id: str) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"sub": user_id}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


class FakeService:
    def __init__(self, *, installed: bool = False) -> None:
        self.installed = installed
        self.executable: Path | None = None

    def install(self, executable_path: Path) -> None:
        self.installed = True
        self.executable = executable_path

    def remove(self) -> None:
        self.installed = False

    def is_installed(self) -> bool:
        return self.installed


@pytest.fixture
def service(monkeypatch) -> FakeService:
    fake = FakeService()
    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.service_for_current_platform", lambda: fake)
    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.check_tls_not_inspected", lambda: None)
    save_credentials(Credentials(api_key="key", user_id="actor"))
    return fake


@respx.mock
def test_add_registers_and_turns_on_the_service(cli_runner, service, fake_executable_path):
    route = respx.post(f"{API_BASE}/custom-proxies").respond(
        201,
        json={
            "custom_proxy": {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": True},
            "gateway_url": GATEWAY_URL,
        },
    )

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["public_key"] == public_key_text(load_or_create_key(HOST))
    assert load_registration(HOST) == _registration()
    assert service.executable == fake_executable_path / "gumloop"


@respx.mock
def test_link_without_a_background_service_registers_and_points_to_connect(cli_runner, service, monkeypatch):
    def no_background_service() -> FakeService:
        raise NoBackgroundService("no systemd user session")

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.service_for_current_platform", no_background_service)
    respx.post(f"{API_BASE}/custom-proxies").respond(
        201,
        json={
            "custom_proxy": {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": True},
            "gateway_url": GATEWAY_URL,
        },
    )

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 0, result.output
    assert load_registration(HOST) == _registration()
    assert not service.installed
    assert "Run `gumloop browser proxy connect`" in " ".join(result.output.split())


@respx.mock
def test_add_refuses_a_temporary_credential_override(cli_runner, service):
    route = respx.post(f"{API_BASE}/custom-proxies")

    result = cli_runner.invoke(app, ["browser", "proxy", "link"], env={"GUMLOOP_ACCESS_TOKEN": "other-account"})

    assert result.exit_code == 1
    assert not route.called
    assert not service.installed


@respx.mock
def test_a_refused_custom_proxy_stays_down_after_a_restart(cli_runner, service, monkeypatch):
    save_registration(HOST, _registration())

    class RefusedConnection:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["linked_proxy_id"] == "dp-1"

        async def run(self) -> None:
            raise SignInRefused("personal_custom_proxy_not_found")

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", RefusedConnection)

    refused = cli_runner.invoke(app, ["browser", "proxy", "connect"])
    restarted = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert (refused.exit_code, restarted.exit_code) == (0, 0)
    assert load_registration(HOST) is None
    assert not respx.calls


def test_connect_says_it_connected_once_across_reconnects(cli_runner, service, monkeypatch):
    save_registration(HOST, _registration())

    class ReconnectingConnection:
        def __init__(self, *, on_connected: Callable[[], None], **kwargs: object) -> None:
            self._on_connected = on_connected

        async def run(self) -> None:
            self._on_connected()
            self._on_connected()

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", ReconnectingConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert " ".join(result.stdout.split()).count("Connected. Agents can now send browser traffic") == 1


@pytest.mark.parametrize(("flags", "printed"), [([], False), (["-v"], True)])
def test_connect_prints_the_sites_agents_open_only_when_verbose(cli_runner, service, monkeypatch, flags, printed):
    save_registration(HOST, _registration())

    class OpeningConnection:
        def __init__(self, *, on_open: Callable[[Target], None] | None, **kwargs: object) -> None:
            self._on_open = on_open

        async def run(self) -> None:
            if self._on_open is not None:
                self._on_open(Target(host="example.com", port=443))

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", OpeningConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect", *flags])

    assert result.exit_code == 0, result.output
    assert ("example.com" in result.stdout) is printed


@pytest.mark.parametrize(
    ("reason", "kept", "expected"),
    [
        ("personal_custom_proxy_not_found", False, "This computer was unlinked from Gumloop."),
        (
            "organization_permission_required",
            True,
            "Your organization's roles don't allow you to use personal proxies.",
        ),
        ("route_not_found", True, "Personal proxies aren't available for your organization yet."),
    ],
)
def test_connect_keeps_the_registration_unless_the_custom_proxy_was_removed(
    cli_runner, service, monkeypatch, reason, kept, expected
):
    save_registration(HOST, _registration())

    class RefusedConnection:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(self) -> None:
            raise SignInRefused(reason)

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", RefusedConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert (load_registration(HOST) == _registration()) is kept
    assert expected in " ".join(result.stderr.split())


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (
            403,
            {"error": "policy_denied", "denied_keys": ["organization:use_personal_proxies"]},
            "Your organization's roles don't allow you to use personal proxies. Ask an admin to turn them on.",
        ),
        (403, {"error": "tier_required_enterprise"}, "Personal proxies need an Enterprise plan."),
        (404, {"error": "route_not_found"}, "Personal proxies aren't available for your organization yet."),
    ],
)
@respx.mock
def test_link_says_why_personal_proxies_are_off(cli_runner, service, status, payload, expected):
    respx.post(f"{API_BASE}/custom-proxies").respond(status, json=payload)

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 1
    assert expected in " ".join(result.stderr.split())
    assert load_registration(HOST) is None
    assert not service.installed


@pytest.mark.parametrize(
    ("status", "payload", "expected_token", "kept"),
    [
        (200, {"gateway_token": "token-1"}, "token-1", True),
        (503, {"error": "unavailable"}, GatewayTokenUnavailable, True),
        (404, {"error": {"code": "personal_custom_proxy_not_found"}}, None, False),
        (403, {"error": "policy_denied", "denied_keys": ["organization:use_personal_proxies"]}, None, True),
        (403, {"error": {"code": "organization_permission_required"}}, None, True),
        (404, {"error": "route_not_found"}, None, True),
        (403, {"error": {"code": "not_a_code_the_cli_knows"}}, GatewayTokenUnavailable, True),
        (404, {"error": "not_found"}, GatewayTokenUnavailable, True),
    ],
)
@respx.mock
def test_connect_signs_in_with_a_gateway_token_and_stops_when_gumloop_refuses_one(
    cli_runner, service, monkeypatch, status, payload, expected_token, kept
):
    save_registration(HOST, _registration())
    respx.post(f"{API_BASE}/custom-proxies/dp-1/gateway-token").respond(status, json=payload)
    fetched: list[object] = []

    class TokenFetchingConnection:
        def __init__(self, *, gateway_token: Callable[[], CustomProxyGatewayToken], **kwargs: object) -> None:
            self._gateway_token = gateway_token

        async def run(self) -> None:
            try:
                fetched.append(self._gateway_token().gateway_token)
            except GatewayTokenUnavailable as error:
                fetched.append(type(error))

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", TokenFetchingConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert fetched == ([expected_token] if expected_token is not None else [])
    assert (load_registration(HOST) == _registration()) is kept


@respx.mock
def test_connect_signs_in_with_the_login_stored_after_it_started(cli_runner, service, monkeypatch):
    save_registration(HOST, _registration())
    route = respx.post(f"{API_BASE}/custom-proxies/dp-1/gateway-token").respond(200, json={"gateway_token": "t"})

    class ReconnectingConnection:
        def __init__(self, *, gateway_token: Callable[[], CustomProxyGatewayToken], **kwargs: object) -> None:
            self._gateway_token = gateway_token

        async def run(self) -> None:
            self._gateway_token()
            save_credentials(Credentials(access_token="fresh"))
            self._gateway_token()

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", ReconnectingConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert [call.request.headers["authorization"] for call in route.calls] == ["Bearer key", "Bearer fresh"]


@pytest.mark.parametrize(
    "login",
    [Credentials(api_key="key", user_id="someone-else"), Credentials(access_token=_access_token("someone-else"))],
)
@respx.mock
def test_connect_as_someone_else_disconnects_and_keeps_the_registration(cli_runner, service, monkeypatch, login):
    save_registration(HOST, _registration())
    save_credentials(login)
    route = respx.post(f"{API_BASE}/custom-proxies/dp-1/gateway-token")

    class TokenFetchingConnection:
        def __init__(self, *, gateway_token: Callable[[], CustomProxyGatewayToken], **kwargs: object) -> None:
            self._gateway_token = gateway_token

        async def run(self) -> None:
            self._gateway_token()

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", TokenFetchingConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert not route.called
    assert load_registration(HOST) == _registration()
    assert "You logged in to Gumloop as someone else" in " ".join(result.stderr.split())


def test_connect_forgets_a_registration_whose_key_is_gone(cli_runner, service, monkeypatch):
    save_registration(HOST, _registration(public_key="a key the keychain no longer has"))

    class UnusedConnection:
        def __init__(self, **kwargs: object) -> None:
            pytest.fail("connected with a key Gumloop doesn't know")

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", UnusedConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert load_registration(HOST) is None
    assert "key is gone from the OS keychain" in " ".join(result.stderr.split())


@respx.mock
def test_link_registers_again_when_the_keychain_key_changed(cli_runner, service):
    save_registration(HOST, _registration(public_key="a key the keychain no longer has"))
    route = respx.post(f"{API_BASE}/custom-proxies").respond(
        201,
        json={
            "custom_proxy": {"id": "dp-2", "name": "Ada's laptop", "kind": "cli", "is_default": True},
            "gateway_url": GATEWAY_URL,
        },
    )

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 0, result.output
    assert route.called
    assert load_registration(HOST) == _registration(custom_proxy_id="dp-2")


@respx.mock
def test_link_refuses_a_computer_linked_to_someone_else(cli_runner, service):
    save_registration(HOST, _registration(user_id="someone-else"))
    route = respx.post(f"{API_BASE}/custom-proxies")

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 1
    assert not route.called
    assert not service.installed
    assert "linked to another Gumloop user" in " ".join(result.stderr.split())


@pytest.mark.parametrize(
    ("running", "connected", "last_error", "expected"),
    [
        (False, True, None, "not running. Run `gumloop browser proxy link` to start."),
        (True, False, "can't reach the gateway (connection refused)", "connecting. Last attempt failed: can't reach"),
        (True, True, None, "connected since"),
    ],
)
def test_status_reads_the_running_custom_proxy_connection(
    cli_runner, service, monkeypatch, running, connected, last_error, expected
):
    save_registration(HOST, _registration())
    save_connection_status(
        HOST,
        CustomProxyConnectionStatus(connected=connected, since=datetime.now(timezone.utc), last_error=last_error),
    )
    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.is_running", lambda host: running)

    result = cli_runner.invoke(app, ["browser", "proxy", "status"])

    assert result.exit_code == 0, result.output
    assert f'"Ada\'s laptop": {expected}' in " ".join(result.output.split())


def test_status_without_a_background_service_points_to_connect(cli_runner, service, monkeypatch):
    def no_background_service() -> FakeService:
        raise NoBackgroundService("no systemd user session")

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.service_for_current_platform", no_background_service)
    save_registration(HOST, _registration())

    result = cli_runner.invoke(app, ["browser", "proxy", "status"])

    assert result.exit_code == 0, result.output
    assert "not running. Run `gumloop browser proxy connect` to start." in " ".join(result.output.split())


@pytest.mark.parametrize("command", [["browser", "proxy", "unlink"], ["logout"]])
@respx.mock
def test_removing_deletes_the_custom_proxy_then_the_key(cli_runner, service, command):
    service.installed = True
    save_registration(HOST, _registration())
    load_or_create_key(HOST)
    route = respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(204)

    result = cli_runner.invoke(app, command)

    assert result.exit_code == 0, result.output
    assert route.called
    assert not service.installed
    assert keyring.get_password(KEYRING_SERVICE, f"custom-proxy:{HOST}") is None
    assert load_registration(HOST) is None


@pytest.mark.parametrize(("login_has_custom_proxy", "kept"), [(True, True), (False, False)])
def test_removing_another_backends_custom_proxy_keeps_the_service_only_while_the_login_needs_it(
    cli_runner, service, login_has_custom_proxy, kept
):
    service.installed = True
    if login_has_custom_proxy:
        save_registration(HOST, _registration())

    result = cli_runner.invoke(
        app, ["browser", "proxy", "unlink"], env={"GUMLOOP_BASE_URL": "https://staging.api.gumloop.com"}
    )

    assert result.exit_code == 0, result.output
    assert service.installed is kept


@respx.mock
def test_remove_keeps_the_key_when_gumloop_cannot_delete_the_custom_proxy(cli_runner, service):
    save_registration(HOST, _registration())
    key = public_key_text(load_or_create_key(HOST))
    respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(503, json={"error": "unavailable"})

    result = cli_runner.invoke(app, ["browser", "proxy", "unlink"])

    assert result.exit_code == 1
    assert public_key_text(load_or_create_key(HOST)) == key
    assert load_registration(HOST) == _registration()
