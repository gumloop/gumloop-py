from __future__ import annotations

from typing import Annotated

import typer
from pydantic import ValidationError

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.commands.brain import sources_app
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

JsonOutput = Annotated[bool, typer.Option("--json")]


@sources_app.command("connect")
def connect_source(
    ctx: typer.Context,
    args_json: str | None = None,
    args_file: str | None = None,
    args: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Create a connected source draft from JSON. Account setup must already be complete."""
    cli: CliContext = ctx.obj
    try:
        settings = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args, allow_empty=False)
        name = settings.pop("name", None)
        source_type = settings.pop("source_type", None)
        if not isinstance(name, str) or not name.strip() or not isinstance(source_type, str):
            raise GumloopError("Connected source JSON requires name and source_type.")
        if source_type == "direct_file_uploads":
            raise GumloopError("Use brain sources create for file-upload sources.")
        print_json(
            cli.call_with_refresh(lambda client: client.brain.create_source(name, source_type=source_type, **settings))
        )
    except ValidationError:
        exit_with_error(GumloopError("Invalid connected source settings JSON."), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("configuration")
def source_configuration(ctx: typer.Context, source_id: str, json_output: JsonOutput = False) -> None:
    """Read source configuration and credential selectors with management permission."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda client: client.brain.get_source_configuration(source_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("configure")
def configure_source(
    ctx: typer.Context,
    source_id: str,
    args_json: str | None = None,
    args_file: str | None = None,
    args: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Update source settings from a JSON object; server-owned setup fields remain protected."""
    cli: CliContext = ctx.obj
    try:
        settings = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args, allow_empty=False)
        print_json(cli.call_with_refresh(lambda client: client.brain.update_source(source_id, **settings)))
    except ValidationError:
        exit_with_error(GumloopError("Invalid source settings JSON."), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("browse")
def browse_source(
    ctx: typer.Context,
    source_type: str,
    args_json: str | None = None,
    args_file: str | None = None,
    args: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Browse source account nodes using JSON credential selectors and scope settings."""
    cli: CliContext = ctx.obj
    try:
        settings = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args)
        if "source_type" in settings:
            raise GumloopError("Pass source_type as the command argument.")
        print_json(cli.call_with_refresh(lambda client: client.brain.browse_source(source_type, **settings)))
    except ValidationError:
        exit_with_error(GumloopError("Invalid source browse settings JSON."), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("sync")
def sync_source(ctx: typer.Context, source_id: str, json_output: JsonOutput = False) -> None:
    """Request sync, restart a draft estimate, or retry source setup."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda client: client.brain.sync_source(source_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("pause")
def pause_source(ctx: typer.Context, source_id: str, json_output: JsonOutput = False) -> None:
    """Pause a source and stop its pending sync work."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda client: client.brain.pause_source(source_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("resume")
def resume_source(ctx: typer.Context, source_id: str, json_output: JsonOutput = False) -> None:
    """Resume an approved source. Draft sources must be approved first."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda client: client.brain.resume_source(source_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("history")
def source_history(
    ctx: typer.Context,
    source_id: str,
    page_size: Annotated[int | None, typer.Option(min=1, max=100)] = None,
    cursor: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """List paginated sync history and credit estimates."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda client: client.brain.list_sync_runs(source_id, page_size=page_size, cursor=cursor)
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("issues")
def source_issues(
    ctx: typer.Context,
    source_id: str,
    page_size: Annotated[int | None, typer.Option(min=1, max=200)] = None,
    cursor: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """List paginated source issues; hidden document details remain redacted."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda client: client.brain.list_source_issues(source_id, page_size=page_size, cursor=cursor)
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@sources_app.command("children")
def source_children(
    ctx: typer.Context,
    source_id: str,
    parent_id: str | None = None,
    query: str | None = None,
    page_size: Annotated[int | None, typer.Option(min=1, max=1000)] = None,
    cursor: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Browse the source's indexed documents using current source permissions."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda client: client.brain.list_source_children(
                    source_id, parent_id=parent_id, query=query, page_size=page_size, cursor=cursor
                )
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
