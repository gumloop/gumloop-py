from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop._http import ResponseSizeExceededError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.commands._workflow_files import read_upload_files
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

workflows_app = typer.Typer(help="Run existing workflow tabs and transfer workflow files.", no_args_is_help=True)
JsonOutput = Annotated[bool, typer.Option("--json", help="Print JSON output.")]
ProjectId = Annotated[str | None, typer.Option(help="Workspace scope for personal API keys or OAuth.")]


@workflows_app.command("list")
def list_workflows(ctx: typer.Context, project_id: ProjectId = None, json_output: JsonOutput = False) -> None:
    """List saved workflow tabs (saved_item_id), optionally within a workspace."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.workflows.list(project_id=project_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("workbooks")
def list_workbooks(ctx: typer.Context, project_id: ProjectId = None, json_output: JsonOutput = False) -> None:
    """List workbook containers and their saved workflow tabs."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.workflows.list_workbooks(project_id=project_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("inputs")
def workflow_inputs(
    ctx: typer.Context, workflow_id: str, project_id: ProjectId = None, json_output: JsonOutput = False
) -> None:
    """Read the input declarations for a saved workflow tab."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.workflows.inputs(workflow_id, project_id=project_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("run")
def run_workflow(
    ctx: typer.Context,
    workflow_id: str,
    args_json: str | None = None,
    args_file: str | None = None,
    args: str | None = None,
    project_id: ProjectId = None,
    wait: bool = False,
    poll_interval: Annotated[float, typer.Option(min=0)] = 1.0,
    timeout: Annotated[float | None, typer.Option(min=0)] = None,
    json_output: JsonOutput = False,
) -> None:
    """Start a saved tab; --wait polls until done. Input JSON maps input names to values.

    --timeout limits polling; timing out leaves the remote run active. Use cancel to stop it.
    """
    cli: CliContext = ctx.obj
    try:
        inputs = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args)
        started = cli.call_with_refresh(lambda c: c.workflows.start(workflow_id, inputs, project_id=project_id))
        if wait:
            result = cli.call_with_refresh(
                lambda c: c.workflows.wait(
                    started.run_id, project_id=project_id, poll_interval=poll_interval, timeout=timeout
                )
            )
            print_json(result)
        else:
            print_json(started)
    except TimeoutError as error:
        exit_with_error(GumloopError(str(error)), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("status")
def run_status(ctx: typer.Context, run_id: str, project_id: ProjectId = None, json_output: JsonOutput = False) -> None:
    """Read a workflow run's state, outputs, and logs."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.workflows.get_run(run_id, project_id=project_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("cancel")
def cancel_run(ctx: typer.Context, run_id: str, project_id: ProjectId = None, json_output: JsonOutput = False) -> None:
    """Terminate a run and its child runs."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.workflows.cancel_run(run_id, project_id=project_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("upload")
def upload(
    ctx: typer.Context,
    files: list[Path],
    project_id: ProjectId = None,
    file_name: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Upload regular files totaling at most 200 MiB. --file-name can rename one file."""
    cli: CliContext = ctx.obj
    try:
        if file_name is not None and len(files) != 1:
            raise GumloopError("--file-name requires exactly one file.")
        names = [file_name or path.name for path in files]
        if len(set(names)) != len(names):
            raise GumloopError("Upload file names must be unique.")
        contents = read_upload_files(dict(zip(names, files, strict=True)))
        if len(files) == 1:
            result = cli.call_with_refresh(
                lambda c: c.workflows.upload_file(names[0], contents[names[0]], project_id=project_id)
            )
            print_json(result)
            if result.success is False:
                raise typer.Exit(1)
        else:
            result = cli.call_with_refresh(lambda c: c.workflows.upload_files(contents, project_id=project_id))
            print_json(result)
            if result.success is False or result.partial_success or result.failed_files:
                raise typer.Exit(1)
    except OSError as error:
        exit_with_error(GumloopError(f"Could not read upload file: {error}"), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@workflows_app.command("download")
def download(
    ctx: typer.Context,
    file_names: list[str],
    output: Annotated[Path, typer.Option()],
    project_id: ProjectId = None,
    run_id: str | None = None,
    workflow_id: str | None = None,
    max_bytes: Annotated[int, typer.Option(min=1)] = 64 * 1024 * 1024,
    json_output: JsonOutput = False,
) -> None:
    """Download one workflow file, or a ZIP for several files, to explicit --output."""
    cli: CliContext = ctx.obj
    try:
        if len(file_names) == 1:
            result = cli.call_with_refresh(
                lambda c: c.workflows.download_file(
                    file_names[0], project_id=project_id, run_id=run_id, workflow_id=workflow_id, max_bytes=max_bytes
                )
            )
        else:
            result = cli.call_with_refresh(
                lambda c: c.workflows.download_files(
                    file_names, project_id=project_id, run_id=run_id, workflow_id=workflow_id, max_bytes=max_bytes
                )
            )
        destination = output.expanduser()
        destination.write_bytes(result.content)
        print_json({"path": str(destination), "bytes": len(result.content), "media_type": result.media_type})
    except (OSError, ResponseSizeExceededError) as error:
        exit_with_error(GumloopError(str(error)), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
