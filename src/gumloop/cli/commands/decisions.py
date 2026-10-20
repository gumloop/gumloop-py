from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

decisions_app = typer.Typer(help="Ask decision models structured questions.", no_args_is_help=True)


@decisions_app.command("create", epilog="Example:\n  gumloop decisions create --args-file decision.json --json")
def create_decision(
    ctx: typer.Context,
    args_json: Annotated[str | None, typer.Option("--args-json", help="Decision request as a JSON object.")] = None,
    args_file: Annotated[str | None, typer.Option("--args-file", help="JSON file with model, state and questions.")] = None,
    args: Annotated[str | None, typer.Option("--args", help="Use '-' to read the request JSON from stdin.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the full response as JSON.")] = False,
) -> None:
    """Create a decision using the same request shape as the SDK."""
    cli: CliContext = ctx.obj
    try:
        request = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args)
        response = cli.call_with_refresh(lambda client: client.decisions.create(request))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"Model: {response.model}", markup=False, highlight=False)
    for name, answer in response.answers.items():
        console.print(f"{name}: {answer.model_dump_json(exclude_none=True)}", markup=False, highlight=False)
