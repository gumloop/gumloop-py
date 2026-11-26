from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import sys
from datetime import datetime
from datetime import timezone
from typing import Annotated

import httpx
import keyring.errors
import typer
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from rich.markup import escape as escape_markup

from gumloop import APIStatusError
from gumloop import GumloopError
from gumloop._client import DEFAULT_BASE_URL
from gumloop._version import __version__
from gumloop.cli.console import console
from gumloop.cli.console import error_console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import load_credentials
from gumloop.cli.custom_proxy_key import CustomProxyConnectionStatus
from gumloop.cli.custom_proxy_key import CustomProxyRegistration
from gumloop.cli.custom_proxy_key import backend_host
from gumloop.cli.custom_proxy_key import forget
from gumloop.cli.custom_proxy_key import forget_connection_status
from gumloop.cli.custom_proxy_key import forget_registration
from gumloop.cli.custom_proxy_key import load_connection_status
from gumloop.cli.custom_proxy_key import load_key
from gumloop.cli.custom_proxy_key import load_or_create_key
from gumloop.cli.custom_proxy_key import load_registration
from gumloop.cli.custom_proxy_key import save_connection_status
from gumloop.cli.custom_proxy_key import save_registration
from gumloop.cli.custom_proxy_lock import custom_proxy_lock
from gumloop.cli.custom_proxy_lock import is_running
from gumloop.cli.custom_proxy_service import CustomProxyService
from gumloop.cli.custom_proxy_service import NoBackgroundService
from gumloop.cli.custom_proxy_service import gumloop_executable
from gumloop.cli.custom_proxy_service import service_for_current_platform
from gumloop.cli.errors import exit_with_error
from gumloop.linked_proxy.connection import GatewayConnection
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignedOut
from gumloop.linked_proxy.connection import SignInRefused
from gumloop.linked_proxy.connection import UpgradeRequired
from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.sign_in import public_key_text
from gumloop.linked_proxy.tls_check import TlsInspected
from gumloop.linked_proxy.tls_check import check_tls_not_inspected
from gumloop.types import CustomProxyGatewayToken

proxy_app = typer.Typer(
    help="Let your agents' browser go out to the internet through this computer.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

_NAME_MAX_LENGTH = 100
_CREDENTIAL_OVERRIDES = ("GUMLOOP_ACCESS_TOKEN", "GUMLOOP_API_KEY", "GUMLOOP_USER_ID")
_ROLE_DENIED = "Your organization's roles don't allow you to use personal proxies. Ask an admin to turn them on."
# Why this member can't use personal proxies right now, keyed by Gumloop API error code.
_UNAVAILABLE_REASONS = {
    "policy_denied": _ROLE_DENIED,
    "organization_permission_required": _ROLE_DENIED,
    "insufficient_permissions": _ROLE_DENIED,
    "tier_required_enterprise": "Personal proxies need an Enterprise plan.",
    "route_not_found": "Personal proxies aren't available for your organization yet.",
}
# The only refusal that forgets the registration.
_REMOVED = "personal_custom_proxy_not_found"
# Also what the API answers when the rollout flag can't be read, so connect retries it.
_NOT_RELEASED = "route_not_found"
_RETRIED_STATUSES = frozenset({408, 409, 429})
# Gumloop answered 401 to a login that can't be refreshed, such as a revoked API key.
_LOGIN_REJECTED = "login_rejected"


@proxy_app.command(
    "link",
    epilog="Examples:\n  gumloop browser proxy link\n  gumloop browser proxy link --name 'Office desktop'",
)
def link(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Option(
            "--name", help="Name for this computer in Gumloop when it is first linked. Default: its hostname."
        ),
    ] = None,
) -> None:
    """Link this computer and keep it connected in the background, also after a restart."""
    cli: CliContext = ctx.obj
    host = backend_host(cli.effective_base_url)
    try:
        if not _signed_in(host):
            raise GumloopError(f"Run `gumloop login` first. Linking this computer needs a stored login for {host}.")
        # The background service runs as the stored login, so it couldn't connect a computer added as anyone else.
        overrides = [variable for variable in _CREDENTIAL_OVERRIDES if os.environ.get(variable)]
        if overrides:
            raise GumloopError(
                f"Linking this computer can't use {', '.join(overrides)}. "
                "Save the login with `gumloop login`, then retry."
            )
        try:
            service: CustomProxyService | None = service_for_current_platform()
        except NoBackgroundService:
            service = None
        executable = gumloop_executable() if service is not None else None
        check_tls_not_inspected()
        key = load_or_create_key(host)
        registration = load_registration(host)
        if registration is not None and _is_someone_else(registration, _stored_credentials()):
            raise GumloopError(
                "This computer is linked to another Gumloop user. Run `gumloop browser proxy unlink`, then link again."
            )
        _register(cli, host, key, name, registration)
        if service is not None and executable is not None:
            service.install(executable)
    except TlsInspected as error:
        exit_with_error(_tls_inspected_error(error))
    except (GumloopError, ValidationError, httpx.HTTPError) as error:
        exit_with_error(_explained(error))

    if service is None:
        console.print(
            "It can't stay connected in the background: this computer has no systemd user session. "
            "Run `gumloop browser proxy connect` and keep it open, for example in tmux."
        )
        return
    console.print("[green]Connected.[/green] Your agents' browser now goes out through this computer.")
    if sys.platform.startswith("linux"):
        console.print("[dim]It connects when you log in, once your keyring is unlocked.[/dim]")


