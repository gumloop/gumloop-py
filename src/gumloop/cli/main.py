from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from gumloop import __version__
from gumloop.cli.commands.agents import agents_app
from gumloop.cli.commands.artifacts import artifacts_app
from gumloop.cli.commands.auth import login as login_command
from gumloop.cli.commands.auth import logout as logout_command
from gumloop.cli.commands.brain import brain_app
from gumloop.cli.commands.chat import chat_app
from gumloop.cli.commands.mcp import mcp_app
from gumloop.cli.commands.sessions import sessions_app
from gumloop.cli.commands.skills import skills_app
from gumloop.cli.commands.sync import sync_app
from gumloop.cli.commands.update import maybe_notify_update
from gumloop.cli.commands.update import update as update_command
from gumloop.cli.context import CliContext
from gumloop.cli.credentials import load_credentials

app = typer.Typer(
    help="Gumloop command line tools.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            envvar="GUMLOOP_BASE_URL",
            help="Override the Gumloop API base URL for this invocation.",
        ),
    ] = None,
    team_id: Annotated[
        str | None,
        typer.Option(
            "--team-id",
            envvar="GUMLOOP_TEAM_ID",
            help="Workspace/team id to scope commands to.",
        ),
    ] = None,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Print the Gumloop CLI version and exit.",
        ),
    ] = False,
) -> None:
    """Gumloop CLI."""
    credentials = load_credentials()

    # Env-supplied auth wins outright over stored creds; the unused
    # fields are blanked so we never send mixed OAuth + API-key headers.
    env_access = os.environ.get("GUMLOOP_ACCESS_TOKEN")
    env_api_key = os.environ.get("GUMLOOP_API_KEY")
    env_user_id = os.environ.get("GUMLOOP_USER_ID")
    if env_access:
        credentials.access_token = env_access
        credentials.api_key = None
        credentials.refresh_token = None
    elif env_api_key:
        credentials.api_key = env_api_key
        credentials.access_token = None
        credentials.refresh_token = None

    ctx.obj = CliContext(
        credentials=credentials,
        base_url_override=base_url,
        team_id_override=team_id,
        user_id_override=env_user_id,
    )


app.command("login", epilog="Examples:\n  gumloop login\n  gumloop login --api-key gum_xxx --user-id user_abc")(
    login_command
)
app.command("logout")(logout_command)
app.command("update")(update_command)
app.add_typer(mcp_app, name="mcp")
app.add_typer(agents_app, name="agents")
app.add_typer(sessions_app, name="sessions")
app.add_typer(skills_app, name="skills")
app.add_typer(artifacts_app, name="artifacts")
app.add_typer(chat_app, name="chat")
app.add_typer(brain_app, name="brain")
app.add_typer(sync_app, name="sync")


def _require_supported_platform() -> None:
    """Refuse to run on Windows; keychain + OAuth callback paths are
    POSIX-only and untested there. The SDK itself still works on Windows."""
    if sys.platform.startswith("win") or sys.platform == "cygwin":
        sys.stderr.write(
            "Error: the Gumloop CLI is not supported on Windows.\n"
            "Please use macOS, Linux, or WSL (Windows Subsystem for Linux).\n"
            "\n"
            "The Gumloop Python SDK itself works on Windows - import it directly:\n"
            "    from gumloop import Gumloop\n"
        )
        sys.exit(1)


def main() -> None:
    _require_supported_platform()
    if sys.argv[1:2] != ["update"]:
        maybe_notify_update()
    app()


if __name__ == "__main__":
    main()
