from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Annotated
from typing import Any

import typer
from rich.table import Table

from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

mcp_app = typer.Typer(help="Explore Gumloop MCP servers.", no_args_is_help=True, rich_markup_mode="rich")


def _render_servers(servers: Sequence[Mapping[str, Any]]) -> None:
    if not servers:
        console.print("No MCP servers found.")
        return

    table = Table(title="Gumloop MCP Servers")
    table.add_column("Server ID", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Tools", justify="right")
    table.add_column("Auth URL", overflow="fold")

    for server in servers:
        status_value = str(server.get("status") or "")
        auth_url = "" if status_value == "connected" else str(server.get("gumloop_auth_url") or "")
        tool_count = server.get("tool_count")
        table.add_row(
            str(server.get("server_id") or ""),
            str(server.get("name") or ""),
            str(server.get("type") or ""),
            status_value,
            "" if tool_count is None else str(tool_count),
            auth_url,
        )

    console.print(table)


def _render_server(server: Mapping[str, Any]) -> None:
    console.print(f"[bold]{server.get('name') or server.get('server_id')}[/bold]")
    for field in ("server_id", "type", "status", "tool_count", "description", "gumloop_auth_url", "mcp_url"):
        value = server.get(field)
        if value not in (None, ""):
            console.print(f"  {field}: {value}")


def _render_tools(tools: Sequence[Mapping[str, Any]]) -> None:
    if not tools:
        console.print("No tools found.")
        return

    table = Table(title="MCP Tools")
    table.add_column("Name", overflow="fold")
    table.add_column("Tool Call ID", overflow="fold")
    table.add_column("Description", overflow="fold")

    for tool in tools:
        table.add_row(
            str(tool.get("name") or ""),
            str(tool.get("tool_call_id") or ""),
            str(tool.get("description") or ""),
        )

    console.print(table)


def _render_call_result(response: Mapping[str, Any]) -> None:
    # markup=False on remote fields stops MCP server output from being
    # interpreted as Rich markup (e.g. fake terminal hyperlinks). Framing
    # uses markup=True because we built it from trusted strings.
    results = response.get("results") or []
    if not results:
        console.print("(no results)")
        return
    for result in results:
        status_value = str(result.get("status") or "")
        ref = result.get("ref") or ""
        tool_name = str(result.get("tool_name") or "")
        ref_suffix = f" (ref: {ref})" if ref else ""
        console.print(f"[bold]{tool_name}[/bold]{ref_suffix}", markup=True, highlight=False)
        console.print(f"  status: {status_value}", markup=False, highlight=False)
        error = result.get("error")
        if error:
            console.print(f"  error: {error}", markup=False, highlight=False)
        content = result.get("content")
        if content is None or content == "":
            continue
        if isinstance(content, str):
            console.print(content, markup=False, highlight=False)
        else:
            print_json(content)


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

    _render_servers(response.get("servers", []))


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

    payload = response.get("server")
    if isinstance(payload, Mapping):
        _render_server(payload)
    else:
        console.print("(no server payload)")


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

    if response.get("status") and response.get("status") != "connected":
        console.print(f"Server [bold]{server}[/bold] is not connected ({response.get('status')}).")
        auth_url = response.get("gumloop_auth_url")
        if auth_url:
            console.print(f"Connect here: {auth_url}")
        return

    _render_tools(response.get("tools", []))


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

    _render_call_result(response)