@proxy_app.command("status")
def status(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Print the status as JSON.")] = False,
) -> None:
    """Show whether this computer is linked and whether it is connected."""
    cli: CliContext = ctx.obj
    host = backend_host(cli.effective_base_url)
    registration = load_registration(host)
    service = _service_or_none()
    service_installed = service is not None and service.is_installed()
    running = registration is not None and is_running(host)
    connection = load_connection_status(host) if running else None
    if registration is None:
        state = None
    elif not running:
        state = "not_running"
    else:
        state = "connected" if connection and connection.connected else "connecting"
    if json_output:
        print_json(
            {
                "backend": host,
                "custom_proxy_id": registration.custom_proxy_id if registration else None,
                "name": registration.name if registration else None,
                "service_installed": service_installed,
                "state": state,
                "since": connection.since.isoformat() if connection else None,
                "last_error": connection.last_error if connection else None,
            }
        )
        return

    if registration is None:
        console.print("This computer is not linked. Run `gumloop browser proxy link`.")
        return
    prefix = f'"{escape_markup(registration.name)}"'
    if not running:
        start = "link" if service is not None else "connect"
        console.print(f"{prefix}: not running. Run `gumloop browser proxy {start}` to start.")
    elif connection and connection.connected:
        console.print(f"{prefix}: connected since {_clock_time(connection.since)}.")
    elif connection and connection.last_error:
        console.print(f"{prefix}: connecting. Last attempt failed: {escape_markup(connection.last_error)}.")
    else:
        console.print(f"{prefix}: connecting.")


@proxy_app.command("unlink")
def unlink(ctx: typer.Context) -> None:
    """Unlink this computer from Gumloop, and delete its key from this computer."""
    cli: CliContext = ctx.obj
    host = backend_host(cli.effective_base_url)
    try:
        removed = remove_custom_proxy(cli, host)
    except (GumloopError, httpx.HTTPError) as error:
        exit_with_error(_explained(error))
    if removed:
        console.print("Unlinked this computer and deleted its key.")
    else:
        console.print("This computer is not linked.")


def remove_custom_proxy(cli: CliContext, host: str) -> bool:
    """Returns whether there was a personal proxy to unlink. When Gumloop can't
    delete it, the key and registration stay so the removal can be retried."""
    login_host = _login_host(_stored_credentials())
    service_still_needed = login_host != host and load_registration(login_host) is not None
    service = None if service_still_needed else _service_or_none()
    registration = load_registration(host)
    service_installed = service is not None and service.is_installed()
    if service is not None and service_installed:
        service.remove()
    if registration is not None:
        _delete_custom_proxy(cli, registration.custom_proxy_id)
    forget(host)
    return service_installed or registration is not None


def remove_stored_login_custom_proxy() -> bool:
    """Unlinks the stored login's personal proxy, whatever overrides the current command has."""
    credentials = _stored_credentials()
    return remove_custom_proxy(CliContext(credentials=credentials), _login_host(credentials))


