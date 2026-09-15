from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape as escape_markup

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

models_app = typer.Typer(
    help="List Gumloop models and route a task to the best one.", no_args_is_help=True, rich_markup_mode="rich"
)


@models_app.command("list", epilog="Examples:\n  gumloop models list\n  gumloop models list --json")
def list_models(
    ctx: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """List the models available to your agents, grouped by provider."""
    cli: CliContext = ctx.obj

    try:
        response = cli.call_with_refresh(lambda client: client.models.list(team_id=cli.effective_team_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print("MODEL", "NAME", "PROVIDER", "STATUS", sep="\t", soft_wrap=True)
    for group in response.model_groups:
        for option in group.get("options", []) or []:
            console.print(
                str(option.get("value", "")),
                str(option.get("label", "")),
                str(group.get("groupLabel", "")),
                str(option.get("status", "")),
                sep="\t",
                soft_wrap=True,
                markup=False,
                highlight=False,
            )


@models_app.command(
    "route",
    epilog=(
        "Examples:\n"
        "  gumloop models route 'Summarize this email thread' --model gpt-5.6-luna --model claude-opus-5\n"
        "  gumloop models route 'Prove this theorem' --json\n"
        "  cat task.txt | gumloop models route --input-stdin - --system-prompt-file agent.md"
    ),
)
def route_model(
    ctx: typer.Context,
    input_text: Annotated[
        str | None,
        typer.Argument(help="The task or user message to route."),
    ] = None,
    input_stdin: Annotated[
        str | None,
        typer.Option("--input-stdin", help="Use '-' to read the task from stdin.", metavar="-"),
    ] = None,
    models: Annotated[
        list[str] | None,
        typer.Option("--model", "-m", help="Candidate model id (repeatable). Omit for the full Gumloop Chew catalog."),
    ] = None,
    agent_name: Annotated[
        str | None,
        typer.Option("--agent-name", help="Name of the agent that will run the task."),
    ] = None,
    agent_description: Annotated[
        str | None,
        typer.Option("--agent-description", help="Description of the agent that will run the task."),
    ] = None,
    system_prompt: Annotated[
        str | None,
        typer.Option("--system-prompt", help="Standing instructions of the agent that will run the task."),
    ] = None,
    system_prompt_file: Annotated[
        str | None,
        typer.Option("--system-prompt-file", help="Path to a file containing the system prompt."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Ask Gumloop Chew which of your models should run a task. Decision only; nothing is executed."""
    cli: CliContext = ctx.obj

    try:
        if input_text is not None and input_stdin is not None:
            raise GumloopError("Pass at most one of INPUT or --input-stdin.")
        if input_stdin is not None and input_stdin != "-":
            raise GumloopError("--input-stdin only accepts '-' (reads from stdin).")
        if system_prompt is not None and system_prompt_file is not None:
            raise GumloopError("Pass at most one of --system-prompt or --system-prompt-file.")
        message = sys.stdin.read() if input_stdin == "-" else input_text
        if message is None or not message.strip():
            raise GumloopError("Provide the task as INPUT or via --input-stdin -.")
        if system_prompt_file is not None:
            try:
                system_prompt = Path(system_prompt_file).expanduser().read_text(encoding="utf-8")
            except OSError as error:
                raise GumloopError(f"Could not read {system_prompt_file}: {error.strerror or error}") from error
        agent = {
            key: value
            for key, value in (
                ("name", agent_name),
                ("description", agent_description),
                ("system_prompt", system_prompt),
            )
            if value
        }

        response = cli.call_with_refresh(
            lambda client: client.models.route(
                input=message,
                models=models or None,
                agent=agent or None,
                team_id=cli.effective_team_id,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    route = response.route
    summary = f"[bold]{escape_markup(route.model)}[/bold]  lane={route.lane}  verdict={route.verdict_lane}"
    if route.adjustment:
        summary += f"  adjustment={route.adjustment}"
    if route.reasoning_effort:
        summary += f"  effort={route.reasoning_effort}"
    if route.fail_closed:
        summary += "  [yellow]fail-closed[/yellow]"
    console.print(summary, markup=True, highlight=False)
    if route.fallback_models:
        console.print("fallbacks: " + ", ".join(route.fallback_models), markup=False, highlight=False)
    console.print("MODEL", "LANES", "BASIS", "STATUS", sep="\t", soft_wrap=True)
    for candidate in response.candidates:
        console.print(
            candidate.model,
            ",".join(candidate.lanes),
            candidate.lane_basis or "",
            candidate.status,
            sep="\t",
            soft_wrap=True,
            markup=False,
            highlight=False,
        )
