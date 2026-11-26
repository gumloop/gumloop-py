from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs

import httpx
import keyring
import pytest
import respx

from gumloop._version import __version__
from gumloop.cli.credentials import KEYRING_SERVICE
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.custom_proxy_key import CustomProxyRegistration
from gumloop.cli.custom_proxy_key import load_or_create_key
from gumloop.cli.custom_proxy_key import load_registration
from gumloop.cli.custom_proxy_key import save_registration
from gumloop.cli.custom_proxy_service import NoBackgroundService
from gumloop.cli.main import app
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignInRefused
from gumloop.linked_proxy.sign_in import public_key_text
from gumloop.types import CustomProxyGatewayToken
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import OAUTH_BASE

HOST = "api.gumloop.com"
GATEWAY_URL = "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect"
REGISTERED = {
    "custom_proxy": {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": True},
    "gateway_url": GATEWAY_URL,
}


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


class FixedHostname(ModuleType):
    """Stands in for the command module's ``socket`` name."""

    def __init__(self) -> None:
        super().__init__("socket")

    def gethostname(self) -> str:
        return "Ada's MacBook Pro"


def _no_background_service(fake: FakeService) -> FakeService:
    raise NoBackgroundService("no systemd user session")


class RecordingConnections:
    """Stands in for ``GatewayConnection``: records each construction and connects nowhere."""

    def __init__(self) -> None:
        self.constructed: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> RecordingConnections:
        self.constructed.append(kwargs)
        return self

    async def run(self) -> None:
        pass


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
    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.executable_version", lambda executable: __version__)
    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.socket", FixedHostname())
    save_credentials(Credentials(api_key="key", user_id="actor"))
    return fake


@pytest.mark.parametrize(
    ("platform_service", "installed_executable"),
    [(lambda fake: fake, lambda bin_dir: bin_dir / "gumloop"), (_no_background_service, lambda bin_dir: None)],
    ids=["background service", "no background service"],
)
@respx.mock
def test_add_registers_and_turns_on_the_service(
    cli_runner, service, monkeypatch, fake_executable_path, platform_service, installed_executable
):
    monkeypatch.setattr(
        "gumloop.cli.commands.custom_proxy.service_for_current_platform", lambda: platform_service(service)
    )
    route = respx.post(f"{API_BASE}/custom-proxies").respond(201, json=REGISTERED)

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "kind": "cli",
        "name": "Ada's MacBook Pro",
        "public_key": public_key_text(load_or_create_key(HOST)),
        "machine_name": "Ada's MacBook Pro",
        "cli_version": __version__,
    }
    assert load_registration(HOST) == _registration()
    assert service.executable == installed_executable(fake_executable_path)


@respx.mock
def test_add_refuses_a_temporary_credential_override(cli_runner, service):
    route = respx.post(f"{API_BASE}/custom-proxies")

    result = cli_runner.invoke(app, ["browser", "proxy", "link"], env={"GUMLOOP_ACCESS_TOKEN": "other-account"})

    assert result.exit_code == 1
    assert not route.called
    assert not service.installed


def test_a_refused_custom_proxy_keeps_a_registration_linked_while_it_was_connected(cli_runner, service, monkeypatch):
    save_registration(HOST, _registration())
    relinked = _registration(custom_proxy_id="dp-2")

    class RefusedAfterRelinkConnection:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(self) -> None:
            save_registration(HOST, relinked)
            raise SignInRefused("personal_custom_proxy_not_found")

    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", RefusedAfterRelinkConnection)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert load_registration(HOST) == relinked


