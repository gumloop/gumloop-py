from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

brain_app = typer.Typer(help="Search your Company Brain.", no_args_is_help=True, rich_markup_mode="rich")


@brain_app.command(
    "search",
    epilog=(
        "Examples:\n"
        '  gumloop brain search "onboarding process"\n'
        '  gumloop brain search "pricing" --limit 5 --source notion --json'
    ),
)
def search_brain(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query.")],
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of results to return (1-50)."),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="Filter by source type (repeatable), e.g. notion, google_drive, slack."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Search indexed Company Brain sources."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.brain.search(query, limit=limit, source_type=source or None)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.results:
        console.print("No results found.")
        return

    console.print("SCORE", "SOURCE", "TITLE", "URL", sep="\t", soft_wrap=True)
    for result in response.results:
        console.print(
            "" if result.score is None else f"{result.score:.3f}",
            result.source or "",
            result.title or "",
            result.url or "",
            sep="\t",
            soft_wrap=True,
        )
