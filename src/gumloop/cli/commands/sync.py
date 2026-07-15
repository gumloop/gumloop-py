from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from typing import NoReturn

import typer

from gumloop.cli.console import error_console
from gumloop.cli.console import print_json
from gumloop.cli.console import print_json_error
from gumloop.cli.context import CliContext
from gumloop.cli.commands._sync_output import SyncOutput
from gumloop.sync.errors import SyncError
from gumloop.sync.local_state import load_config
from gumloop.sync.lock import sync_lock
from gumloop.sync.results import SyncExecution
from gumloop.sync.run import run_sync

sync_app = typer.Typer(
    help="Converge coding-agent Skills from Gumloop.",
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode="rich",
)


@sync_app.callback(invoke_without_command=True)
def sync(
    ctx: typer.Context,
    once: Annotated[
        bool,
        typer.Option("--once", help="Run stateless sync for an ephemeral environment."),
    ] = False,
    non_interactive: Annotated[
        bool,
        typer.Option("--non-interactive", help="Never prompt or open a browser."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print one deterministic JSON result."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="List every changed Skill after syncing."),
    ] = False,
) -> None:
    """Converge detected user-level coding-agent targets once."""
    cli: CliContext = ctx.obj
    try:
        if once:
            if not non_interactive:
                raise typer.BadParameter("--once requires --non-interactive")
            if not os.environ.get("GUMLOOP_API_KEY") or not os.environ.get("GUMLOOP_USER_ID"):
                raise SyncError(
                    "auth_required",
                    "Stateless sync requires GUMLOOP_API_KEY and GUMLOOP_USER_ID.",
                )
            cli.credentials.access_token = None
            cli.credentials.refresh_token = None
            cli.credentials.api_key = os.environ["GUMLOOP_API_KEY"]
            cli.user_id_override = os.environ["GUMLOOP_USER_ID"]
            config = None
        else:
            config = load_config(Path.home())

        output = SyncOutput()
        with output, sync_lock(home=Path.home()):
            execution = run_sync(
                cli=cli,
                home=Path.home(),
                config=config,
                on_progress=None if json_output else output,
            )
    except SyncError as error:
        _exit_sync_error(error, json_output=json_output)
    except typer.BadParameter:
        raise
    except Exception as error:
        _exit_sync_error(
            SyncError(
                "target_failed",
                "Skill sync failed unexpectedly.",
                details={"reason": str(error), "type": error.__class__.__name__},
            ),
            json_output=json_output,
        )

    _print_execution(
        execution,
        json_output=json_output,
        verbose=verbose,
        output=output,
    )
    if execution.status != "ok":
        raise typer.Exit(1)


def _print_execution(
    execution: SyncExecution,
    *,
    json_output: bool,
    verbose: bool,
    output: SyncOutput,
) -> None:
    envelope = {
        "command": "sync",
        "error": None,
        "result": execution.result,
        "schema_version": 1,
        "status": execution.status,
    }
    if json_output:
        print_json(envelope)
        return

    output.print_result(execution, verbose=verbose)


def _exit_sync_error(error: SyncError, *, json_output: bool) -> NoReturn:
    envelope = {
        "command": "sync",
        "error": {
            "code": error.code,
            "details": error.details or None,
            "message": str(error),
        },
        "result": None,
        "schema_version": 1,
        "status": "error",
    }
    if json_output:
        print_json_error(envelope)
    else:
        error_console.print(f"Error: {error}", markup=False, highlight=False)
    raise typer.Exit(1)
