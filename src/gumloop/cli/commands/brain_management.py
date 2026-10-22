from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.commands.brain import sources_app
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

JsonOutput = Annotated[bool, typer.Option("--json")]


@sources_app.command("sync")
def sync_source(ctx: typer.Context, source_id: str, json_output: JsonOutput = False) -> None:
    """Request sync for an existing ready, active connected source."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda client: client.brain.sync_source(source_id)))
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
