from __future__ import annotations

import sys
from typing import Annotated

import click
import questionary
import typer
from rich.prompt import Prompt

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import clear_credentials
from gumloop.cli.credentials import keyring_backend_name
from gumloop.cli.credentials import save_credentials
from gumloop.cli.errors import exit_with_error
from gumloop.cli.oauth import DEFAULT_REDIRECT_PORT
from gumloop.cli.oauth import perform_oauth_login
from gumloop.cli.oauth import revoke_oauth_token

METHOD_OAUTH = "oauth"
METHOD_API_KEY = "api_key"

# Sentinel for `--api-key -` / `--access-token -`: read secret from stdin
# instead of argv (keeps it out of shell history and /proc/<pid>/cmdline).
_STDIN_SENTINEL = "-"


def _read_secret(value: str, *, label: str) -> str:
    if value != _STDIN_SENTINEL:
        return value
    if sys.stdin.isatty():
        raise GumloopError(
            f"--{label} - was passed but stdin is a TTY. Pipe the secret in, e.g. "
            f"`echo $SECRET | gumloop login --{label} -`."
        )
    data = sys.stdin.read().strip()
    if not data:
        raise GumloopError(f"--{label} - was passed but stdin was empty.")
    return data


def _prompt_method() -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise GumloopError(
            "Cannot prompt for a login method in a non-interactive session. "
            "Pass --method oauth or --method api-key (or use --api-key / --access-token directly)."
        )
    choice = questionary.select(
        "Sign in to Gumloop",
        choices=[
            questionary.Choice(title="OAuth (browser)", value=METHOD_OAUTH),
            questionary.Choice(title="API key", value=METHOD_API_KEY),
        ],
        default=METHOD_OAUTH,
        pointer="❯",
        instruction=" ",
        qmark="?",
    ).ask()
    if choice is None:
        raise typer.Exit(130)
    return choice


def _validate(client: Gumloop) -> None:
    client.models.list()


def login(
    ctx: typer.Context,
    method: Annotated[
        str | None,
        typer.Option(
            "--method",
            help="Auth method to use without prompting.",
            click_type=click.Choice(["oauth", "api-key", "api_key"]),
        ),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="Save an existing API key. Use '-' to read from stdin.",
        ),
    ] = None,
    user_id: Annotated[
        str | None,
        typer.Option("--user-id", help="Gumloop user id that owns the API key. Required for --api-key."),
    ] = None,
    access_token: Annotated[
        str | None,
        typer.Option(
            "--access-token",
            help="Save an existing OAuth access token. Use '-' to read from stdin.",
        ),
    ] = None,
    callback_port: Annotated[
        int,
        typer.Option("--callback-port", help="Localhost port for the OAuth callback server."),
    ] = DEFAULT_REDIRECT_PORT,
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", help="Print the OAuth URL instead of opening a browser."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the result as JSON."),
    ] = False,
) -> None:
    """Sign in to Gumloop."""
    cli: CliContext = ctx.obj
    effective_url = cli.effective_base_url

    try:
        if api_key is not None:
            resolved_method = METHOD_API_KEY
        elif access_token is not None:
            resolved_method = METHOD_OAUTH
        elif method:
            resolved_method = METHOD_API_KEY if method in ("api-key", "api_key") else METHOD_OAUTH
        else:
            resolved_method = _prompt_method()
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    try:
        if resolved_method == METHOD_API_KEY:
            if api_key is not None:
                key = _read_secret(api_key, label="api-key")
            else:
                key = Prompt.ask("Gumloop API key", password=True)
            if not key:
                exit_with_error(GumloopError("API key cannot be empty."), json_output=json_output)
            resolved_user_id = user_id or Prompt.ask("Gumloop user id")
            if not resolved_user_id:
                exit_with_error(GumloopError("User id cannot be empty."), json_output=json_output)
            _validate(Gumloop(api_key=key, user_id=resolved_user_id, base_url=effective_url))
            new_creds = Credentials(
                api_key=key,
                user_id=resolved_user_id,
                base_url=effective_url,
            )
        else:
            if access_token is not None:
                resolved_access = _read_secret(access_token, label="access-token")
                tokens: dict[str, str | None] = {"access_token": resolved_access}
            else:

                def _on_url(url: str) -> None:
                    if no_browser:
                        console.print(url)
                    else:
                        console.print("Opening browser for Gumloop OAuth login...")

                raw_tokens = perform_oauth_login(
                    base_url=effective_url,
                    port=callback_port,
                    open_browser=not no_browser,
                    on_url=_on_url,
                )
                tokens = dict(raw_tokens)
            access = tokens.get("access_token")
            if not isinstance(access, str) or not access:
                exit_with_error(
                    GumloopError("OAuth response did not include an access_token."),
                    json_output=json_output,
                )
            _validate(Gumloop(access_token=access, base_url=effective_url))
            refresh = tokens.get("refresh_token")
            new_creds = Credentials(
                access_token=access,
                refresh_token=refresh if isinstance(refresh, str) else None,
                base_url=effective_url,
            )
    except (GumloopError, RuntimeError, OSError) as error:
        exit_with_error(error, json_output=json_output)

    try:
        save_credentials(new_creds)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    cli.credentials = new_creds

    payload = {
        "status": "ok",
        "auth_method": new_creds.auth_method,
        "base_url": effective_url,
    }
    if json_output:
        print_json(payload)
        return
    console.print(f"[green]Logged in[/green] via {new_creds.auth_method} ([dim]{keyring_backend_name()}[/dim]).")


def logout(
    ctx: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the result as JSON."),
    ] = False,
) -> None:
    """Clear stored Gumloop credentials."""
    cli: CliContext = ctx.obj

    # Server-side revoke first so the refresh token can't outlive the
    # local logout. Revoke failures never block the local clear.
    oauth_revoked = False
    revoke_failed = False
    if cli.effective_auth_method == METHOD_OAUTH:
        token = cli.credentials.refresh_token or cli.credentials.access_token
        if token:
            try:
                revoke_oauth_token(base_url=cli.effective_base_url, token=token)
                oauth_revoked = True
            except Exception:
                revoke_failed = True

    clear_credentials()

    payload: dict[str, object] = {"status": "ok", "oauth_revoked": oauth_revoked}
    if revoke_failed:
        payload["oauth_revoke_failed"] = True

    if json_output:
        print_json(payload)
        return

    console.print("[green]Logged out.[/green]")
    if revoke_failed:
        console.print(
            "[yellow]Note:[/yellow] could not reach the server to revoke the refresh token; "
            "it will remain valid until it expires."
        )
