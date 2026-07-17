from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from typing import NoReturn

import typer

from gumloop._client import DEFAULT_BASE_URL
from gumloop.cli.commands._sync_output import SyncOutput
from gumloop.cli.console import error_console
from gumloop.cli.console import print_json
from gumloop.cli.console import print_json_error
from gumloop.cli.context import CliContext
from gumloop.cli.credentials import is_keyring_available
from gumloop.cli.credentials import load_credentials
from gumloop.sync.errors import SyncError
from gumloop.sync.local_state import SyncConfig
from gumloop.sync.local_state import load_config
from gumloop.sync.local_state import remove_config
from gumloop.sync.local_state import write_config
from gumloop.sync.lock import sync_lock
from gumloop.sync.results import SyncExecution
from gumloop.sync.run import BeforeTargetWrites
from gumloop.sync.run import DepartureCleanup
from gumloop.sync.run import run_sync
from gumloop.sync.scheduler import SYNC_INTERVAL_SECONDS
from gumloop.sync.scheduler import SyncScheduler
from gumloop.sync.scheduler import resolve_gumloop_executable
from gumloop.sync.scheduler import scheduler_for_current_platform
from gumloop.sync.targets import PhysicalTarget
from gumloop.types import CliSyncPlanResponse

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
    home = Path.home()
    try:
        output = SyncOutput()
        with output, sync_lock(home=home):
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
                before_target_writes = None
                on_departure = None
                background = None
            else:
                config, cli, before_target_writes, on_departure, background = _prepare_persistent_sync(
                    cli=cli,
                    home=home,
                    non_interactive=non_interactive,
                    json_output=json_output,
                    output=output,
                )
            execution = run_sync(
                cli=cli,
                home=home,
                config=config,
                on_progress=None if json_output else output,
                before_target_writes=before_target_writes,
                on_departure=on_departure,
                background=background,
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


def _prepare_persistent_sync(
    *,
    cli: CliContext,
    home: Path,
    non_interactive: bool,
    json_output: bool,
    output: SyncOutput,
) -> tuple[
    SyncConfig | None,
    CliContext,
    BeforeTargetWrites | None,
    DepartureCleanup | None,
    dict[str, object],
]:
    try:
        config = load_config(home)
    except SyncError as error:
        if error.code != "not_configured" or non_interactive:
            raise
        return _prepare_enrollment(
            cli=cli,
            home=home,
            json_output=json_output,
            output=output,
        )

    scheduler = scheduler_for_current_platform(home=home)
    if non_interactive:
        background: dict[str, object] = {
            "enabled": scheduler.is_current(
                Path(config.scheduler_gumloop_path)
            ),
            "interval_seconds": SYNC_INTERVAL_SECONDS,
            "scheduler": "launch_agent",
        }
        return (
            config,
            cli,
            None,
            _departure_cleanup_callback(
                scheduler=scheduler,
                home=home,
                background=background,
            ),
            background,
        )

    executable_path = resolve_gumloop_executable()
    scheduler.validate(executable_path)
    was_current = (
        config.scheduler_gumloop_path == str(executable_path)
        and scheduler.is_current(executable_path)
    )
    scheduler.install(executable_path)
    background = {
        "enabled": True,
        "interval_seconds": SYNC_INTERVAL_SECONDS,
        "scheduler": "launch_agent",
    }
    if config.scheduler_gumloop_path != str(executable_path):
        config = config.model_copy(
            update={"scheduler_gumloop_path": str(executable_path)}
        )
        write_config(config, home)
    if not json_output and not was_current:
        output.print_background_status("repaired")
    return (
        config,
        cli,
        None,
        _departure_cleanup_callback(
            scheduler=scheduler,
            home=home,
            background=background,
        ),
        background,
    )


def _prepare_enrollment(
    *,
    cli: CliContext,
    home: Path,
    json_output: bool,
    output: SyncOutput,
) -> tuple[
    None,
    CliContext,
    BeforeTargetWrites,
    None,
    dict[str, object],
]:
    enrollment_cli = _durable_enrollment_context(cli)
    scheduler = scheduler_for_current_platform(home=home)
    executable_path = resolve_gumloop_executable()
    scheduler.validate(executable_path)
    background: dict[str, object] = {
        "enabled": True,
        "interval_seconds": SYNC_INTERVAL_SECONDS,
        "scheduler": "launch_agent",
    }

    def commit_enrollment(
        plan: CliSyncPlanResponse,
        targets: tuple[PhysicalTarget, ...],
    ) -> SyncConfig:
        if not json_output:
            output.print_enrollment(plan=plan, targets=targets)
        new_config = SyncConfig(
            schema_version=1,
            organization_id=plan.organization.organization_id,
            scheduler_gumloop_path=str(executable_path),
        )
        try:
            scheduler.install(executable_path)
            write_config(new_config, home)
        except Exception:
            try:
                scheduler.remove()
            except Exception:
                pass
            raise
        if not json_output:
            output.print_background_status("enabled")
        return new_config

    return None, enrollment_cli, commit_enrollment, None, background


def _departure_cleanup_callback(
    *,
    scheduler: SyncScheduler,
    home: Path,
    background: dict[str, object],
) -> DepartureCleanup:
    def cleanup() -> None:
        scheduler.remove()
        remove_config(home)
        background["enabled"] = False

    return cleanup


def _durable_enrollment_context(cli: CliContext) -> CliContext:
    if not is_keyring_available():
        raise SyncError(
            "scheduler_unavailable",
            "Persistent Skill sync requires an operating-system keychain. "
            "Use `gumloop sync --once --non-interactive` on this machine.",
        )
    durable = load_credentials()
    if not durable.has_any or (durable.auth_method == "api_key" and not durable.user_id):
        raise SyncError(
            "auth_required",
            "Sign in with `gumloop login`, then run `gumloop sync` again.",
        )
    if os.environ.get("GUMLOOP_ACCESS_TOKEN") or os.environ.get("GUMLOOP_API_KEY"):
        raise SyncError(
            "auth_required",
            "Persistent enrollment cannot use temporary credential overrides. "
            "Save the credential with `gumloop login`, then retry.",
        )
    durable_base_url = (durable.base_url or DEFAULT_BASE_URL).rstrip("/")
    if cli.base_url_override is not None and cli.base_url_override.rstrip("/") != durable_base_url:
        raise SyncError(
            "auth_required",
            "Persistent enrollment cannot use a temporary base URL override. "
            "Run `gumloop login` against that URL, then retry.",
        )
    return CliContext(credentials=durable)


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
