from __future__ import annotations

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
from gumloop.cli.linked_proxy_key import LinkedProxyConnectionStatus
from gumloop.cli.linked_proxy_key import LinkedProxyRegistration
from gumloop.cli.linked_proxy_key import load_or_create_key
from gumloop.cli.linked_proxy_key import load_registration
from gumloop.cli.linked_proxy_key import save_connection_status
from gumloop.cli.linked_proxy_key import save_registration
from gumloop.cli.main import app
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignInRefused
from gumloop.linked_proxy.sign_in import public_key_text
from tests.sdk.helpers import API_BASE

HOST = "api.gumloop.com"
GATEWAY_URL = "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect"
REGISTRATION = LinkedProxyRegistration(linked_proxy_id="dp-1", name="Ada's laptop", gateway_url=GATEWAY_URL)


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
    monkeypatch.setattr("gumloop.cli.commands.linked_proxy.service_for_current_platform", lambda: fake)
    monkeypatch.setattr("gumloop.cli.commands.linked_proxy.check_tls_not_inspected", lambda: None)
    save_credentials(Credentials(api_key="key", user_id="actor"))
    return fake


@respx.mock
def test_add_registers_and_turns_on_the_service(cli_runner, service, fake_executable_path):
    route = respx.post(f"{API_BASE}/linked-proxies/cli").respond(
        201,
        json={
            "linked_proxy": {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": True},
            "gateway_url": GATEWAY_URL,
        },
    )

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["public_key"] == public_key_text(load_or_create_key(HOST))
    assert load_registration(HOST) == REGISTRATION
    assert service.executable == fake_executable_path / "gumloop"


@respx.mock
def test_add_refuses_a_temporary_credential_override(cli_runner, service):
    route = respx.post(f"{API_BASE}/linked-proxies/cli")

    result = cli_runner.invoke(app, ["browser", "proxy", "link"], env={"GUMLOOP_ACCESS_TOKEN": "other-account"})

    assert result.exit_code == 1
    assert not route.called
    assert not service.installed


@respx.mock
def test_a_refused_linked_proxy_stays_down_after_a_restart(cli_runner, service, monkeypatch):
    save_registration(HOST, REGISTRATION)

    class RefusedConnection:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["linked_proxy_id"] == "dp-1"

        async def run(self) -> None:
            raise SignInRefused("sign_in_refused")

    monkeypatch.setattr("gumloop.cli.commands.linked_proxy.GatewayConnection", RefusedConnection)

    refused = cli_runner.invoke(app, ["browser", "proxy", "run"])
    restarted = cli_runner.invoke(app, ["browser", "proxy", "run"])

    assert (refused.exit_code, restarted.exit_code) == (0, 0)
    assert load_registration(HOST) is None
    assert not respx.calls


@pytest.mark.parametrize(
    ("status", "payload", "expected_token", "kept"),
    [
        (200, {"gateway_token": "token-1"}, "token-1", True),
        (503, {"error": "unavailable"}, GatewayTokenUnavailable, True),
        (404, {"error": {"code": "linked_proxy_not_found"}}, None, False),
        (403, {"error": {"code": "permission_denied"}}, None, False),
    ],
)
@respx.mock
def test_run_signs_in_with_a_gateway_token_and_stops_when_gumloop_refuses_one(
    cli_runner, service, monkeypatch, status, payload, expected_token, kept
):
    save_registration(HOST, REGISTRATION)
    respx.post(f"{API_BASE}/linked-proxies/dp-1/gateway-token").respond(status, json=payload)
    fetched: list[object] = []

    class TokenFetchingConnection:
        def __init__(self, **kwargs: object) -> None:
            self._gateway_token = kwargs["gateway_token"]

        async def run(self) -> None:
            try:
                fetched.append(self._gateway_token())
            except GatewayTokenUnavailable as error:
                fetched.append(type(error))

    monkeypatch.setattr("gumloop.cli.commands.linked_proxy.GatewayConnection", TokenFetchingConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "run"])

    assert result.exit_code == 0, result.output
    assert fetched == ([expected_token] if expected_token is not None else [])
    assert (load_registration(HOST) == REGISTRATION) is kept