@pytest.mark.parametrize(
    ("status", "payload", "expected_fetched", "kept"),
    [
        (200, {"gateway_token": "token-1"}, ["token-1"], True),
        (503, {"error": "unavailable"}, [GatewayTokenUnavailable], True),
        (404, {"error": {"code": "personal_custom_proxy_not_found"}}, [], False),
        (403, {"error": {"code": "not_a_code_the_cli_knows"}}, [], True),
        (404, {"error": "not_found"}, [], True),
        (401, {"error": "unauthorized"}, [], True),
        (404, {"error": "route_not_found"}, [GatewayTokenUnavailable], True),
        (
            403,
            {"error": "feature_restricted", "denied_keys": ["organization:use_personal_proxies"]},
            [GatewayTokenUnavailable],
            True,
        ),
        (429, {"error": "rate_limited"}, [GatewayTokenUnavailable], True),
    ],
)
@respx.mock
def test_connect_signs_in_with_a_gateway_token_and_stops_when_gumloop_refuses_one(
    cli_runner, service, monkeypatch, status, payload, expected_fetched, kept
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
    assert fetched == expected_fetched
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


def _forget_key() -> None:
    keyring.delete_password(KEYRING_SERVICE, f"custom-proxy:{HOST}")


@pytest.mark.parametrize(
    ("reset_keychain", "key_kept"),
    [(lambda: None, True), (_forget_key, False)],
    ids=["changed", "empty"],
)
def test_connect_with_a_lost_key_stops_without_making_one_and_keeps_the_registration(
    cli_runner, service, monkeypatch, reset_keychain, key_kept
):
    lost = _registration(public_key="a key the keychain no longer has")
    save_registration(HOST, lost)
    reset_keychain()
    connections = RecordingConnections()
    monkeypatch.setattr("gumloop.cli.commands.custom_proxy.GatewayConnection", connections)

    result = cli_runner.invoke(app, ["browser", "proxy", "connect"])

    assert result.exit_code == 0, result.output
    assert connections.constructed == []
    assert load_registration(HOST) == lost
    assert (keyring.get_password(KEYRING_SERVICE, f"custom-proxy:{HOST}") is not None) is key_kept


@pytest.mark.parametrize(("was_default", "default_route_called"), [(True, True), (False, False)])
@respx.mock
def test_link_replaces_the_custom_proxy_of_a_lost_key_and_keeps_its_default(
    cli_runner, service, was_default, default_route_called
):
    save_registration(HOST, _registration(public_key="a key the keychain no longer has"))
    lost = {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": was_default}
    replacement = {"id": "dp-2", "name": "Ada's laptop", "kind": "cli", "is_default": False}
    respx.get(f"{API_BASE}/custom-proxies").respond(200, json={"custom_proxies": [lost], "limit": 5})
    deleted = respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(204)
    registered = respx.post(f"{API_BASE}/custom-proxies").respond(
        201, json={"custom_proxy": replacement, "gateway_url": GATEWAY_URL}
    )
    made_default = respx.post(f"{API_BASE}/custom-proxies/dp-2/default").respond(
        200, json={"custom_proxy": {**replacement, "is_default": True}}
    )

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 0, result.output
    assert deleted.called
    assert registered.called
    assert made_default.called is default_route_called
    assert load_registration(HOST) == _registration(custom_proxy_id="dp-2")


@respx.mock
def test_link_with_a_lost_key_keeps_its_custom_proxy_when_registering_fails(cli_runner, service):
    lost = _registration(public_key="a key the keychain no longer has")
    save_registration(HOST, lost)
    listed = {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": True}
    respx.get(f"{API_BASE}/custom-proxies").respond(200, json={"custom_proxies": [listed], "limit": 5})
    deleted = respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(204)
    respx.post(f"{API_BASE}/custom-proxies").respond(422, json={"error": "invalid_request"})

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 1
    assert not deleted.called
    assert load_registration(HOST) == lost
    assert not service.installed


@respx.mock
def test_link_refuses_a_computer_linked_to_someone_else(cli_runner, service):
    save_registration(HOST, _registration(user_id="someone-else"))
    route = respx.post(f"{API_BASE}/custom-proxies")

    result = cli_runner.invoke(app, ["browser", "proxy", "link"])

    assert result.exit_code == 1
    assert not route.called
    assert not service.installed


@pytest.mark.parametrize("command", [["browser", "proxy", "unlink"], ["logout"]])
@pytest.mark.parametrize(
    ("status", "payload"), [(204, None), (404, {"error": {"code": "personal_custom_proxy_not_found"}})]
)
@respx.mock
def test_removing_deletes_the_custom_proxy_then_the_key(cli_runner, service, command, status, payload):
    service.installed = True
    save_registration(HOST, _registration())
    load_or_create_key(HOST)
    route = respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(status, json=payload)

    result = cli_runner.invoke(app, command)

    assert result.exit_code == 0, result.output
    assert route.called
    assert not service.installed
    assert keyring.get_password(KEYRING_SERVICE, f"custom-proxy:{HOST}") is None
    assert load_registration(HOST) is None


@respx.mock
def test_logout_unlinks_with_the_stored_login_not_a_credential_override(cli_runner, service):
    save_registration(HOST, _registration())
    route = respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(204)

    result = cli_runner.invoke(app, ["logout"], env={"GUMLOOP_API_KEY": "someone-elses-key"})

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["Authorization"] == "Bearer key"
    assert load_registration(HOST) is None


@respx.mock
def test_logout_revokes_the_refresh_token_the_unlink_refresh_replaced(cli_runner, service):
    save_credentials(Credentials(access_token=_access_token("actor"), refresh_token="orig_refresh"))
    save_registration(HOST, _registration())
    respx.delete(f"{API_BASE}/custom-proxies/dp-1").mock(
        side_effect=[httpx.Response(401, json={"error": {"code": "invalid_token"}}), httpx.Response(204)]
    )
    respx.post(f"{OAUTH_BASE}/oauth/token").respond(
        200, json={"access_token": _access_token("actor"), "refresh_token": "fresh_refresh"}
    )
    revoke = respx.post(f"{OAUTH_BASE}/oauth/revoke").respond(200)

    result = cli_runner.invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert parse_qs(revoke.calls.last.request.content.decode())["token"] == ["fresh_refresh"]


@respx.mock
def test_logout_revokes_the_stored_refresh_token_at_the_backend_it_came_from(cli_runner, service):
    save_credentials(Credentials(access_token=_access_token("actor"), refresh_token="stored_refresh"))
    revoke = respx.post(f"{OAUTH_BASE}/oauth/revoke").respond(200)

    result = cli_runner.invoke(app, ["--base-url", "https://staging.api.gumloop.com/api/v1", "logout"])

    assert result.exit_code == 0, result.output
    assert parse_qs(revoke.calls.last.request.content.decode())["token"] == ["stored_refresh"]


@pytest.mark.parametrize(
    ("link_this_backend", "kept"),
    [(lambda: save_registration(HOST, _registration()), True), (lambda: None, False)],
    ids=["login has a personal proxy", "login has none"],
)
def test_removing_another_backends_custom_proxy_keeps_the_service_only_while_the_login_needs_it(
    cli_runner, service, link_this_backend, kept
):
    service.installed = True
    link_this_backend()

    result = cli_runner.invoke(
        app, ["browser", "proxy", "unlink"], env={"GUMLOOP_BASE_URL": "https://staging.api.gumloop.com"}
    )

    assert result.exit_code == 0, result.output
    assert service.installed is kept


@pytest.mark.parametrize(("status", "payload"), [(503, {"error": "unavailable"}), (404, {"error": "route_not_found"})])
@respx.mock
def test_remove_keeps_the_key_when_gumloop_cannot_delete_the_custom_proxy(cli_runner, service, status, payload):
    save_registration(HOST, _registration())
    key = public_key_text(load_or_create_key(HOST))
    respx.delete(f"{API_BASE}/custom-proxies/dp-1").respond(status, json=payload)

    result = cli_runner.invoke(app, ["browser", "proxy", "unlink"])

    assert result.exit_code == 1
    assert public_key_text(load_or_create_key(HOST)) == key
    assert load_registration(HOST) == _registration()
