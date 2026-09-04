from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from rich.markup import escape as escape_markup

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import Evaluation

evaluations_app = typer.Typer(
    help="Create organization evaluations, choose which agents they grade, and run them over past sessions.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

_ORGANIZATION_OPTION = typer.Option(
    "--organization", help="Organization id. Defaults to the organization you belong to."
)
_JSON_OPTION = typer.Option("--json", help="Print the raw SDK response as JSON.")


def _resolve_organization_id(client: Gumloop, organization_id: str | None) -> str:
    if organization_id:
        return organization_id
    organizations = client.organizations.list().organizations
    if not organizations:
        raise GumloopError("You are not a member of an organization. Pass --organization explicitly.")
    return organizations[0].id


def _resolve_config(config_json: str | None, config_file: str | None) -> dict[str, Any] | None:
    if config_json is not None and config_file is not None:
        raise GumloopError("Pass at most one of --config-json or --config-file.")
    if config_json is None and config_file is None:
        return None
    if config_file is not None:
        try:
            raw = Path(config_file).expanduser().read_text(encoding="utf-8")
        except OSError as error:
            raise GumloopError(f"Could not read {config_file}: {error.strerror or error}") from error
    else:
        raw = config_json or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GumloopError(f"Could not parse config JSON: {error.msg} at line {error.lineno}.") from error
    if not isinstance(parsed, dict):
        raise GumloopError("Config JSON must be an object at the top level.")
    return parsed


def _print_evaluation(evaluation: Evaluation) -> None:
    console.print(f"[bold]Evaluation {escape_markup(evaluation.id)}[/bold]", markup=True, highlight=False)
    summary = evaluation.run_summary
    rows = (
        ("name", evaluation.name),
        ("description", evaluation.description),
        ("enabled", evaluation.enabled),
        ("organization_id", evaluation.organization_id),
        ("covered_agents", evaluation.covered_agent_count),
        ("targets", ", ".join(f"{t.type}:{t.id}" if t.id else t.type for t in evaluation.targets) or "none"),
        ("criteria", len(evaluation.config.criteria or [])),
        ("graded", summary.get("graded_count")),
        ("success_rate", _percent(summary.get("success_rate"))),
        ("created_at", evaluation.created_at),
        ("updated_at", evaluation.updated_at),
    )
    for field, value in rows:
        if value not in (None, ""):
            console.print(f"  {field}: {value}", markup=False, highlight=False)


def _percent(value: Any) -> str | None:
    return f"{round(value * 100)}%" if isinstance(value, (int, float)) else None


@evaluations_app.command(
    "list",
    epilog="Examples:\n  gumloop evaluations list\n  gumloop evaluations list --organization org_abc --json",
)
def list_evaluations(
    ctx: typer.Context,
    organization_id: Annotated[str | None, _ORGANIZATION_OPTION] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum number of evaluations to return.")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor", help="Pagination cursor from a previous list call.")] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List an organization's evaluations."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.evaluations.list(
                _resolve_organization_id(client, organization_id), page_size=limit, cursor=cursor
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.evaluations:
        console.print("No evaluations found.")
    else:
        console.print("ID", "NAME", "ENABLED", "AGENTS", "GRADED", "SUCCESS", sep="\t", soft_wrap=True)
        for evaluation in response.evaluations:
            console.print(
                evaluation.id,
                evaluation.name,
                "yes" if evaluation.enabled else "no",
                evaluation.covered_agent_count,
                evaluation.run_summary.get("graded_count", 0),
                _percent(evaluation.run_summary.get("success_rate")) or "-",
                sep="\t",
                soft_wrap=True,
                markup=False,
                highlight=False,
            )

    if response.next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(response.next_cursor)}")


