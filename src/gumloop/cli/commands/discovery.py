from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

teams_app = typer.Typer(help="Find the teams you can access.", no_args_is_help=True)
organizations_app = typer.Typer(help="Find your organizations.", no_args_is_help=True)


@teams_app.command("list", epilog="Example:\n  gumloop teams list --json")
def list_teams(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Print team IDs and names as JSON.")] = False,
) -> None:
    """List accessible teams and their IDs for use with --team-id."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.teams.list())
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.teams:
        console.print("No teams found.")
    for team in response.teams:
        console.print(f"{team.id}\t{team.name}", markup=False, highlight=False)


@organizations_app.command("list", epilog="Example:\n  gumloop organizations list --json")
def list_organizations(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Print organization IDs and names as JSON.")] = False,
) -> None:
    """List the organizations you belong to."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.organizations.list())
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.organizations:
        console.print("No organizations found.")
    for organization in response.organizations:
        console.print(f"{organization.id}\t{organization.name or ''}", markup=False, highlight=False)
