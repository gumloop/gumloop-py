from __future__ import annotations

from typing import Annotated
from typing import Literal

import typer
from pydantic import ValidationError

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.commands.discovery import organizations_app
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import DataExportRequest

roles_app = typer.Typer(help="Read and set custom-role monthly credit caps.", no_args_is_help=True)
exports_app = typer.Typer(help="Create scoped exports and read their status.", no_args_is_help=True)
organizations_app.add_typer(roles_app, name="roles")
organizations_app.add_typer(exports_app, name="exports")
JsonOutput = Annotated[bool, typer.Option("--json", help="Print JSON output.")]


@roles_app.command("list")
def list_limits(
    ctx: typer.Context,
    organization_id: str,
    page_size: int = 20,
    cursor: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """List roles and caps. Requires view_permission_groups."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda c: c.organizations.list_role_credit_limits(organization_id, page_size=page_size, cursor=cursor)
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@roles_app.command("get")
def get_limit(ctx: typer.Context, organization_id: str, role_id: str, json_output: JsonOutput = False) -> None:
    """Read a role cap. Requires view_permission_groups."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.organizations.get_role_credit_limit(organization_id, role_id)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@roles_app.command("set")
def set_limit(
    ctx: typer.Context,
    organization_id: str,
    role_id: str,
    monthly_credit_limit: Annotated[int | None, typer.Option(min=0)] = None,
    clear: bool = False,
    json_output: JsonOutput = False,
) -> None:
    """Set --monthly-credit-limit or --clear. Requires manage_permission_groups."""
    cli: CliContext = ctx.obj
    try:
        if clear == (monthly_credit_limit is not None):
            raise GumloopError("Pass exactly one of --monthly-credit-limit or --clear.")
        print_json(
            cli.call_with_refresh(
                lambda c: c.organizations.set_role_credit_limit(organization_id, role_id, monthly_credit_limit)
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@organizations_app.command("audit-logs")
def audit_logs(
    ctx: typer.Context,
    organization_id: str,
    start_time: str,
    end_time: str,
    page: int = 1,
    page_size: int = 50,
    event_type: list[str] | None = None,
    user_id: Annotated[list[str] | None, typer.Option("--filter-user-id")] = None,
    ip_address: list[str] | None = None,
    workspace_id: list[str] | None = None,
    entity_id: list[str] | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Read a bounded ISO-time range. Requires view_audit_logs; filters can repeat."""
    cli: CliContext = ctx.obj
    try:
        print_json(
            cli.call_with_refresh(
                lambda c: c.organizations.audit_logs(
                    organization_id,
                    start_time=start_time,
                    end_time=end_time,
                    page=page,
                    page_size=page_size,
                    event_types=event_type,
                    user_ids=user_id,
                    ip_addresses=ip_address,
                    workspace_ids=workspace_id,
                    entity_ids=entity_id,
                )
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@organizations_app.command("workspace-user")
def workspace_user(
    ctx: typer.Context,
    organization_id: str,
    workspace_id: str,
    user_email: str,
    action: Annotated[str, typer.Option(help="add or remove.")],
    is_admin: bool = False,
    json_output: JsonOutput = False,
) -> None:
    """Change workspace membership. Requires project membership administration permissions."""
    cli: CliContext = ctx.obj
    try:
        if action not in ("add", "remove"):
            raise GumloopError("--action must be add or remove.")
        selected: Literal["add", "remove"] = "add" if action == "add" else "remove"
        print_json(
            cli.call_with_refresh(
                lambda c: c.organizations.manage_workspace_user(
                    organization_id, workspace_id, user_email, action=selected, is_admin=is_admin
                )
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@organizations_app.command("role-user")
def role_user(
    ctx: typer.Context,
    organization_id: str,
    role_id: str,
    user_email: str,
    action: Annotated[str, typer.Option(help="add or remove.")],
    json_output: JsonOutput = False,
) -> None:
    """Change custom-role membership. Requires manage_permission_groups."""
    cli: CliContext = ctx.obj
    try:
        if action not in ("add", "remove"):
            raise GumloopError("--action must be add or remove.")
        selected: Literal["add", "remove"] = "add" if action == "add" else "remove"
        print_json(
            cli.call_with_refresh(
                lambda c: c.organizations.manage_role_user(organization_id, role_id, user_email, action=selected)
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@exports_app.command("create")
def create_export(
    ctx: typer.Context,
    args_json: str | None = None,
    args_file: str | None = None,
    args: str | None = None,
    json_output: JsonOutput = False,
) -> None:
    """Create from JSON (--args-json/--args-file/--args -), with explicit export_scope and data_type.

    Personal and organization exports have separate permissions and plan restrictions.
    """
    cli: CliContext = ctx.obj
    try:
        request = DataExportRequest.model_validate(
            resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args)
        )
        print_json(cli.call_with_refresh(lambda c: c.organizations.export_data(request)))
    except ValidationError as error:
        exit_with_error(GumloopError(str(error)), json_output=json_output)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


@exports_app.command("status")
def export_status(
    ctx: typer.Context, export_id: str, download_url: bool = False, json_output: JsonOutput = False
) -> None:
    """Read your export; --download-url returns a signed URL only when complete."""
    cli: CliContext = ctx.obj
    try:
        print_json(cli.call_with_refresh(lambda c: c.organizations.export_status(export_id, download_url=download_url)))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)
