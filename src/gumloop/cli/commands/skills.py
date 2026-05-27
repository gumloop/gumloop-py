from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape as escape_markup

from gumloop import GumloopError
from gumloop.cli.commands._downloads import download_response
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.resources.skills import SkillFile

skills_app = typer.Typer(help="Manage Gumloop skills.", no_args_is_help=True, rich_markup_mode="rich")


@skills_app.command(
    "list",
    epilog=("Examples:\n  gumloop skills list\n  gumloop skills list --search retrieval --limit 50 --json"),
)
def list_skills(
    ctx: typer.Context,
    search: Annotated[
        str | None,
        typer.Option("--search", help="Filter skills by query string."),
    ] = None,
    server: Annotated[
        str | None,
        typer.Option("--server", help="Filter skills related to a specific MCP server id."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of skills to return."),
    ] = None,
    cursor: Annotated[
        str | None,
        typer.Option("--cursor", help="Pagination cursor returned by a previous list call."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """List skills the authenticated user can see."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.skills.list(
                team_id=cli.effective_team_id,
                search_query=search,
                related_server_id=server,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.skills:
        console.print("No skills found.")
    else:
        console.print("ID", "NAME", "TEAM", "USAGE", "UPDATED", sep="\t", soft_wrap=True)
        for skill in response.skills:
            console.print(
                skill.id,
                skill.name,
                skill.team_id,
                "" if skill.usage_count is None else str(skill.usage_count),
                skill.updated_at or "",
                sep="\t",
                soft_wrap=True,
            )

    if response.next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(response.next_cursor)}")


@skills_app.command(
    "create",
    epilog=("Examples:\n  gumloop skills create ./my-skill.md\n  gumloop skills create skills/*.md --json"),
)
def create_skill(
    ctx: typer.Context,
    files: Annotated[
        list[Path],
        typer.Argument(
            help="One or more skill files to upload.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Upload one or more files as a new skill."""
    cli: CliContext = ctx.obj
    try:
        payload_files: list[SkillFile] = []
        for path in files:
            resolved = path.expanduser()
            if not resolved.exists():
                raise GumloopError(f"File not found: {path}")
            if not resolved.is_file():
                raise GumloopError(f"Not a regular file: {path}")
            try:
                payload_files.append((resolved.name, resolved.read_bytes()))
            except OSError as error:
                raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error

        response = cli.call_with_refresh(
            lambda client: client.skills.create(
                files=payload_files,
                team_id=cli.effective_team_id,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    skill = response.skill
    console.print(f"[green]Created skill[/green] {escape_markup(skill.id)}")
    if skill.name:
        console.print(f"  Name: {skill.name}", markup=False, highlight=False)


@skills_app.command(
    "update",
    epilog="Example:\n  gumloop skills update skill_abc ./new-version.md",
)
def update_skill(
    ctx: typer.Context,
    skill_id: Annotated[str, typer.Argument(help="ID of the skill to update.")],
    files: Annotated[
        list[Path],
        typer.Argument(
            help="One or more replacement files for the skill.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Replace the files attached to an existing skill."""
    cli: CliContext = ctx.obj
    try:
        payload_files: list[SkillFile] = []
        for path in files:
            resolved = path.expanduser()
            if not resolved.exists():
                raise GumloopError(f"File not found: {path}")
            if not resolved.is_file():
                raise GumloopError(f"Not a regular file: {path}")
            try:
                payload_files.append((resolved.name, resolved.read_bytes()))
            except OSError as error:
                raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error

        response = cli.call_with_refresh(lambda client: client.skills.update(skill_id, files=payload_files))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Updated skill[/green] {skill_id}")


@skills_app.command("delete", epilog="Example:\n  gumloop skills delete skill_abc")
def delete_skill(
    ctx: typer.Context,
    skill_id: Annotated[str, typer.Argument(help="ID of the skill to delete.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Delete an existing skill."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.skills.delete(skill_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Deleted skill[/green] {escape_markup(skill_id)}")


@skills_app.command(
    "download",
    epilog=(
        "Examples:\n"
        "  gumloop skills download skill_abc\n"
        "  gumloop skills download skill_abc -o ./local-name.md\n"
        "  gumloop skills download skill_abc -o -"
    ),
)
def download_skill(
    ctx: typer.Context,
    skill_id: Annotated[str, typer.Argument(help="ID of the skill to download.")],
    output: Annotated[
        str | None,
        typer.Option("-o", "--output", help="File or directory to write to. Use '-' for stdout."),
    ] = None,
    version_id: Annotated[
        str | None,
        typer.Option("--version-id", help="Specific skill version to download."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the local download metadata as JSON."),
    ] = False,
) -> None:
    """Download a skill's files via the SDK's signed download URL."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.skills.download(skill_id, version_id=version_id))
        result = download_response(response, output=output, fallback_name=f"{skill_id}.bin")
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(result)
        return

    if result["path"] is None:
        return
    console.print(f"[green]Saved[/green] {result['path']} ({result['bytes']} bytes)")
