from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

import typer
from rich.markup import escape as escape_markup
from rich.table import Table
from rich.text import Text

from gumloop import GumloopError
from gumloop.cli.commands._downloads import download_response
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import Artifact

artifacts_app = typer.Typer(help="List and download Gumloop artifacts.", no_args_is_help=True, rich_markup_mode="rich")


def _render_artifacts(artifacts: Sequence[Artifact]) -> None:
    if not artifacts:
        console.print("No artifacts found.")
        return

    table = Table(title="Gumloop Artifacts")
    table.add_column("ID", overflow="fold")
    table.add_column("Filename", overflow="fold")
    table.add_column("Version", overflow="fold")
    table.add_column("Session", overflow="fold")
    table.add_column("Created")

    # Table cells default to markup=True; Text cells render as plain text.
    for artifact in artifacts:
        table.add_row(
            Text(artifact.id),
            Text(artifact.filename or ""),
            Text(artifact.version_id or ""),
            Text(artifact.session_id or ""),
            Text(artifact.created_at or ""),
        )

    console.print(table)


@artifacts_app.command(
    "list",
    epilog="Example:\n  gumloop artifacts list agent_abc --limit 50 --json",
)
def list_artifacts(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="Agent id whose artifacts should be listed.")],
    session: Annotated[
        str | None,
        typer.Option("--session", help="Filter to a single session id."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of artifacts to return."),
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
    """List artifacts produced by an agent."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.artifacts.list(
                agent_id,
                session_id=session,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    _render_artifacts(response.artifacts)
    if response.next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(response.next_cursor)}")


@artifacts_app.command(
    "download",
    epilog=(
        "Examples:\n"
        "  gumloop artifacts download artifact_abc\n"
        "  gumloop artifacts download artifact_abc -o ./downloads/\n"
        "  gumloop artifacts download artifact_abc -o -"
    ),
)
def download_artifact(
    ctx: typer.Context,
    artifact_id: Annotated[str, typer.Argument(help="Artifact id to download.")],
    output: Annotated[
        str | None,
        typer.Option("-o", "--output", help="File or directory to write to. Use '-' for stdout."),
    ] = None,
    version_id: Annotated[
        str | None,
        typer.Option("--version-id", help="Specific artifact version to download."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the local download metadata as JSON."),
    ] = False,
) -> None:
    """Download an artifact via the SDK's signed download URL."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.artifacts.download(artifact_id, version_id=version_id))
        result = download_response(response, output=output, fallback_name=f"{artifact_id}.bin")
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(result)
        return

    if result["path"] is None:
        return
    # result["path"] embeds the server-supplied filename, which is path-safe
    # but not markup-safe; escape before the markup=True framing print.
    console.print(f"[green]Saved[/green] {escape_markup(result['path'])} ({result['bytes']} bytes)")
