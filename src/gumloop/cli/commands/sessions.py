from __future__ import annotations

import sys
from typing import Annotated
from typing import cast

import typer
from rich.markup import escape as escape_markup
from rich.table import Table
from rich.text import Text

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import Session
from gumloop.types import SessionResponse

sessions_app = typer.Typer(
    help="Create, inspect, and continue Gumloop agent sessions.", no_args_is_help=True, rich_markup_mode="rich"
)


def _render_session(session: Session) -> None:
    # Header uses markup=True framing -> escape the server-supplied id.
    # Data rows use markup=False. Table cells default to markup=True so
    # message bodies go through rich.text.Text.
    console.print(f"[bold]Session {escape_markup(session.id)}[/bold]", markup=True, highlight=False)
    for field in ("agent_id", "agent_name", "state", "created_at"):
        value = getattr(session, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)
    if session.messages:
        console.print(f"  messages: {len(session.messages)}")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Role")
        table.add_column("Content", overflow="fold")
        for m in session.messages[-5:]:
            content = m.content if isinstance(m.content, str) else str(m.content or "")
            table.add_row(Text(m.role or ""), Text(content[:200]))
        console.print(table)


def _resolve_input(inline: str | None, stdin_marker: str | None) -> str | None:
    """Mirror the args-input pattern: inline or '-' for stdin, never both."""
    if inline is not None and stdin_marker is not None:
        raise GumloopError("Pass at most one of --input or --input-stdin.")
    if stdin_marker is not None:
        if stdin_marker != "-":
            raise GumloopError("--input-stdin only accepts '-' (reads from stdin).")
        return sys.stdin.read()
    return inline


@sessions_app.command(
    "create",
    epilog=(
        "Examples:\n"
        "  gumloop sessions create agent_abc --input 'Hello!'\n"
        "  echo 'Hi from a file' | gumloop sessions create agent_abc --input-stdin -"
    ),
)
def create_session(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="Agent id to start a session with.")],
    input_text: Annotated[
        str | None,
        typer.Option("--input", help="Initial user message."),
    ] = None,
    input_stdin: Annotated[
        str | None,
        typer.Option("--input-stdin", help="Use '-' to read the initial message from stdin.", metavar="-"),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Optional client-side id for the new session."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Start a new agent session, optionally with an initial message."""
    cli: CliContext = ctx.obj

    try:
        message = _resolve_input(input_text, input_stdin)
        # Cast narrows the SessionResponse | Iterator union to the
        # non-streaming branch (we never pass stream=True).
        response = cast(
            SessionResponse,
            cli.call_with_refresh(
                lambda client: client.sessions.create(
                    agent_id,
                    input=message,
                    session_id=session_id,
                )
            ),
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    _render_session(response.session)


@sessions_app.command("get", epilog="Example:\n  gumloop sessions get session_abc --json")
def get_session(
    ctx: typer.Context,
    session_id: Annotated[str, typer.Argument(help="Session id to retrieve.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Show one session's state and recent messages."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.sessions.retrieve(session_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    _render_session(response.session)


@sessions_app.command(
    "send",
    epilog=(
        "Examples:\n"
        "  gumloop sessions send session_abc --input 'follow-up question'\n"
        "  cat next-turn.txt | gumloop sessions send session_abc --input-stdin -"
    ),
)
def send_session(
    ctx: typer.Context,
    session_id: Annotated[str, typer.Argument(help="Session id to send a message to.")],
    input_text: Annotated[
        str | None,
        typer.Option("--input", help="Message text to send."),
    ] = None,
    input_stdin: Annotated[
        str | None,
        typer.Option("--input-stdin", help="Use '-' to read the message from stdin.", metavar="-"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Send a follow-up message to an existing session."""
    cli: CliContext = ctx.obj

    try:
        message = _resolve_input(input_text, input_stdin)
        if not message:
            raise GumloopError("Pass --input or --input-stdin with text to send.")
        response = cast(
            SessionResponse,
            cli.call_with_refresh(lambda client: client.sessions.send(session_id, input=message)),
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if response.session:
        _render_session(response.session)
    else:
        console.print("[green]Message sent.[/green]")


@sessions_app.command("cancel", epilog="Example:\n  gumloop sessions cancel session_abc")
def cancel_session(
    ctx: typer.Context,
    session_id: Annotated[str, typer.Argument(help="Session id to cancel.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Cancel an in-flight session."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.sessions.cancel(session_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Cancelled[/green] session {session_id}")