@proxy_app.command("connect")
def connect(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show more detail while connected."),
    ] = False,
) -> None:
    """Keep this computer connected from this terminal until you stop it with Ctrl-C."""
    # The background service runs this too. A clean exit means the service should stay down.
    cli: CliContext = ctx.obj
    host = backend_host(cli.effective_base_url)
    custom_proxy_id: str | None = None
    try:
        with custom_proxy_lock(host):
            registration = load_registration(host)
            if registration is None:
                error_console.print("This computer is not linked. Run `gumloop browser proxy link`.")
                return
            custom_proxy_id = registration.custom_proxy_id
            # The registration stays, so `link` can replace its personal proxy in Gumloop.
            key = load_key(host)
            if key is None or registration.public_key != public_key_text(key):
                error_console.print(
                    "This computer's personal proxy key is gone from the OS keychain. "
                    "Run `gumloop browser proxy link` to link it again."
                )
                return
            check_tls_not_inspected()
            announced = False

            def on_connected() -> None:
                nonlocal announced
                _record_connection(host, connected=True)
                if not announced:
                    announced = True
                    console.print(
                        "[green]Connected.[/green] Agents can now send browser traffic through this computer. "
                        "Press Ctrl-C to stop."
                    )

            connection = GatewayConnection(
                gateway_url=registration.gateway_url,
                linked_proxy_id=registration.custom_proxy_id,
                key=key,
                signed_in=lambda: _owner_login(host, registration) is not None,
                gateway_token=lambda: _gateway_token(host, registration),
                on_open=_print_destination if verbose else None,
                on_connected=on_connected,
                on_failed=lambda error: _record_connection(host, connected=False, last_error=error),
            )
            _record_connection(host, connected=False)
            try:
                asyncio.run(connection.run())
            finally:
                forget_connection_status(host)
    except TlsInspected as error:
        exit_with_error(_tls_inspected_error(error))
    except SignInRefused as refusal:
        if refusal.reason == _REMOVED:
            # `link` doesn't take the lock, so it may have saved a new registration meanwhile.
            current = load_registration(host)
            if current is not None and current.custom_proxy_id == custom_proxy_id:
                forget_registration(host)
            error_console.print(
                "This computer was unlinked from Gumloop. Run `gumloop browser proxy link` to link it again."
            )
        elif refusal.reason == _LOGIN_REJECTED:
            error_console.print(
                "Gumloop no longer accepts your login, so this computer disconnected. "
                "Run `gumloop login`, then `gumloop browser proxy link`."
            )
        else:
            reason = _UNAVAILABLE_REASONS.get(refusal.reason, "You can't use personal proxies right now.")
            error_console.print(
                f"{reason} This computer disconnected. Run `gumloop browser proxy link` once that changes."
            )
    except SignedOut:
        if _signed_in(host):
            error_console.print(
                "You logged in to Gumloop as someone else, so this computer disconnected. "
                "Log back in as the person who linked it, or run `gumloop browser proxy unlink` and link it again."
            )
        else:
            error_console.print("You logged out of Gumloop, so this computer disconnected.")
    except UpgradeRequired:
        error_console.print(
            "This version of the Gumloop CLI is too old to connect this computer. "
            "Run `gumloop update`, then `gumloop browser proxy link`."
        )
    except KeyboardInterrupt:
        console.print("Stopped.")
    except GumloopError as error:
        exit_with_error(error)


def _signed_in(host: str) -> bool:
    """A stored login for this backend. Logging out, or in to another backend, stops the personal proxy."""
    credentials = _stored_credentials()
    return credentials.has_any and _login_host(credentials) == host


def _stored_credentials() -> Credentials:
    try:
        return load_credentials()
    except keyring.errors.KeyringError as error:
        raise GumloopError(f"Could not read your Gumloop login from the OS keychain: {error}") from error


def _login_host(credentials: Credentials) -> str:
    """The backend the background service serves, whatever overrides the current command has."""
    return backend_host(credentials.base_url or DEFAULT_BASE_URL)


def _owner_login(host: str, registration: CustomProxyRegistration) -> Credentials | None:
    """The stored login, while it is for this backend and not someone other than who linked this computer."""
    credentials = _stored_credentials()
    if not credentials.has_any or _login_host(credentials) != host or _is_someone_else(registration, credentials):
        return None
    return credentials


def _is_someone_else(registration: CustomProxyRegistration, credentials: Credentials) -> bool:
    """Only when both users are known: another user's gateway token request answers personal_custom_proxy_not_found."""
    login_user_id = _login_user_id(credentials)
    return None not in (registration.user_id, login_user_id) and login_user_id != registration.user_id


def _login_user_id(credentials: Credentials) -> str | None:
    """Read from the access token without verifying it, which only tells logins apart."""
    if credentials.auth_method == "api_key":
        return credentials.user_id
    if not credentials.access_token:
        return None
    try:
        payload = credentials.access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    subject = claims.get("sub") if isinstance(claims, dict) else None
    return subject if isinstance(subject, str) else None