@respx.mock
def test_run_signs_in_with_the_login_stored_after_it_started(cli_runner, service, monkeypatch):
    save_registration(HOST, REGISTRATION)
    route = respx.post(f"{API_BASE}/linked-proxies/dp-1/gateway-token").respond(200, json={"gateway_token": "t"})

    class ReconnectingConnection:
        def __init__(self, *, gateway_token: Callable[[], str], **kwargs: object) -> None:
            self._gateway_token = gateway_token

        async def run(self) -> None:
            self._gateway_token()
            save_credentials(Credentials(access_token="fresh"))
            self._gateway_token()

    monkeypatch.setattr("gumloop.cli.commands.linked_proxy.GatewayConnection", ReconnectingConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "run"])

    assert result.exit_code == 0, result.output
    assert [call.request.headers["authorization"] for call in route.calls] == ["Bearer key", "Bearer fresh"]


@pytest.mark.parametrize(
    ("running", "connected", "last_error", "expected"),
    [
        (False, True, None, "not running. Run `gumloop browser proxy link` to start."),
        (True, False, "can't reach the gateway (connection refused)", "connecting. Last attempt failed: can't reach"),
        (True, True, None, "connected since"),
    ],
)
def test_status_reads_the_running_linked_proxy_connection(
    cli_runner, service, monkeypatch, running, connected, last_error, expected
):
    save_registration(HOST, REGISTRATION)
    save_connection_status(
        HOST,
        LinkedProxyConnectionStatus(connected=connected, since=datetime.now(timezone.utc), last_error=last_error),
    )
    monkeypatch.setattr("gumloop.cli.commands.linked_proxy.is_running", lambda host: running)

    result = cli_runner.invoke(app, ["browser", "proxy", "status"])

    assert result.exit_code == 0, result.output
    assert f'"Ada\'s laptop": {expected}' in " ".join(result.output.split())


@pytest.mark.parametrize("command", [["browser", "proxy", "unlink"], ["logout"]])
@respx.mock
def test_removing_deletes_the_linked_proxy_then_the_key(cli_runner, service, command):
    service.installed = True
    save_registration(HOST, REGISTRATION)
    load_or_create_key(HOST)
    route = respx.delete(f"{API_BASE}/linked-proxies/dp-1").respond(204)

    result = cli_runner.invoke(app, command)

    assert result.exit_code == 0, result.output
    assert route.called
    assert not service.installed
    assert keyring.get_password(KEYRING_SERVICE, f"linked-proxy:{HOST}") is None
    assert load_registration(HOST) is None


@pytest.mark.parametrize(("login_has_linked_proxy", "kept"), [(True, True), (False, False)])
def test_removing_another_backends_linked_proxy_keeps_the_service_only_while_the_login_needs_it(
    cli_runner, service, login_has_linked_proxy, kept
):
    service.installed = True
    if login_has_linked_proxy:
        save_registration(HOST, REGISTRATION)

    result = cli_runner.invoke(
        app, ["browser", "proxy", "unlink"], env={"GUMLOOP_BASE_URL": "https://staging.api.gumloop.com"}
    )

    assert result.exit_code == 0, result.output
    assert service.installed is kept


@respx.mock
def test_remove_keeps_the_key_when_gumloop_cannot_delete_the_linked_proxy(cli_runner, service):
    save_registration(HOST, REGISTRATION)
    key = public_key_text(load_or_create_key(HOST))
    respx.delete(f"{API_BASE}/linked-proxies/dp-1").respond(503, json={"error": "unavailable"})

    result = cli_runner.invoke(app, ["browser", "proxy", "unlink"])

    assert result.exit_code == 1
    assert public_key_text(load_or_create_key(HOST)) == key
    assert load_registration(HOST) == REGISTRATION