@evaluations_app.command("get", epilog="Example:\n  gumloop evaluations get eval_abc --json")
def get_evaluation(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id to retrieve.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Show one evaluation: rubric size, targets, coverage, and results so far."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.evaluations.retrieve(evaluation_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_evaluation(response.evaluation)


@evaluations_app.command(
    "create",
    epilog=(
        "Examples:\n"
        "  gumloop evaluations create --name 'Support tone'\n"
        "  gumloop evaluations create --name 'Refund policy' --config-file rubric.json\n"
        "\n"
        "A new evaluation starts disabled. Add targets with 'gumloop evaluations targets',\n"
        "then turn it on with 'gumloop evaluations update EVAL_ID --enable'."
    ),
)
def create_evaluation(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name", help="Evaluation name, unique within the organization.")],
    description: Annotated[str | None, typer.Option("--description", help="Optional description.")] = None,
    organization_id: Annotated[str | None, _ORGANIZATION_OPTION] = None,
    config_json: Annotated[
        str | None,
        typer.Option("--config-json", help="Inline JSON rubric (criteria, tags, data_points, model_name, ...)."),
    ] = None,
    config_file: Annotated[
        str | None,
        typer.Option("--config-file", help="Path to a JSON file containing the rubric."),
    ] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Create an organization evaluation."""
    cli: CliContext = ctx.obj
    try:
        config = _resolve_config(config_json, config_file)
        response = cli.call_with_refresh(
            lambda client: client.evaluations.create(
                organization_id=_resolve_organization_id(client, organization_id),
                name=name,
                description=description,
                config=config,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Created evaluation[/green] {escape_markup(response.evaluation.id)}")
    console.print(f"  Name: {response.evaluation.name}", markup=False, highlight=False)


@evaluations_app.command(
    "update",
    epilog=(
        "Examples:\n"
        "  gumloop evaluations update eval_abc --enable\n"
        "  gumloop evaluations update eval_abc --name 'Support tone v2' --config-file rubric.json"
    ),
)
def update_evaluation(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id to update.")],
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="New description ('' clears it).")] = None,
    enabled: Annotated[
        bool | None,
        typer.Option("--enable/--disable", help="Turn the evaluation on or off."),
    ] = None,
    config_json: Annotated[
        str | None,
        typer.Option("--config-json", help="Inline JSON rubric fields to change; lists replace wholesale."),
    ] = None,
    config_file: Annotated[
        str | None,
        typer.Option("--config-file", help="Path to a JSON file with rubric fields to change."),
    ] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Change an evaluation's name, description, rubric, or on/off state."""
    cli: CliContext = ctx.obj
    try:
        config = _resolve_config(config_json, config_file)
        if name is None and description is None and enabled is None and config is None:
            raise GumloopError("Pass at least one of --name, --description, --enable/--disable, or a config.")
        response = cli.call_with_refresh(
            lambda client: client.evaluations.update(
                evaluation_id, name=name, description=description, enabled=enabled, config=config
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_evaluation(response.evaluation)


@evaluations_app.command("delete", epilog="Example:\n  gumloop evaluations delete eval_abc")
def delete_evaluation(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id to delete.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Delete an evaluation. Past results stay attached to their sessions."""
    cli: CliContext = ctx.obj
    try:
        cli.call_with_refresh(lambda client: client.evaluations.delete(evaluation_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json({"deleted": True, "id": evaluation_id})
        return
    console.print(f"[green]Deleted[/green] evaluation {escape_markup(evaluation_id)}")


@evaluations_app.command(
    "targets",
    epilog=(
        "Examples:\n"
        "  gumloop evaluations targets eval_abc --whole-organization\n"
        "  gumloop evaluations targets eval_abc --team team_1 --team team_2 --agent agent_9\n"
        "  gumloop evaluations targets eval_abc --user user_5\n"
        "\n"
        "Replaces the full target set each time. --user covers a member's personal agents."
    ),
)
def set_targets(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id whose targets to replace.")],
    whole_organization: Annotated[
        bool, typer.Option("--whole-organization", help="Grade every agent in the organization.")
    ] = False,
    team_ids: Annotated[list[str] | None, typer.Option("--team", help="Team id (repeatable).")] = None,
    user_ids: Annotated[list[str] | None, typer.Option("--user", help="Member user id (repeatable).")] = None,
    agent_ids: Annotated[list[str] | None, typer.Option("--agent", help="Agent id (repeatable).")] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Choose which agents the evaluation grades."""
    cli: CliContext = ctx.obj
    targets: list[dict[str, Any]] = []
    if whole_organization:
        targets.append({"type": "organization"})
    targets += [{"type": "team", "id": team_id} for team_id in team_ids or []]
    targets += [{"type": "user", "id": user_id} for user_id in user_ids or []]
    targets += [{"type": "agent", "id": agent_id} for agent_id in agent_ids or []]
    try:
        response = cli.call_with_refresh(lambda client: client.evaluations.set_targets(evaluation_id, targets))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[green]Updated targets[/green] for {escape_markup(evaluation_id)}")
    for target in response.targets:
        console.print(f"  {target.type}: {target.id or ''}", markup=False, highlight=False)
    console.print(f"  covered agents: {response.covered_agent_count}")
    if not response.enabled:
        console.print("  enabled: no")


@evaluations_app.command(
    "run",
    epilog=(
        "Examples:\n"
        "  gumloop evaluations run eval_abc session_1 session_2\n"
        "  gumloop evaluations run eval_abc session_1 --dry-run"
    ),
)
def run_evaluation(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id to run.")],
    session_ids: Annotated[list[str], typer.Argument(help="Session ids to grade (up to 200).")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report the credit cost and skipped sessions without queuing.")
    ] = False,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Grade past sessions with this evaluation. Runs are queued; poll results with 'evaluations results'."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.evaluations.run(evaluation_id, session_ids, dry_run=dry_run)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    verb = "Would queue" if response.dry_run else "Queued"
    console.print(f"[green]{verb}[/green] {len(response.results)} session(s) for {response.credit_cost} credit(s)")
    for result in response.results:
        console.print(f"  {result.session_id}\t{result.status}\t{result.id or ''}", markup=False, highlight=False)
    for skipped in response.skipped:
        console.print(f"  {skipped.session_id}\tskipped: {skipped.reason}", markup=False, highlight=False)


@evaluations_app.command(
    "results",
    epilog=(
        "Examples:\n"
        "  gumloop evaluations results eval_abc --grade needs_attention\n"
        "  gumloop evaluations results eval_abc --agent agent_9 --since 2026-09-01T00:00:00Z --json"
    ),
)
def list_results(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id whose results to list.")],
    agent_id: Annotated[str | None, typer.Option("--agent", help="Only results for this agent.")] = None,
    session_id: Annotated[str | None, typer.Option("--session", help="Only results for this session.")] = None,
    grade: Annotated[
        str | None, typer.Option("--grade", help="Filter by grade (pass, needs_review, needs_attention).")
    ] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="Filter by status (queued, in_progress, completed, failed).")
    ] = None,
    since: Annotated[str | None, typer.Option("--since", help="Created at or after this RFC 3339 time.")] = None,
    until: Annotated[str | None, typer.Option("--until", help="Created before this RFC 3339 time.")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum number of results to return.")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor", help="Pagination cursor from a previous call.")] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List graded sessions for an evaluation."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.evaluations.list_results(
                evaluation_id,
                agent_id=agent_id,
                session_id=session_id,
                grade=grade,
                status=status,
                created_after=since,
                created_before=until,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.results:
        console.print("No results found.")
    else:
        console.print("ID", "SESSION", "AGENT", "STATUS", "GRADE", "CREATED", sep="\t", soft_wrap=True)
        for result in response.results:
            console.print(
                result.id,
                result.session_id,
                result.agent_id,
                result.status,
                result.grade or (result.error_code or ""),
                result.created_at or "",
                sep="\t",
                soft_wrap=True,
                markup=False,
                highlight=False,
            )

    if response.next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(response.next_cursor)}")


@evaluations_app.command("options", epilog="Example:\n  gumloop evaluations options | jq .grades")
def get_options(ctx: typer.Context) -> None:
    """Print the allowed values for rubric fields and result filters, plus size limits, as JSON."""
    cli: CliContext = ctx.obj
    try:
        options = cli.call_with_refresh(lambda client: client.evaluations.options())
    except GumloopError as error:
        exit_with_error(error, json_output=True)
    print_json(options)


@evaluations_app.command("metrics", epilog="Example:\n  gumloop evaluations metrics eval_abc --days 7")
def get_metrics(
    ctx: typer.Context,
    evaluation_id: Annotated[str, typer.Argument(help="Evaluation id.")],
    days: Annotated[int | None, typer.Option("--days", help="Window in days (1-365, default 30).")] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Grade counts for an evaluation over a time window."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.evaluations.metrics(evaluation_id, days=days))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    console.print(f"[bold]Last {response.days} days[/bold]", markup=True, highlight=False)
    if not response.grades:
        console.print("  No graded sessions.")
    for grade, count in sorted(response.grades.items()):
        console.print(f"  {grade}: {count}", markup=False, highlight=False)
