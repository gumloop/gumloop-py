from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from typing import Any

import typer
from pydantic import BaseModel
from pydantic import ValidationError

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.cli.commands._args_input import resolve_json_args
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error

configuration_app = typer.Typer()
triggers_app = typer.Typer(help="Manage agent schedules, webhooks and integration triggers.", no_args_is_help=True)
knowledge_app = typer.Typer(help="Attach and scope agent Brain sources.", no_args_is_help=True)
subagents_app = typer.Typer(help="Manage which subagents an agent can call.", no_args_is_help=True)
configuration_app.add_typer(triggers_app, name="triggers")
configuration_app.add_typer(knowledge_app, name="knowledge-sources")
configuration_app.add_typer(subagents_app, name="subagents")
AgentId = Annotated[str, typer.Argument(help="Agent id.")]
TriggerId = Annotated[str, typer.Argument(help="Trigger id.")]
ArgsJson = Annotated[str | None, typer.Option("--args-json", help="Request as a JSON object.")]
ArgsFile = Annotated[str | None, typer.Option("--args-file", help="File containing request JSON.")]
Args = Annotated[str | None, typer.Option("--args", help="Use '-' to read request JSON from stdin.")]
JsonOutput = Annotated[bool, typer.Option("--json", help="Print compact JSON for scripting.")]


def _request(inline: str | None, path: str | None, stdin: str | None, json_output: bool) -> dict[str, Any]:
    try:
        return resolve_json_args(inline=inline, file_path=path, stdin_marker=stdin)
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)


def _run(ctx: typer.Context, operation: Callable[[Gumloop], BaseModel], json_output: bool) -> None:
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(operation)
    except (GumloopError, ValidationError) as error:
        exit_with_error(error, json_output=json_output)
    if json_output:
        print_json(response)
    else:
        console.print_json(data=response.model_dump(mode="json"))


@configuration_app.command("delete")
def delete_agent(ctx: typer.Context, agent_id: AgentId, json_output: JsonOutput = False) -> None:
    """Delete a custom agent. The server refuses platform agents."""
    _run(ctx, lambda client: client.agents.delete(agent_id), json_output)


@configuration_app.command("set-abilities")
def set_abilities(
    ctx: typer.Context,
    agent_id: AgentId,
    args_json: ArgsJson = None,
    args_file: ArgsFile = None,
    args: Args = None,
    json_output: JsonOutput = False,
) -> None:
    """Update native abilities and their settings; omitted abilities are unchanged."""
    request = _request(args_json, args_file, args, json_output)
    _run(ctx, lambda client: client.agents.update_abilities(agent_id, request), json_output)


@configuration_app.command("app-rules")
def list_app_rules(ctx: typer.Context, agent_id: AgentId, json_output: JsonOutput = False) -> None:
    """List the agent's connector rules."""
    _run(ctx, lambda client: client.agents.list_app_rules(agent_id), json_output)


@knowledge_app.command("list")
def list_sources(ctx: typer.Context, agent_id: AgentId, json_output: JsonOutput = False) -> None:
    """List Brain sources attached to the agent."""
    _run(ctx, lambda client: client.agents.list_knowledge_sources(agent_id), json_output)


@knowledge_app.command("attach")
def attach_source(
    ctx: typer.Context,
    agent_id: AgentId,
    connector_id: Annotated[str, typer.Argument(help="Brain source id.")],
    args_json: ArgsJson = None,
    args_file: ArgsFile = None,
    args: Args = None,
    json_output: JsonOutput = False,
) -> None:
    """Attach a Brain source. Optional JSON is the SDK KnowledgeSourceScope object."""
    config = (
        _request(args_json, args_file, args, json_output)
        if any(value is not None for value in (args_json, args_file, args))
        else None
    )
    _run(ctx, lambda client: client.agents.attach_knowledge_source(agent_id, connector_id, config=config), json_output)


@knowledge_app.command("detach")
def detach_source(
    ctx: typer.Context,
    agent_id: AgentId,
    connector_id: Annotated[str, typer.Argument(help="Brain source id.")],
    json_output: JsonOutput = False,
) -> None:
    """Detach a Brain source without deleting it."""
    _run(ctx, lambda client: client.agents.detach_knowledge_source(agent_id, connector_id), json_output)


@subagents_app.command("attach")
def attach_subagent(
    ctx: typer.Context,
    agent_id: AgentId,
    subagent_id: Annotated[str, typer.Argument(help="Agent to allow as a subagent.")],
    json_output: JsonOutput = False,
) -> None:
    """Allow delegation to an existing agent in the same workspace."""
    _run(ctx, lambda client: client.agents.attach_subagent(agent_id, subagent_id), json_output)


@subagents_app.command("detach")
def detach_subagent(
    ctx: typer.Context,
    agent_id: AgentId,
    subagent_id: Annotated[str, typer.Argument(help="Subagent to detach.")],
    json_output: JsonOutput = False,
) -> None:
    """Remove an allowed subagent."""
    _run(ctx, lambda client: client.agents.detach_subagent(agent_id, subagent_id), json_output)


@triggers_app.command("list")
def list_triggers(
    ctx: typer.Context,
    agent_id: AgentId,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    json_output: JsonOutput = False,
) -> None:
    """List triggers; webhook secrets are retrieved separately."""
    _run(ctx, lambda client: client.agents.list_triggers(agent_id, page_size=limit, cursor=cursor), json_output)


