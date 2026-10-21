from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop._http import ResponseSizeExceededError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.commands._downloads import write_download_bytes
from gumloop.cli.commands.artifacts import artifacts_app
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

hosting_app = typer.Typer(help="Read or change generated-file hosting.", no_args_is_help=True)
scripts_app = typer.Typer(help="Inspect and run declared generated-file scripts.", no_args_is_help=True)
artifacts_app.add_typer(hosting_app, name="hosting")
artifacts_app.add_typer(scripts_app, name="scripts")
JsonOutput = Annotated[bool, typer.Option("--json")]


@artifacts_app.command("get")
def get_artifact(
    ctx: typer.Context, artifact_id: str, version_id: str | None = None, json_output: JsonOutput = False
) -> None:
    """Read file metadata, script declarations, and your consent state."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.retrieve(artifact_id, version_id=version_id)))
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
            lambda c: c.artifacts.content(artifact_id, version_id=version_id, max_bytes=max_bytes)
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
        print_json(cli.call_with_refresh(lambda c: c.artifacts.rename(artifact_id, name)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("delete")
def delete(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Soft-delete a legacy generated file; VFS handles cannot be deleted here."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.delete(artifact_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("versions")
def versions(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Discover available versions, newest first."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.list_versions(artifact_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@artifacts_app.command("restore")
def restore(ctx: typer.Context, artifact_id: str, version_id: str, json_output: JsonOutput = False) -> None:
    """Queue a historical VFS version as a new version. Legacy files cannot be restored."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.restore(artifact_id, version_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@hosting_app.command("get")
def get_hosting(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Read the file's hosting configuration."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.get_hosting(artifact_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@hosting_app.command("enable")
def enable_hosting(
    ctx: typer.Context, artifact_id: str, alias: str | None = None, json_output: JsonOutput = False
) -> None:
    """Enable hosting with a new alias or an existing reserved alias."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.enable_hosting(artifact_id, alias=alias)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@hosting_app.command("rename")
def rename_hosting(ctx: typer.Context, artifact_id: str, alias: str, json_output: JsonOutput = False) -> None:
    """Change the hosted URL alias."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.rename_hosting(artifact_id, alias)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@hosting_app.command("disable")
def disable_hosting(ctx: typer.Context, artifact_id: str, json_output: JsonOutput = False) -> None:
    """Stop serving the hosted file while preserving its alias reservation."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.artifacts.disable_hosting(artifact_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@scripts_app.command("list")
def scripts(
    ctx: typer.Context, artifact_id: str, version_id: str | None = None, json_output: JsonOutput = False
) -> None:
    """Read declared script keys/tools and the selected version's consent state."""
    cli: CliContext = ctx.obj
    try:
        detail = cli.call_with_refresh(lambda c: c.artifacts.retrieve(artifact_id, version_id=version_id))
        print_json(
            {"version_id": detail.version_id, "scripts": detail.scripts, "acknowledgements": detail.acknowledgements}
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@scripts_app.command("acknowledge-integrations")
def acknowledge(ctx: typer.Context, artifact_id: str, version_id: str, json_output: JsonOutput = False) -> None:
    """Record explicit app consent for a reviewed version, using personal API key or OAuth."""
    cli: CliContext = ctx.obj
    try:
        cli.call_with_refresh(lambda c: c.artifacts.acknowledge_integrations(artifact_id, version_id))
        print_json({"acknowledged": True, "version_id": version_id})
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@scripts_app.command("execute")
def execute(
    ctx: typer.Context,
    artifact_id: str,
    key: str,
    args_json: str | None = None,
    args_file: str | None = None,
    args: str | None = None,
    version_id: str | None = None,
    output: Annotated[
        Path | None,
        typer.Option(
            help="Request a generated binary file (download=true); JSON results print to stdout without --output."
        ),
    ] = None,
    max_bytes: Annotated[int, typer.Option(min=1)] = 64 * 1024 * 1024,
    force: Annotated[bool, typer.Option(help="Replace an existing output file.")] = False,
    json_output: JsonOutput = False,
) -> None:
    """Run a script. JSON args are an object with optional payload (any JSON value).

    --output requests a script-generated binary file, not a saved JSON response.
    Without it, JSON prints to stdout. Execution uses current app permissions and bills the caller.
    """
    cli: CliContext = ctx.obj
    try:
        request = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args)
        if set(request) - {"payload"}:
            raise GumloopError("Script args accept only the payload field.")
        if output is None:
            print_json(
                cli.call_with_refresh(
                    lambda c: c.artifacts.execute_script(
                        artifact_id, key, payload=request.get("payload"), version_id=version_id
                    )
                )
            )
        else:
            destination = _output_destination(output, force=force)
            result = cli.call_with_refresh(
                lambda c: c.artifacts.download_script(
                    artifact_id, key, payload=request.get("payload"), version_id=version_id, max_bytes=max_bytes
                )
            )
            write_download_bytes(result.content, destination, force=force)
            print_json({"path": str(output), "bytes": len(result.content), "media_type": result.media_type})
    except (OSError, ResponseSizeExceededError) as error:
        exit_with_error(GumloopError(str(error)), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


def _output_destination(output: Path, *, force: bool) -> Path:
    destination = output.expanduser()
    if not force and (destination.exists() or destination.is_symlink()):
        raise GumloopError(f"Output already exists: {destination}. Use --force to replace it.")
    return destination
