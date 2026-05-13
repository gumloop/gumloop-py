from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Annotated
from typing import Any

import typer
from rich.table import Table

from gumloop import GumloopError
from gumloop.cli.commands._downloads import download_response
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

artifacts_app = typer.Typer(help="List and download Gumloop artifacts.", no_args_is_help=True, rich_markup_mode="rich")


def _render_artifacts(artifacts: Sequence[Mapping[str, Any]]) -> None:
    if not artifacts:
        console.print("No artifacts found.")
        return

    table = Table(title="Gumloop Artifacts")
    table.add_column("ID", overflow="fold")
    table.add_column("Filename", overflow="fold")
    table.add_column("Version", overflow="fold")
    table.add_column("Session", overflow="fold")
    table.add_column("Created")

    for artifact in artifacts:
        table.add_row(
            str(artifact.get("id") or ""),
            str(artifact.get("filename") or ""),
            str(artifact.get("version_id") or ""),
            str(artifact.get("session_id") or ""),
            str(artifact.get("created_at") or ""),
        )

    console.print(table)


@artifacts_app.command(
    "list",
    epilog="Example:\n  gumloop artifacts list agent_abc --limit 50 --json",
)
def list_artifacts(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="Agent id whose artifacts should be listed.")],
    interaction: Annotated[
        str | None,
        typer.Option("--interaction", help="Filter to a single agent interaction id."),
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
                interaction_id=interaction,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    _render_artifacts(response.get("artifacts", []))
    next_cursor = response.get("next_cursor")
    if next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {next_cursor}")


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
    console.print(f"[green]Saved[/green] {result['path']} ({result['bytes']} bytes)")
