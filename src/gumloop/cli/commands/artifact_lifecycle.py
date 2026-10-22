from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.commands.artifacts import artifacts_app
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

JsonOutput = Annotated[bool, typer.Option("--json")]


@artifacts_app.command("get")
def get_artifact(
    ctx: typer.Context, artifact_id: str, version_id: str | None = None, json_output: JsonOutput = False
) -> None:
    """Get existing download metadata and its signed URL without downloading bytes."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda c: c.artifacts.download(artifact_id, version_id=version_id, team_id=cli.effective_team_id)
            )
        )
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
            cli.call_with_refresh(lambda c: c.artifacts.rename(artifact_id, name, team_id=cli.effective_team_id))
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("delete")
def delete(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Soft-delete a legacy generated file; VFS handles cannot be deleted here."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.delete(artifact_id, team_id=cli.effective_team_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("versions")
def versions(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Discover available versions, newest first."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(lambda c: c.artifacts.list_versions(artifact_id, team_id=cli.effective_team_id))
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
