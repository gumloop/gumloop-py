from __future__ import annotations

import asyncio
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
from gumloop.cli.errors import exit_with_error
from gumloop.cli.linked_proxy_key import LinkedProxyConnectionStatus
from gumloop.cli.linked_proxy_key import LinkedProxyRegistration
from gumloop.cli.linked_proxy_key import backend_host
from gumloop.cli.linked_proxy_key import forget
from gumloop.cli.linked_proxy_key import forget_connection_status
from gumloop.cli.linked_proxy_key import forget_registration
from gumloop.cli.linked_proxy_key import load_connection_status
from gumloop.cli.linked_proxy_key import load_or_create_key
from gumloop.cli.linked_proxy_key import load_registration
from gumloop.cli.linked_proxy_key import save_connection_status
from gumloop.cli.linked_proxy_key import save_registration
from gumloop.cli.linked_proxy_lock import is_running
from gumloop.cli.linked_proxy_lock import linked_proxy_lock
from gumloop.cli.linked_proxy_service import LinkedProxyService
from gumloop.cli.linked_proxy_service import NoBackgroundService
from gumloop.cli.linked_proxy_service import gumloop_executable
from gumloop.cli.linked_proxy_service import service_for_current_platform
from gumloop.linked_proxy.connection import SIGN_IN_REFUSED
from gumloop.linked_proxy.connection import GatewayConnection
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignedOut
from gumloop.linked_proxy.connection import SignInRefused
from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.sign_in import public_key_text
from gumloop.linked_proxy.tls_check import TlsInspected
from gumloop.linked_proxy.tls_check import check_tls_not_inspected

