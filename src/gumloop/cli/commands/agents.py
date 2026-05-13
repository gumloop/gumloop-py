from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from rich.table import Table

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

agents_app = typer.Typer(help="Manage Gumloop agents.", no_args_is_help=True, rich_markup_mode="rich")


def _render_agents(agents: Sequence[Mapping[str, Any]]) -> None:
    if not agents:
        console.print("No agents found.")
        return

    table = Table(title="Gumloop Agents")
    table.add_column("ID", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Model", overflow="fold")
    table.add_column("Team", overflow="fold")
    table.add_column("Active")

    for agent in agents:
        table.add_row(
            str(agent.get("id") or ""),
            str(agent.get("name") or ""),
            str(agent.get("model_name") or ""),
            str(agent.get("team_id") or ""),
            "yes" if agent.get("is_active") else "no",
        )

    console.print(table)


def _render_agent(agent: Mapping[str, Any]) -> None:
    console.print(f"[bold]{agent.get('name') or agent.get('id')}[/bold]")
    for field in ("id", "model_name", "team_id", "is_active", "folder_id", "description", "created_at"):
        value = agent.get(field)
        if value not in (None, ""):
            console.print(f"  {field}: {value}")
    if agent.get("system_prompt"):
        console.print(f"  system_prompt:\n    {agent['system_prompt']}")


def _read_prompt(value: str | None, file_path: str | None, field_name: str) -> str | None:
    if value is not None and file_path is not None:
        raise GumloopError(f"Pass at most one of --{field_name} or --{field_name}-file.")
    if file_path is not None:
        return Path(file_path).expanduser().read_text(encoding="utf-8")
    return value


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

    _render_agents(response.get("agents", []))
    next_cursor = response.get("next_cursor")
    if next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {next_cursor}")


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

    payload = response.get("agent")
    if isinstance(payload, Mapping):
        _render_agent(payload)
    else:
        console.print("(no agent payload)")


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
        resolved_prompt = _read_prompt(system_prompt, system_prompt_file, "system-prompt")
        tools = _resolve_tools(tools_json, tools_file)
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

    agent = response.get("agent") or {}
    console.print(f"[green]Created agent[/green] {agent.get('id', '')}")
    agent_name = agent.get("name")
    if agent_name:
        console.print(f"  Name: {agent_name}")


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
        resolved_prompt = _read_prompt(system_prompt, system_prompt_file, "system-prompt")
        tools = _resolve_tools(tools_json, tools_file)
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


def _resolve_tools(tools_json: str | None, tools_file: str | None) -> list[dict[str, Any]] | None:
    # Not via resolve_json_args: that requires a top-level object, tools is an array.
    if tools_json is None and tools_file is None:
        return None
    if tools_json is not None and tools_file is not None:
        raise GumloopError("Pass at most one of --tools-json or --tools-file.")

    import json

    if tools_file is not None:
        raw = Path(tools_file).expanduser().read_text(encoding="utf-8")
    else:
        raw = tools_json or ""

    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GumloopError(f"Could not parse tools JSON: {error.msg} at line {error.lineno}.") from error
    if not isinstance(parsed, list):
        raise GumloopError("Tools JSON must be an array at the top level.")
    return parsed