@triggers_app.command("create")
def create_trigger(
    ctx: typer.Context,
    agent_id: AgentId,
    args_json: ArgsJson = None,
    args_file: ArgsFile = None,
    args: Args = None,
    json_output: JsonOutput = False,
) -> None:
    """Create a schedule, webhook or integration from the SDK request shape."""
    request = _request(args_json, args_file, args, json_output)
    _run(ctx, lambda client: client.agents.create_trigger(agent_id, request), json_output)


@triggers_app.command("update")
def update_trigger(
    ctx: typer.Context,
    agent_id: AgentId,
    trigger_id: TriggerId,
    args_json: ArgsJson = None,
    args_file: ArgsFile = None,
    args: Args = None,
    json_output: JsonOutput = False,
) -> None:
    """Edit or enable/disable a trigger; send enabled=false to pause it."""
    request = _request(args_json, args_file, args, json_output)
    _run(ctx, lambda client: client.agents.update_trigger(agent_id, trigger_id, request), json_output)


@triggers_app.command("delete")
def delete_trigger(
    ctx: typer.Context, agent_id: AgentId, trigger_id: TriggerId, json_output: JsonOutput = False
) -> None:
    """Delete an agent trigger."""
    _run(ctx, lambda client: client.agents.delete_trigger(agent_id, trigger_id), json_output)


@triggers_app.command("webhook-url")
def webhook_url(ctx: typer.Context, agent_id: AgentId, trigger_id: TriggerId, json_output: JsonOutput = False) -> None:
    """Retrieve the webhook URL including its secret, on demand."""
    _run(ctx, lambda client: client.agents.get_trigger_webhook_url(agent_id, trigger_id), json_output)


@triggers_app.command("catalog")
def trigger_catalog(ctx: typer.Context, agent_id: AgentId, json_output: JsonOutput = False) -> None:
    """Discover supported operators, parameter schemas and required account types."""
    _run(ctx, lambda client: client.agents.list_trigger_operators(agent_id), json_output)


@triggers_app.command("get")
def get_trigger(ctx: typer.Context, agent_id: AgentId, trigger_id: TriggerId, json_output: JsonOutput = False) -> None:
    """Read current trigger status and public configuration."""
    _run(ctx, lambda client: client.agents.get_trigger(agent_id, trigger_id), json_output)


@triggers_app.command("runs")
def trigger_runs(
    ctx: typer.Context,
    agent_id: AgentId,
    trigger_id: TriggerId,
    limit: Annotated[int | None, typer.Option("--limit", min=1, max=100)] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    state: Annotated[
        list[str] | None, typer.Option("--state", help="Filter by state; repeat to include more than one.")
    ] = None,
    json_output: JsonOutput = False,
) -> None:
    """List trigger runs and credit metadata with cursor pagination."""
    _run(
        ctx,
        lambda client: client.agents.list_trigger_runs(
            agent_id, trigger_id, page_size=limit, cursor=cursor, states=state
        ),
        json_output,
    )


@triggers_app.command("stats")
def trigger_stats(
    ctx: typer.Context, agent_id: AgentId, trigger_id: TriggerId, json_output: JsonOutput = False
) -> None:
    """Read run counts and existing run/poll credit totals."""
    _run(ctx, lambda client: client.agents.get_trigger_stats(agent_id, trigger_id), json_output)


@configuration_app.command("eval-config")
def get_eval_config(ctx: typer.Context, agent_id: AgentId, json_output: JsonOutput = False) -> None:
    """Read agent evaluation configuration."""
    _run(ctx, lambda client: client.agents.get_evaluation_config(agent_id), json_output)


@configuration_app.command("set-eval-config")
def set_eval_config(
    ctx: typer.Context,
    agent_id: AgentId,
    args_json: ArgsJson = None,
    args_file: ArgsFile = None,
    args: Args = None,
    json_output: JsonOutput = False,
) -> None:
    """Update evaluation configuration; supplied lists replace existing lists."""
    request = _request(args_json, args_file, args, json_output)
    _run(ctx, lambda client: client.agents.update_evaluation_config(agent_id, request), json_output)


@configuration_app.command("eval-results")
def list_eval_results(
    ctx: typer.Context,
    agent_id: AgentId,
    grade: Annotated[str | None, typer.Option("--grade")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    created_after: Annotated[datetime | None, typer.Option("--created-after")] = None,
    created_before: Annotated[datetime | None, typer.Option("--created-before")] = None,
    session_id: Annotated[str | None, typer.Option("--session-id")] = None,
    organization_evaluation_id: Annotated[str | None, typer.Option("--organization-evaluation-id")] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    json_output: JsonOutput = False,
) -> None:
    """List evaluation results with filters and cursor pagination."""
    _run(
        ctx,
        lambda client: client.agents.list_evaluations(
            agent_id,
            grade=grade,
            status=status,
            created_after=created_after,
            created_before=created_before,
            session_id=session_id,
            organization_evaluation_id=organization_evaluation_id,
            page_size=limit,
            cursor=cursor,
        ),
        json_output,
    )


@configuration_app.command("eval-result")
def get_eval_result(
    ctx: typer.Context,
    agent_id: AgentId,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation result id.")],
    json_output: JsonOutput = False,
) -> None:
    """Read one agent evaluation result."""
    _run(ctx, lambda client: client.agents.get_evaluation(agent_id, evaluation_id), json_output)
