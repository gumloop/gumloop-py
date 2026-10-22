from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop._http import ResponseSizeExceededError
from gumloop.cli.commands._downloads import write_download_bytes
from gumloop.cli.commands.artifacts import artifacts_app
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

JsonOutput = Annotated[bool, typer.Option("--json")]


@artifacts_app.command("get")
def get_artifact(
    ctx: typer.Context, artifact_id: str, version_id: str | None = None, json_output: JsonOutput = False
) -> None:
    """Read file metadata."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda c: c.artifacts.retrieve(artifact_id, version_id=version_id), team_id=cli.effective_team_id
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("content")
def content(
    ctx: typer.Context,
    artifact_id: str,
    output: Annotated[Path, typer.Option()],
    version_id: str | None = None,
    max_bytes: Annotated[int, typer.Option(min=1)] = 64 * 1024 * 1024,
    force: Annotated[bool, typer.Option(help="Replace an existing output file.")] = False,
    json_output: JsonOutput = False,
) -> None:
    """Download file content or its bundle ZIP to explicit --output. Use --force to replace a file."""
    cli: CliContext = ctx.obj
    try:
        destination = _output_destination(output, force=force)
        result = cli.call_with_refresh(
            lambda c: c.artifacts.content(artifact_id, version_id=version_id, max_bytes=max_bytes),
            team_id=cli.effective_team_id,
        )
        write_download_bytes(result.content, destination, force=force)
        print_json({"path": str(output), "bytes": len(result.content), "media_type": result.media_type})
    except (OSError, ResponseSizeExceededError) as error:
        exit_with_error(GumloopError(str(error)), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("rename")
def rename(
    ctx: typer.Context, artifact_id: str, name: str | None = None, reset: bool = False, json_output: JsonOutput = False
) -> None:
    """Set --name or --reset the display name; the stored filename stays the same."""
    cli: CliContext = ctx.obj
    try:
        if reset == (name is not None):
            raise GumloopError("Pass exactly one of --name or --reset.")
        print_json(
            cli.call_with_refresh(lambda c: c.artifacts.rename(artifact_id, name), team_id=cli.effective_team_id)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("delete")
def delete(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Soft-delete a legacy generated file; VFS handles cannot be deleted here."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.delete(artifact_id), team_id=cli.effective_team_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("versions")
def versions(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Discover available versions, newest first."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(lambda c: c.artifacts.list_versions(artifact_id), team_id=cli.effective_team_id)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


def _output_destination(output: Path, *, force: bool) -> Path:
    destination = output.expanduser()
    if not force and (destination.exists() or destination.is_symlink()):
        raise GumloopError(f"Output already exists: {destination}. Use --force to replace it.")
    return destination
