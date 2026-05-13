from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from rich.table import Table

from gumloop import GumloopError
from gumloop.cli.commands._downloads import download_response
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.skills import SkillFile

skills_app = typer.Typer(help="Manage Gumloop skills.", no_args_is_help=True, rich_markup_mode="rich")


def _render_skills(skills: Sequence[Mapping[str, Any]]) -> None:
    if not skills:
        console.print("No skills found.")
        return

    table = Table(title="Gumloop Skills")
    table.add_column("ID", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Team", overflow="fold")
    table.add_column("Usage", justify="right")
    table.add_column("Updated")

    for skill in skills:
        table.add_row(
            str(skill.get("id") or ""),
            str(skill.get("name") or ""),
            str(skill.get("team_id") or ""),
            "" if skill.get("usage_count") is None else str(skill.get("usage_count")),
            str(skill.get("updated_at") or ""),
        )

    console.print(table)


def _read_files(paths: Sequence[Path]) -> list[SkillFile]:
    contents: list[SkillFile] = []
    for path in paths:
        resolved = path.expanduser()
        if not resolved.exists():
            raise GumloopError(f"File not found: {path}")
        if not resolved.is_file():
            raise GumloopError(f"Not a regular file: {path}")
        contents.append((resolved.name, resolved.read_bytes()))
    return contents


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

    _render_skills(response.get("skills", []))
    next_cursor = response.get("next_cursor")
    if next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {next_cursor}")


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
        payload_files = _read_files(files)
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

    skill = response.get("skill") or {}
    console.print(f"[green]Created skill[/green] {skill.get('id', '')}")
    skill_name = skill.get("name")
    if skill_name:
        console.print(f"  Name: {skill_name}")


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
        payload_files = _read_files(files)
        response = cli.call_with_refresh(lambda client: client.skills.update(skill_id, files=payload_files))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Updated skill[/green] {skill_id}")


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
