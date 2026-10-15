from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Annotated

import typer
from rich.markup import escape as escape_markup

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.cli.commands._downloads import download_response
from gumloop.cli.commands._item_access import apply_item_access
from gumloop.cli.commands._item_access import json_option
from gumloop.cli.commands._item_access import link_option
from gumloop.cli.commands._item_access import link_role_option
from gumloop.cli.commands._item_access import organization_option
from gumloop.cli.commands._item_access import read_password_stdin
from gumloop.cli.commands._item_access import remove_option
from gumloop.cli.commands._item_access import remove_team_option
from gumloop.cli.commands._item_access import share_option
from gumloop.cli.commands._item_access import share_team_option
from gumloop.cli.commands._item_access import show_item_access
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import ArtifactPasswordResponse

artifacts_app = typer.Typer(
    help="List, download, and share Gumloop artifacts.", no_args_is_help=True, rich_markup_mode="rich"
)


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

    if not response.artifacts:
        console.print("No artifacts found.")
    else:
        console.print("ID", "FILENAME", "VERSION", "SESSION", "CREATED", sep="\t", soft_wrap=True)
        for artifact in response.artifacts:
            console.print(
                artifact.id,
                artifact.filename or "",
                artifact.version_id or "",
                artifact.session_id or "",
                artifact.created_at or "",
                sep="\t",
                soft_wrap=True,
            )

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
    console.print(f"[green]Saved[/green] {result['path']} ({result['bytes']} bytes)")


@artifacts_app.command("access", epilog="Example:\n  gumloop artifacts access artifact_abc --json")
def artifact_access(
    ctx: typer.Context,
    artifact_id: Annotated[str, typer.Argument(help="Artifact id.")],
    json_output: Annotated[bool, json_option()] = False,
) -> None:
    """Show who can access an artifact."""
    show_item_access(
        ctx,
        json_output=json_output,
        read=lambda client: client.artifacts.get_access(artifact_id),
    )


@artifacts_app.command(
    "set-access",
    epilog=(
        "Examples:\n"
        "  gumloop artifacts set-access artifact_abc --share ada@example.com:viewer\n"
        "  gumloop artifacts set-access artifact_abc --share-team team_abc:editor --link anyone\n"
        "  printf '%s' 'secret' | gumloop artifacts set-access artifact_abc --password-stdin --link password"
    ),
)
def set_artifact_access(
    ctx: typer.Context,
    artifact_id: Annotated[str, typer.Argument(help="Artifact id.")],
    share: Annotated[list[str] | None, share_option()] = None,
    remove: Annotated[list[str] | None, remove_option()] = None,
    share_team: Annotated[list[str] | None, share_team_option()] = None,
    remove_team: Annotated[list[str] | None, remove_team_option()] = None,
    organization: Annotated[str | None, organization_option()] = None,
    link: Annotated[str | None, link_option()] = None,
    link_role: Annotated[str | None, link_role_option()] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the new link password from stdin."),
    ] = False,
    json_output: Annotated[bool, json_option()] = False,
) -> None:
    """Change who can access an artifact."""
    set_password: Callable[[Gumloop], ArtifactPasswordResponse] | None = None
    if password_stdin:
        password = read_password_stdin()
        if password == "":
            exit_with_error(GumloopError("Password from stdin is empty."), json_output=json_output)
        set_password = partial(_set_artifact_password, artifact_id=artifact_id, password=password)

    apply_item_access(
        ctx,
        share=share,
        remove=remove,
        share_team=share_team,
        remove_team=remove_team,
        organization=organization,
        link=link,
        link_role=link_role,
        json_output=json_output,
        update=lambda client, parsed: client.artifacts.update_access(
            artifact_id,
            share=parsed.share,
            remove=parsed.remove,
            link=parsed.link,
        ),
        set_password=set_password,
    )


def _set_artifact_password(client: Gumloop, *, artifact_id: str, password: str) -> ArtifactPasswordResponse:
    return client.artifacts.set_password(artifact_id, password)
