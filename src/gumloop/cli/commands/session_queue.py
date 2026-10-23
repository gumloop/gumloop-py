from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.commands._text_input import resolve_text_input
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import SessionQueueResponse

queue_app = typer.Typer(help="List, add, edit, delete, or send queued session messages.", no_args_is_help=True)
SessionId = Annotated[str, typer.Argument(help="Session id.")]
MessageId = Annotated[str, typer.Argument(help="Queued message id.")]
JsonOutput = Annotated[bool, typer.Option("--json", help="Print the raw response as JSON.")]
Input = Annotated[str | None, typer.Option("--input", help="Message text.")]
InputStdin = Annotated[str | None, typer.Option("--input-stdin", help="Use '-' to read message text from stdin.")]


def _message(input_text: str | None, input_stdin: str | None) -> str:
    text = resolve_text_input(input_text, input_stdin)
    if not text or not text.strip():
        raise GumloopError("Pass --input or --input-stdin with text to queue.")
    return text


def _print_queue(response: SessionQueueResponse, json_output: bool) -> None:
    if json_output:
        print_json(response)
    elif not response.queue:
        console.print("No queued messages.")
    else:
        console.print("ID", "STATE", "POSITION", "INPUT", sep="\t")
        for message in response.queue:
            console.print(
                message.id,
                message.state,
                str(message.position),
                message.input or "",
                sep="\t",
                markup=False,
                highlight=False,
            )


@queue_app.command("list")
def list_queue(ctx: typer.Context, session_id: SessionId, json_output: JsonOutput = False) -> None:
    """Show a session's current message queue."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.sessions.list_queue(session_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    _print_queue(response, json_output)


@queue_app.command("add")
def add_message(
    ctx: typer.Context,
    session_id: SessionId,
    input_text: Input = None,
    input_stdin: InputStdin = None,
    json_output: JsonOutput = False,
) -> None:
    """Queue a message for a later turn."""
    cli: CliContext = ctx.obj
    try:
        message = _message(input_text, input_stdin)
        response = cli.call_with_refresh(lambda client: client.sessions.queue_message(session_id, message))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    _print_queue(response, json_output)


@queue_app.command("edit")
def edit_message(
    ctx: typer.Context,
    session_id: SessionId,
    queued_message_id: MessageId,
    input_text: Input = None,
    input_stdin: InputStdin = None,
    json_output: JsonOutput = False,
) -> None:
    """Replace a queued message's text."""
    cli: CliContext = ctx.obj
    try:
        message = _message(input_text, input_stdin)
        response = cli.call_with_refresh(
            lambda client: client.sessions.edit_queued_message(session_id, queued_message_id, message)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    _print_queue(response, json_output)


@queue_app.command("delete")
def delete_message(
    ctx: typer.Context, session_id: SessionId, queued_message_id: MessageId, json_output: JsonOutput = False
) -> None:
    """Remove a queued message."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.sessions.delete_queued_message(session_id, queued_message_id)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    _print_queue(response, json_output)


@queue_app.command("send")
def send_message(
    ctx: typer.Context, session_id: SessionId, queued_message_id: MessageId, json_output: JsonOutput = False
) -> None:
    """Send a queued message now, interrupting any active run."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.sessions.send_queued_message(session_id, queued_message_id)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json(response)
    else:
        console.print(response.session.id, response.session.state or "", sep="\t", markup=False, highlight=False)