proxy_app = typer.Typer(
    help="Let your agents' browser go out to the internet through this computer.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

_NAME_MAX_LENGTH = 100
_CREDENTIAL_OVERRIDES = ("GUMLOOP_ACCESS_TOKEN", "GUMLOOP_API_KEY", "GUMLOOP_USER_ID")
_ROLE_DENIED = "Your organization's roles don't allow you to use personal proxies. Ask an admin to turn them on."
_PLAN_REQUIRED = "Personal proxies need an Enterprise plan."
_NOT_RELEASED = "Personal proxies aren't available for your organization yet."
# Why this member can't use personal proxies right now, keyed by Gumloop API error code or gateway close reason.
_UNAVAILABLE_REASONS = {
    "policy_denied": _ROLE_DENIED,
    "permission_denied": _ROLE_DENIED,
    "tier_required_enterprise": _PLAN_REQUIRED,
    "not_enterprise": _PLAN_REQUIRED,
    "route_not_found": _NOT_RELEASED,
    "not_released": _NOT_RELEASED,
    "not_a_member": "Personal proxies need you to be in a Gumloop organization.",
}
# Refusals that mean the linked proxy no longer exists. Any other refusal keeps the registration.
_REMOVED_REASONS = frozenset({"not_found", "linked_proxy_not_found", SIGN_IN_REFUSED})


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
            service: LinkedProxyService | None = service_for_current_platform()
        except NoBackgroundService:
            service = None
        executable = gumloop_executable() if service is not None else None
        check_tls_not_inspected()
        key = load_or_create_key(host)
        if load_registration(host) is None:
            _register(cli, host, key, name)
        if service is not None and executable is not None:
            service.install(executable)
    except TlsInspected as error:
        exit_with_error(_tls_inspected_error(error))
    except (GumloopError, ValidationError) as error:
        exit_with_error(_explained(error))

    if service is None:
        console.print(
            "It can't stay connected in the background: this computer has no systemd user session. "
            "Run `gumloop browser proxy connect` and keep it open, for example in tmux."
        )
        return
    console.print("Connected. Your agents' browser now goes out through this computer.")
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
                "linked_proxy_id": registration.linked_proxy_id if registration else None,
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
        removed = remove_linked_proxy(cli, host)
    except (GumloopError, httpx.HTTPError) as error:
        exit_with_error(_explained(error))
    if removed:
        console.print("Unlinked this computer and deleted its key.")
    else:
        console.print("This computer is not linked.")


def remove_linked_proxy(cli: CliContext, host: str) -> bool:
    """Returns whether there was a linked proxy to unlink. When Gumloop can't
    delete it, the key and registration stay so the removal can be retried."""
    login_host = _login_host(_stored_credentials())
    service_still_needed = login_host != host and load_registration(login_host) is not None
    service = None if service_still_needed else _service_or_none()
    registration = load_registration(host)
    service_installed = service is not None and service.is_installed()
    if service is not None and service_installed:
        service.remove()
    if registration is not None:
        linked_proxy_id = registration.linked_proxy_id
        try:
            cli.call_with_refresh(lambda client: client.linked_proxies.delete(linked_proxy_id))
        except APIStatusError as error:
            if error.status_code != 404:
                raise
    forget(host)
    return service_installed or registration is not None


@proxy_app.command("connect")
def connect(ctx: typer.Context) -> None:
    """Keep this computer connected from this terminal until you stop it with Ctrl-C."""
    # The background service runs this too. A clean exit means the service should stay down.
    cli: CliContext = ctx.obj
    host = backend_host(cli.effective_base_url)
    try:
        with linked_proxy_lock(host):
            registration = load_registration(host)
            if registration is None:
                error_console.print("This computer is not linked. Run `gumloop browser proxy link`.")
                return
            check_tls_not_inspected()
            linked_proxy_id = registration.linked_proxy_id
            connection = GatewayConnection(
                gateway_url=registration.gateway_url,
                linked_proxy_id=linked_proxy_id,
                key=load_or_create_key(host),
                signed_in=lambda: _signed_in(host),
                gateway_token=lambda: _gateway_token(host, linked_proxy_id),
                on_open=_print_destination,
                on_connected=lambda: _record_connection(host, connected=True),
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
        if refusal.reason in _REMOVED_REASONS:
            forget_registration(host)
            error_console.print(
                "This computer was unlinked from Gumloop. Run `gumloop browser proxy link` to link it again."
            )
        else:
            reason = _UNAVAILABLE_REASONS.get(refusal.reason, "You can't use personal proxies right now.")
            error_console.print(
                f"{reason} This computer disconnected. Run `gumloop browser proxy link` once that changes."
            )
    except SignedOut:
        error_console.print("You logged out of Gumloop, so this computer disconnected.")
    except KeyboardInterrupt:
        console.print("Stopped.")
    except GumloopError as error:
        exit_with_error(error)


def _signed_in(host: str) -> bool:
    """A stored login for this backend. Logging out, or in to another backend, stops the linked proxy."""
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


def _gateway_token(host: str, linked_proxy_id: str) -> str:
    """A 403 or 404 means the linked proxy was unlinked or its owner can't use it anymore."""
    # The service outlives logins, so each request uses the login stored now, not the one it started with.
    credentials = _stored_credentials()
    if not credentials.has_any or _login_host(credentials) != host:
        raise SignedOut()
    try:
        response = CliContext(credentials=credentials).call_with_refresh(
            lambda client: client.linked_proxies.create_gateway_token(linked_proxy_id)
        )
    except APIStatusError as error:
        if error.status_code in (403, 404):
            raise SignInRefused(error.code if isinstance(error.code, str) else str(error)) from error
        raise GatewayTokenUnavailable(f"Gumloop didn't give a gateway token (HTTP {error.status_code})") from error
    except (GumloopError, httpx.HTTPError) as error:
        raise GatewayTokenUnavailable(f"Gumloop didn't give a gateway token ({error})") from error
    return response.gateway_token


def _register(cli: CliContext, host: str, key: Ed25519PrivateKey, name: str | None) -> LinkedProxyRegistration:
    machine_name = socket.gethostname()
    response = cli.call_with_refresh(
        lambda client: client.linked_proxies.register_cli(
            name=name or machine_name[:_NAME_MAX_LENGTH],
            public_key=public_key_text(key),
            machine_name=machine_name,
            cli_version=__version__,
        )
    )
    registration = LinkedProxyRegistration(
        linked_proxy_id=response.linked_proxy.id,
        name=response.linked_proxy.name,
        gateway_url=response.gateway_url,
    )
    save_registration(host, registration)
    added_name = escape_markup(response.linked_proxy.name)
    console.print(f"Linked this computer to Gumloop as '{added_name}'.")
    return registration


def _service_or_none() -> LinkedProxyService | None:
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
        LinkedProxyConnectionStatus(connected=connected, since=datetime.now(timezone.utc), last_error=last_error),
    )


def _clock_time(moment: datetime) -> str:
    local = moment.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%-I:%M %p")
    return local.strftime("%b %-d, %-I:%M %p")


def _print_destination(target: Target) -> None:
    console.print(f"[dim]{escape_markup(target.host)}:{target.port}[/dim]")