def _gateway_token(host: str, registration: CustomProxyRegistration) -> CustomProxyGatewayToken:
    """A refusal stops the personal proxy, except the ones that can pass on their own: a timeout,
    a conflict, rate limiting, and ``route_not_found``."""
    # The service outlives logins, so each request uses the login stored now, not the one it started with.
    credentials = _owner_login(host, registration)
    if credentials is None:
        raise SignedOut()
    try:
        response = CliContext(credentials=credentials).call_with_refresh(
            lambda client: client.custom_proxies.create_gateway_token(registration.custom_proxy_id)
        )
    except APIStatusError as error:
        code = error.code if isinstance(error.code, str) else None
        if error.status_code == 401:
            raise SignInRefused(_LOGIN_REJECTED) from error
        if 400 <= error.status_code < 500 and error.status_code not in _RETRIED_STATUSES and code != _NOT_RELEASED:
            raise SignInRefused(code or f"http_{error.status_code}") from error
        raise GatewayTokenUnavailable(f"Gumloop didn't give a gateway token (HTTP {error.status_code})") from error
    except (GumloopError, httpx.HTTPError) as error:
        raise GatewayTokenUnavailable(f"Gumloop didn't give a gateway token ({error})") from error
    return response


def _register(
    cli: CliContext, host: str, key: Ed25519PrivateKey, name: str | None, previous: CustomProxyRegistration | None
) -> None:
    """Registering this key again gets its personal proxy, or a new one if it was unlinked in Gumloop. A previous
    registration of a key the keychain lost is unusable, so its personal proxy is replaced and its default kept."""
    replaced = previous if previous is not None and previous.public_key != public_key_text(key) else None
    machine_name = socket.gethostname()
    response = cli.call_with_refresh(
        lambda client: client.custom_proxies.register_cli(
            name=name or machine_name[:_NAME_MAX_LENGTH],
            public_key=public_key_text(key),
            machine_name=machine_name,
            cli_version=__version__,
        )
    )
    registration = CustomProxyRegistration(
        custom_proxy_id=response.custom_proxy.id,
        name=response.custom_proxy.name,
        gateway_url=response.gateway_url,
        public_key=public_key_text(key),
        user_id=_login_user_id(_stored_credentials()),
    )
    save_registration(host, registration)
    # Deleted only now, so a failed registration leaves the lost key's personal proxy and its default in place.
    keep_default = replaced is not None and _delete_lost_custom_proxy(cli, replaced.custom_proxy_id)
    if keep_default and not response.custom_proxy.is_default:
        cli.call_with_refresh(lambda client: client.custom_proxies.set_default(registration.custom_proxy_id))
    added_name = escape_markup(response.custom_proxy.name)
    console.print(f"Linked this computer to Gumloop as '{added_name}'.")


def _delete_lost_custom_proxy(cli: CliContext, custom_proxy_id: str) -> bool:
    """Returns whether it was the default."""
    listed = cli.call_with_refresh(lambda client: client.custom_proxies.list())
    lost = next((custom_proxy for custom_proxy in listed.custom_proxies if custom_proxy.id == custom_proxy_id), None)
    if lost is None:
        return False
    _delete_custom_proxy(cli, custom_proxy_id)
    return lost.is_default


def _delete_custom_proxy(cli: CliContext, custom_proxy_id: str) -> None:
    """One Gumloop no longer has counts as deleted."""
    try:
        cli.call_with_refresh(lambda client: client.custom_proxies.delete(custom_proxy_id))
    except APIStatusError as error:
        if error.code != _REMOVED:
            raise


def _service_or_none() -> CustomProxyService | None:
    try:
        return service_for_current_platform()
    except GumloopError:
        return None


def _explained(error: Exception) -> Exception:
    """Personal proxies being off for this member, in words. Any other error stays as it is."""
    if isinstance(error, APIStatusError) and error.code in _UNAVAILABLE_REASONS:
        return GumloopError(_UNAVAILABLE_REASONS[error.code])
    return error


def _tls_inspected_error(error: TlsInspected) -> GumloopError:
    return GumloopError(
        f"This network inspects TLS traffic ({error}), so sites would show your agents' browser "
        "certificate errors. Use this computer on a network without TLS inspection."
    )


def _record_connection(host: str, *, connected: bool, last_error: str | None = None) -> None:
    save_connection_status(
        host,
        CustomProxyConnectionStatus(connected=connected, since=datetime.now(timezone.utc), last_error=last_error),
    )


def _clock_time(moment: datetime) -> str:
    local = moment.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%-I:%M %p")
    return local.strftime("%b %-d, %-I:%M %p")


def _print_destination(target: Target) -> None:
    opened = datetime.now().astimezone().strftime("%b %-d, %-I:%M:%S %p")
    console.print(f"[dim]{opened}  {escape_markup(target.host)}[/dim]", highlight=False)
