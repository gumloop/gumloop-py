from __future__ import annotations

import sys
from typing import Annotated
from typing import cast

import typer
from rich.markup import escape as escape_markup

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import SessionResponse

sessions_app = typer.Typer(
    help="Create, inspect, and continue Gumloop agent sessions.", no_args_is_help=True, rich_markup_mode="rich"
)


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
        # Resolve --input vs --input-stdin (at most one; '-' reads from stdin).
        if input_text is not None and input_stdin is not None:
            raise GumloopError("Pass at most one of --input or --input-stdin.")
        if input_stdin is not None and input_stdin != "-":
            raise GumloopError("--input-stdin only accepts '-' (reads from stdin).")
        message = sys.stdin.read() if input_stdin == "-" else input_text

        # cast narrows SessionResponse | Iterator to the non-streaming branch
        # (we never pass stream=True).
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

    # Header line uses markup=True; escape the server-supplied id.
    # Data rows use markup=False. Table cells default to markup=True so
    # message bodies go through rich.text.Text.
    session = response.session
    console.print(f"[bold]Session {escape_markup(session.id)}[/bold]", markup=True, highlight=False)
    for field in ("agent_id", "agent_name", "state", "created_at"):
        value = getattr(session, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)
    if session.messages:
        console.print(f"  messages: {len(session.messages)}")
        for m in session.messages[-5:]:
            content = m.content if isinstance(m.content, str) else str(m.content or "")
            console.print(f"  [{m.role or ''}] {content[:200]}", markup=False, highlight=False)


@sessions_app.command(
    "list",
    epilog=(
        "Examples:\n"
        "  gumloop sessions list agent_abc --state completed --limit 50 --json\n"
        "  gumloop sessions list agent_abc --search 'invoice' --sort oldest\n"
        "  gumloop sessions list agent_abc --type api --creator user_123"
    ),
)
def list_sessions(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="Agent id whose sessions should be listed.")],
    search: Annotated[
        str | None,
        typer.Option("--search", help="Search session name and content."),
    ] = None,
    state: Annotated[
        str | None,
        typer.Option("--state", help="Filter by state (e.g. completed, failed, processing, idle)."),
    ] = None,
    type_filter: Annotated[
        str | None,
        typer.Option("--type", help="Filter by session type (e.g. api, chat, slack)."),
    ] = None,
    creator: Annotated[
        str | None,
        typer.Option("--creator", help="Filter by creator user id."),
    ] = None,
    trigger_id: Annotated[
        str | None,
        typer.Option("--trigger-id", help="Filter by originating trigger id."),
    ] = None,
    sort_order: Annotated[
        str | None,
        typer.Option("--sort", help="Sort order (e.g. newest, oldest, credits_desc, name_asc)."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of sessions to return."),
    ] = None,
    cursor: Annotated[
        str | None,
        typer.Option("--cursor", help="Pagination cursor from a previous list call."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """List an agent's sessions with search, filters, and sort."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.sessions.list(
                agent_id,
                search=search,
                state=state,
                type=type_filter,
                creator_user_id=creator,
                trigger_id=trigger_id,
                sort_order=sort_order,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.sessions:
        console.print("No sessions found.")
    else:
        console.print("ID", "STATE", "TYPE", "NAME", "CREATED", sep="\t", soft_wrap=True)
        for session in response.sessions:
            console.print(
                session.id,
                session.state or "",
                session.type or "",
                session.name or "",
                session.created_at or "",
                sep="\t",
                soft_wrap=True,
                markup=False,
                highlight=False,
            )

    if response.next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(response.next_cursor)}")


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

    session = response.session
    console.print(f"[bold]Session {escape_markup(session.id)}[/bold]", markup=True, highlight=False)
    for field in ("agent_id", "agent_name", "state", "created_at"):
        value = getattr(session, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)
    if session.messages:
        console.print(f"  messages: {len(session.messages)}")
        for m in session.messages[-5:]:
            content = m.content if isinstance(m.content, str) else str(m.content or "")
            console.print(f"  [{m.role or ''}] {content[:200]}", markup=False, highlight=False)


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
        if input_text is not None and input_stdin is not None:
            raise GumloopError("Pass at most one of --input or --input-stdin.")
        if input_stdin is not None and input_stdin != "-":
            raise GumloopError("--input-stdin only accepts '-' (reads from stdin).")
        message = sys.stdin.read() if input_stdin == "-" else input_text
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

    session = response.session
    if not session:
        console.print("[green]Message sent.[/green]")
        return

    console.print(f"[bold]Session {escape_markup(session.id)}[/bold]", markup=True, highlight=False)
    for field in ("agent_id", "agent_name", "state", "created_at"):
        value = getattr(session, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)
    if session.messages:
        console.print(f"  messages: {len(session.messages)}")
        for m in session.messages[-5:]:
            content = m.content if isinstance(m.content, str) else str(m.content or "")
            console.print(f"  [{m.role or ''}] {content[:200]}", markup=False, highlight=False)


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
