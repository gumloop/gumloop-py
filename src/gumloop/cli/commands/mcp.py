from __future__ import annotations

from typing import Annotated

import typer
from rich.markup import escape as escape_markup
from rich.table import Table
from rich.text import Text

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

mcp_app = typer.Typer(help="Explore Gumloop MCP servers.", no_args_is_help=True, rich_markup_mode="rich")


@mcp_app.command("list", epilog="Example:\n  gumloop mcp list --json")
def list_servers(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw SDK response as JSON.")] = False,
) -> None:
    """List MCP servers available to the authenticated Gumloop user."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.mcp.list_servers(team_id=cli.effective_team_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.servers:
        console.print("No MCP servers found.")
        return

    table = Table(title="Gumloop MCP Servers")
    table.add_column("Server ID", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Tools", justify="right")
    table.add_column("Auth URL", overflow="fold")
    # Table cells default to markup=True; Text cells render as plain text.
    for server in response.servers:
        auth_url = "" if server.status == "connected" else (server.gumloop_auth_url or "")
        table.add_row(
            Text(server.server_id),
            Text(server.name or ""),
            Text(server.type),
            Text(server.status),
            "" if server.tool_count is None else str(server.tool_count),
            Text(auth_url),
        )
    console.print(table)


@mcp_app.command("get", epilog="Example:\n  gumloop mcp get gmail --json")
def get_server(
    ctx: typer.Context,
    server: Annotated[str, typer.Argument(help="MCP server id (for example 'gmail').")],
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw SDK response as JSON.")] = False,
) -> None:
    """Show one MCP server's details."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.mcp.get_server(server, team_id=cli.effective_team_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    payload = response.server
    title = payload.name or payload.server_id
    console.print(f"[bold]{escape_markup(title)}[/bold]")
    for field in ("server_id", "type", "status", "tool_count", "description", "gumloop_auth_url", "mcp_url"):
        value = getattr(payload, field, None)
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)


@mcp_app.command("tools", epilog="Example:\n  gumloop mcp tools gmail")
def list_tools(
    ctx: typer.Context,
    server: Annotated[str, typer.Argument(help="MCP server id whose tools should be listed.")],
    json_output: Annotated[bool, typer.Option("--json", help="Print the raw SDK response as JSON.")] = False,
) -> None:
    """List the tools a connected MCP server exposes."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.mcp.list_tools(server, team_id=cli.effective_team_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if response.status and response.status != "connected":
        status_text = escape_markup(response.status)
        console.print(f"Server [bold]{escape_markup(server)}[/bold] is not connected ({status_text}).")
        if response.gumloop_auth_url:
            console.print(f"Connect here: {response.gumloop_auth_url}", markup=False, highlight=False)
        return

    if not response.tools:
        console.print("No tools found.")
        return

    table = Table(title="MCP Tools")
    table.add_column("Name", overflow="fold")
    table.add_column("Tool Call ID", overflow="fold")
    table.add_column("Description", overflow="fold")
    for tool in response.tools:
        table.add_row(
            Text(tool.name),
            Text(tool.tool_call_id),
            Text(tool.description or ""),
        )
    console.print(table)


@mcp_app.command(
    "call",
    epilog=(
        "Examples:\n"
        "  gumloop mcp call gmail list_emails --args-json '{\"max_results\": 5}'\n"
        "  gumloop mcp call gmail send_email --args-file ./email.json\n"
        "  cat email.json | gumloop mcp call gmail send_email --args -"
    ),
)
def call_tool(
    ctx: typer.Context,
    server: Annotated[str, typer.Argument(help="MCP server id (for example 'gmail').")],
    tool: Annotated[str, typer.Argument(help="Tool name on that server (for example 'list_emails').")],
    args_json: Annotated[
        str | None,
        typer.Option("--args-json", help="Inline JSON object of tool arguments."),
    ] = None,
    args_file: Annotated[
        str | None,
        typer.Option("--args-file", help="Path to a file containing the JSON arguments."),
    ] = None,
    args_stdin: Annotated[
        str | None,
        typer.Option("--args", help="Use '-' to read JSON arguments from stdin.", metavar="-"),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option("--ref", help="Optional ref string echoed back in the response."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw SDK response as JSON."),
    ] = False,
) -> None:
    """Execute an MCP tool on a server."""
    cli: CliContext = ctx.obj
    try:
        arguments = resolve_json_args(inline=args_json, file_path=args_file, stdin_marker=args_stdin)
        response = cli.call_with_refresh(
            lambda client: client.mcp.execute(
                server,
                tool,
                arguments,
                ref=ref,
                team_id=cli.effective_team_id,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    # markup=False on remote fields stops MCP server output from rendering
    # as Rich markup (e.g. fake terminal hyperlinks).
    if not response.results:
        console.print("(no results)")
        return
    for result in response.results:
        ref_value = result.ref or ""
        tool_name = result.tool_name or ""
        ref_suffix = f" (ref: {escape_markup(ref_value)})" if ref_value else ""
        console.print(f"[bold]{escape_markup(tool_name)}[/bold]{ref_suffix}", markup=True, highlight=False)
        console.print(f"  status: {result.status}", markup=False, highlight=False)
        if result.error:
            console.print(f"  error: {result.error}", markup=False, highlight=False)
        content = result.content
        if not content:
            continue
        if isinstance(content, str):
            console.print(content, markup=False, highlight=False)
        else:
            print_json(content)
