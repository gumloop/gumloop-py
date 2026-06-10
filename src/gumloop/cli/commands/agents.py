from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from rich.markup import escape as escape_markup
from rich.table import Table

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

agents_app = typer.Typer(help="Manage Gumloop agents.", no_args_is_help=True, rich_markup_mode="rich")


@agents_app.command(
    "list",
    epilog=("Examples:\n  gumloop agents list\n  gumloop agents list --search support --json"),
)
def list_agents(
    ctx: typer.Context,
    search: Annotated[
        str | None,
        typer.Option("--search", help="Filter agents by name/description."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of agents to return."),
    ] = None,
    cursor: Annotated[
        str | None,
        typer.Option("--cursor", help="Pagination cursor from a previous list call."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """List agents the authenticated user can see."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.agents.list(
                search=search,
                team_id=cli.effective_team_id,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.agents:
        console.print("No agents found.")
    else:
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("NAME")
        table.add_column("MODEL")
        table.add_column("TEAM", style="dim")
        table.add_column("ACTIVE", justify="center")
        for agent in response.agents:
            active = "[green]yes[/green]" if agent.is_active else "[dim]no[/dim]"
            table.add_row(
                escape_markup(agent.id or ""),
                escape_markup(agent.name or ""),
                escape_markup(agent.model_name or ""),
                escape_markup(agent.team_id or ""),
                active,
            )
        console.print(table)

    if response.next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(response.next_cursor)}")


@agents_app.command("get", epilog="Example:\n  gumloop agents get agent_abc --json")
def get_agent(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="ID of the agent to retrieve.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Show one agent's full configuration."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.agents.retrieve(agent_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    # Header line uses markup=True framing -> escape the server-supplied title.
    # Data rows use markup=False end-to-end.
    agent = response.agent
    title = agent.name or agent.id
    console.print(f"[bold]{escape_markup(title)}[/bold]")
    for field in ("id", "model_name", "team_id", "is_active", "folder_id", "description", "created_at"):
        value = getattr(agent, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)
    if agent.system_prompt:
        console.print("  system_prompt:", markup=False, highlight=False)
        console.print(f"    {agent.system_prompt}", markup=False, highlight=False)


@agents_app.command(
    "create",
    epilog=(
        "Examples:\n"
        "  gumloop agents create --name 'Support bot' --model auto\n"
        "  gumloop agents create --name X --model auto --system-prompt-file prompt.md\n"
        '  gumloop agents create --name X --model auto --tools-json \'[{"type":"gumcp_server","server":"gmail"}]\''
    ),
)
def create_agent(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name", help="Display name for the new agent.")],
    model: Annotated[str, typer.Option("--model", help="Model name (for example 'auto').")],
    description: Annotated[
        str | None,
        typer.Option("--description", help="Optional short description."),
    ] = None,
    system_prompt: Annotated[
        str | None,
        typer.Option("--system-prompt", help="Inline system prompt text."),
    ] = None,
    system_prompt_file: Annotated[
        str | None,
        typer.Option("--system-prompt-file", help="Path to a file containing the system prompt."),
    ] = None,
    tools_json: Annotated[
        str | None,
        typer.Option("--tools-json", help="Inline JSON array of tool config objects."),
    ] = None,
    tools_file: Annotated[
        str | None,
        typer.Option("--tools-file", help="Path to a JSON file containing the tools array."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Create a new agent."""
    cli: CliContext = ctx.obj

    try:
        # Resolve --system-prompt vs --system-prompt-file (at most one).
        if system_prompt is not None and system_prompt_file is not None:
            raise GumloopError("Pass at most one of --system-prompt or --system-prompt-file.")
        resolved_prompt = system_prompt
        if system_prompt_file is not None:
            try:
                resolved_prompt = Path(system_prompt_file).expanduser().read_text(encoding="utf-8")
            except OSError as error:
                raise GumloopError(f"Could not read {system_prompt_file}: {error.strerror or error}") from error

        # Resolve --tools-json vs --tools-file (at most one), parse as a top-level array.
        tools: list[dict[str, Any]] | None = None
        if tools_json is not None and tools_file is not None:
            raise GumloopError("Pass at most one of --tools-json or --tools-file.")
        if tools_json is not None or tools_file is not None:
            if tools_file is not None:
                try:
                    raw = Path(tools_file).expanduser().read_text(encoding="utf-8")
                except OSError as error:
                    raise GumloopError(f"Could not read {tools_file}: {error.strerror or error}") from error
            else:
                raw = tools_json or ""
            if not raw.strip():
                tools = []
            else:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as error:
                    raise GumloopError(f"Could not parse tools JSON: {error.msg} at line {error.lineno}.") from error
                if not isinstance(parsed, list):
                    raise GumloopError("Tools JSON must be an array at the top level.")
                tools = parsed

        response = cli.call_with_refresh(
            lambda client: client.agents.create(
                name=name,
                model_name=model,
                description=description,
                system_prompt=resolved_prompt,
                tools=tools,
                team_id=cli.effective_team_id,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    agent = response.agent
    console.print(f"[green]Created agent[/green] {escape_markup(agent.id)}")
    if agent.name:
        console.print(f"  Name: {agent.name}", markup=False, highlight=False)


@agents_app.command(
    "update",
    epilog=(
        "Examples:\n"
        "  gumloop agents update agent_abc --name 'Better bot'\n"
        "  gumloop agents update agent_abc --system-prompt-file new-prompt.md"
    ),
)
def update_agent(
    ctx: typer.Context,
    agent_id: Annotated[str, typer.Argument(help="ID of the agent to update.")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    system_prompt: Annotated[
        str | None,
        typer.Option("--system-prompt", help="Inline system prompt text."),
    ] = None,
    system_prompt_file: Annotated[
        str | None,
        typer.Option("--system-prompt-file", help="Path to a file containing the system prompt."),
    ] = None,
    tools_json: Annotated[
        str | None,
        typer.Option("--tools-json", help="Inline JSON array of tool config objects."),
    ] = None,
    tools_file: Annotated[
        str | None,
        typer.Option("--tools-file", help="Path to a JSON file containing the tools array."),
    ] = None,
    is_active: Annotated[
        bool | None,
        typer.Option("--is-active/--inactive", help="Mark the agent as active or inactive."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Update fields on an existing agent. Only flags you pass get changed."""
    cli: CliContext = ctx.obj

    try:
        if system_prompt is not None and system_prompt_file is not None:
            raise GumloopError("Pass at most one of --system-prompt or --system-prompt-file.")
        resolved_prompt = system_prompt
        if system_prompt_file is not None:
            try:
                resolved_prompt = Path(system_prompt_file).expanduser().read_text(encoding="utf-8")
            except OSError as error:
                raise GumloopError(f"Could not read {system_prompt_file}: {error.strerror or error}") from error

        tools: list[dict[str, Any]] | None = None
        if tools_json is not None and tools_file is not None:
            raise GumloopError("Pass at most one of --tools-json or --tools-file.")
        if tools_json is not None or tools_file is not None:
            if tools_file is not None:
                try:
                    raw = Path(tools_file).expanduser().read_text(encoding="utf-8")
                except OSError as error:
                    raise GumloopError(f"Could not read {tools_file}: {error.strerror or error}") from error
            else:
                raw = tools_json or ""
            if not raw.strip():
                tools = []
            else:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as error:
                    raise GumloopError(f"Could not parse tools JSON: {error.msg} at line {error.lineno}.") from error
                if not isinstance(parsed, list):
                    raise GumloopError("Tools JSON must be an array at the top level.")
                tools = parsed

        response = cli.call_with_refresh(
            lambda client: client.agents.update(
                agent_id,
                name=name,
                model_name=model,
                description=description,
                system_prompt=resolved_prompt,
                tools=tools,
                is_active=is_active,
                team_id=cli.effective_team_id,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Updated agent[/green] {agent_id}")
