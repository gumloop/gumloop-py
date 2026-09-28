from __future__ import annotations

from pathlib import Path
from typing import Annotated
from typing import Any

import typer
from rich.markup import escape as escape_markup

from gumloop import Gumloop
from gumloop import GumloopError
from gumloop._http import UploadFile
from gumloop.brain_sync import BrainSyncPlan
from gumloop.brain_sync import LocalFile
from gumloop.brain_sync import scan_directory
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.errors import APIStatusError
from gumloop.types import BrainFile
from gumloop.types import BrainFileRejection
from gumloop.types import BrainSourceEstimate

brain_app = typer.Typer(help="Search and manage your Company Brain.", no_args_is_help=True, rich_markup_mode="rich")
sources_app = typer.Typer(help="Manage Brain sources.", no_args_is_help=True, rich_markup_mode="rich")
files_app = typer.Typer(help="Manage files in a file-upload source.", no_args_is_help=True, rich_markup_mode="rich")
brain_app.add_typer(sources_app, name="sources")
brain_app.add_typer(files_app, name="files")

UPLOAD_BATCH_SIZE = 25

_JSON_OPTION = typer.Option("--json", help="Print the raw SDK response as JSON.")


@brain_app.command(
    "search",
    epilog=(
        "Examples:\n"
        '  gumloop brain search "onboarding process"\n'
        '  gumloop brain search "pricing" --limit 5 --source notion --json'
    ),
)
def search_brain(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query.")],
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum number of results to return (1-50)."),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="Filter by source type (repeatable), e.g. notion, google_drive, slack."),
    ] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Search indexed Company Brain sources."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.brain.search(query, limit=limit, source_type=source or None)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.results:
        console.print("No results found.")
        return

    console.print("SCORE", "SOURCE", "TITLE", "URL", sep="\t", soft_wrap=True)
    for result in response.results:
        console.print(
            "" if result.score is None else f"{result.score:.3f}",
            result.source or "",
            result.title or "",
            result.url or "",
            sep="\t",
            soft_wrap=True,
        )


@sources_app.command(
    "list", epilog="Examples:\n  gumloop brain sources list\n  gumloop brain sources list --scope team --json"
)
def list_sources(
    ctx: typer.Context,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Filter by scope: personal, team, or organization."),
    ] = None,
    source_type: Annotated[
        str | None,
        typer.Option("--source-type", help="Filter by source type, e.g. direct_file_uploads, notion."),
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum number of sources to return.")] = None,
    cursor: Annotated[
        str | None,
        typer.Option("--cursor", help="Pagination cursor returned by a previous list call."),
    ] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List Brain sources you can see."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.brain.list_sources(
                scope=scope,
                source_type=source_type,
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
    if not response.sources:
        console.print("No sources found.")
        return
    console.print("ID", "NAME", "TYPE", "SCOPE", "STATUS", sep="\t", soft_wrap=True)
    for item in response.sources:
        console.print(item.id, item.name, item.source_type, item.scope, item.status, sep="\t", soft_wrap=True)
    if response.next_cursor:
        console.print(f"\nMore results: --cursor {response.next_cursor}")


@sources_app.command(
    "create",
    epilog=(
        "Examples:\n"
        '  gumloop brain sources create "Engineering docs"\n'
        '  gumloop brain sources create "Team runbooks" --team-id <team_id>\n'
        '  gumloop brain sources create "Company policies" --scope organization --require-approval'
    ),
)
def create_source(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Display name of the new source.")],
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="personal (default), team (with --team-id), or organization."),
    ] = None,
    require_approval: Annotated[
        bool,
        typer.Option("--require-approval", help="Create as a draft and estimate credits before indexing."),
    ] = False,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Create a file-upload Brain source."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: _create_source(client, cli, name, scope=scope, require_approval=require_approval)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    item = response.source
    console.print(f"[green]Created source[/green] {escape_markup(item.id)} ({item.scope}, {item.status})")


@sources_app.command("get")
def get_source(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Show one Brain source."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.brain.get_source(source_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    item = response.source
    for label, value in (
        ("ID", item.id),
        ("Name", item.name),
        ("Type", item.source_type),
        ("Scope", item.scope + (f" ({item.team_id})" if item.team_id else "")),
        ("Status", item.status),
        ("Created", item.created_at or ""),
    ):
        console.print(f"{label}:\t{escape_markup(str(value))}", soft_wrap=True)


@sources_app.command("delete")
def delete_source(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Delete a Brain source and every file in it."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.brain.delete_source(source_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Deleted source[/green] {escape_markup(source_id)}")


@sources_app.command("estimate")
def get_estimate(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Show the credit estimate for a draft source."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.brain.get_estimate(source_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_estimate(response.status, response.estimate)


@sources_app.command("approve")
def approve_source(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Approve a draft source so its files are indexed and billed."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.brain.approve_source(source_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Approved source[/green] {escape_markup(source_id)} ({response.source.status})")


@files_app.command("list")
def list_files(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum number of files to return.")] = None,
    cursor: Annotated[
        str | None,
        typer.Option("--cursor", help="Pagination cursor returned by a previous list call."),
    ] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List files in a source."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.brain.list_files(source_id, page_size=limit, cursor=cursor)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if not response.files:
        console.print("No files found.")
        return
    console.print("ID", "NAME", "SIZE", "STATUS", "SHA256", sep="\t", soft_wrap=True)
    for item in response.files:
        console.print(
            item.id,
            item.file_name,
            "" if item.size_bytes is None else str(item.size_bytes),
            item.status + (f" ({item.error})" if item.error else ""),
            (item.sha256 or "")[:12],
            sep="\t",
            soft_wrap=True,
        )
    if response.next_cursor:
        console.print(f"\nMore results: --cursor {response.next_cursor}")


@files_app.command(
    "upload",
    epilog="Examples:\n  gumloop brain files upload <source_id> ./handbook.pdf ./policies/*.md",
)
def upload_files(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    paths: Annotated[
        list[Path],
        typer.Argument(help="Files to upload (at most 25 per call).", exists=True, dir_okay=False, readable=True),
    ],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Upload files to a source. Indexing starts on its own."""
    cli: CliContext = ctx.obj
    try:
        if len(paths) > UPLOAD_BATCH_SIZE:
            raise GumloopError(f"At most {UPLOAD_BATCH_SIZE} files per upload.")
        payload: list[UploadFile] = [(path.expanduser().name, _read_file(path.expanduser())) for path in paths]
        response = cli.call_with_refresh(lambda client: client.brain.upload_files(source_id, payload))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    for item in response.files:
        console.print(f"[green]Uploaded[/green] {escape_markup(item.file_name)} ({item.id})")
    _print_rejections(response.rejected)


@files_app.command("delete")
def delete_file(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source id.")],
    file_id: Annotated[str, typer.Argument(help="File id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Remove a file from a source and from search."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.brain.delete_file(source_id, file_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Deleted file[/green] {escape_markup(file_id)}")


@brain_app.command(
    "sync",
    epilog=(
        "Examples:\n"
        "  gumloop brain sync ./docs --source <source_id>\n"
        '  gumloop brain sync ./docs --create "Engineering docs" --prune\n'
        '  gumloop brain sync ./policies --create "Policies" --scope organization --require-approval --approve'
    ),
)
def sync_directory(
    ctx: typer.Context,
    directory: Annotated[
        Path,
        typer.Argument(help="Directory to mirror into the source.", exists=True, file_okay=False, readable=True),
    ],
    source_id: Annotated[str | None, typer.Option("--source", help="Existing source id to sync into.")] = None,
    create: Annotated[
        str | None,
        typer.Option("--create", help="Create a new source with this name instead of --source."),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option("--scope", help="Scope for --create: personal (default), team (with --team-id), or organization."),
    ] = None,
    require_approval: Annotated[
        bool,
        typer.Option("--require-approval", help="With --create: start as a draft that estimates credits first."),
    ] = False,
    prune: Annotated[
        bool,
        typer.Option("--prune", help="Delete remote files that no longer exist locally."),
    ] = False,
    approve: Annotated[
        bool,
        typer.Option("--approve", help="Approve a draft source once the estimate is ready."),
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan without changing anything.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the sync result as JSON.")] = False,
) -> None:
    """Mirror a local directory into a file-upload source. Unchanged files (same name and sha256) are skipped."""
    cli: CliContext = ctx.obj
    if (source_id is None) == (create is None):
        raise typer.BadParameter("Pass exactly one of --source or --create.")
    try:
        result = cli.call_with_refresh(
            lambda client: _sync(
                client,
                cli,
                directory.expanduser(),
                source_id=source_id,
                create=create,
                scope=scope,
                require_approval=require_approval,
                prune=prune,
                approve=approve,
                dry_run=dry_run,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(result)
        return
    console.print(f"Source {escape_markup(result['source_id'] or create or '')} ({result['status']})")
    console.print(
        f"{len(result['uploaded'])} uploaded, {len(result['replaced'])} replaced, "
        f"{len(result['pruned'])} pruned, {result['unchanged']} unchanged" + (" (dry run)" if dry_run else "")
    )
    _print_rejections([BrainFileRejection.model_validate(item) for item in result["rejected"]])
    if result["status"] == "draft":
        estimate = result["estimate"]
        _print_estimate("draft", BrainSourceEstimate.model_validate(estimate) if estimate else None)


def _create_source(client: Gumloop, cli: CliContext, name: str, *, scope: str | None, require_approval: bool):
    team_id = cli.effective_team_id
    if team_id and scope is None:
        scope = "team"
    return client.brain.create_source(name, scope=scope, team_id=team_id, require_approval=require_approval)


def _read_file(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise GumloopError(f"Could not read {path}: {error.strerror or error}") from error


def _all_remote_files(client: Gumloop, source_id: str) -> list[BrainFile]:
    files: list[BrainFile] = []
    cursor = None
    while True:
        page = client.brain.list_files(source_id, page_size=100, cursor=cursor)
        files.extend(page.files)
        cursor = page.next_cursor
        if not cursor:
            return files


def _sync(
    client: Gumloop,
    cli: CliContext,
    directory: Path,
    *,
    source_id: str | None,
    create: str | None,
    scope: str | None,
    require_approval: bool,
    prune: bool,
    approve: bool,
    dry_run: bool,
) -> dict[str, Any]:
    local = scan_directory(directory)
    remote: list[BrainFile] = []
    if source_id is not None:
        source = client.brain.get_source(source_id).source
        remote = _all_remote_files(client, source_id)
    elif dry_run:
        source = None
    else:
        source = _create_source(client, cli, create or "", scope=scope, require_approval=require_approval).source
        source_id = source.id

    plan = BrainSyncPlan.build(local, remote)
    replaced_names = {item.file_name for item in plan.replace}
    result: dict[str, Any] = {
        "source_id": source_id,
        "status": source.status if source else "new",
        "uploaded": [item.name for item in plan.upload if item.name not in replaced_names],
        "replaced": sorted(replaced_names),
        "pruned": [item.file_name for item in plan.prune] if prune else [],
        "unchanged": len(plan.unchanged),
        "rejected": [],
        "estimate": None,
        "dry_run": dry_run,
    }
    if dry_run or source_id is None:
        return result

    for remote_file in plan.replace + (plan.prune if prune else []):
        client.brain.delete_file(source_id, remote_file.id)
    for batch in _batches(plan.upload, UPLOAD_BATCH_SIZE):
        payload: list[UploadFile] = [(item.name, _read_file(item.path)) for item in batch]
        try:
            rejected = client.brain.upload_files(source_id, payload).rejected
        except APIStatusError as error:
            if error.code != "no_files_accepted":
                raise
            rejected = [BrainFileRejection.model_validate(item) for item in error.details.get("rejected", [])]
        result["rejected"].extend(item.model_dump() for item in rejected)
    rejected_names = {item["file_name"] for item in result["rejected"]}
    result["uploaded"] = [name for name in result["uploaded"] if name not in rejected_names]

    if source is not None and source.status == "draft":
        if approve:
            result["status"] = client.brain.approve_source(source_id).source.status
        else:
            estimate = client.brain.get_estimate(source_id).estimate
            result["estimate"] = estimate.model_dump() if estimate else None
    return result


def _batches(items: list[LocalFile], size: int) -> list[list[LocalFile]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _print_rejections(rejected: list[BrainFileRejection]) -> None:
    for item in rejected:
        console.print(f"[yellow]Skipped[/yellow] {escape_markup(item.file_name)}: {escape_markup(item.error)}")


def _print_estimate(status: str, estimate: BrainSourceEstimate | None) -> None:
    if estimate is None:
        console.print(f"Source is {status}; no estimate yet.")
        return
    console.print(
        f"Estimate ({estimate.status}): {estimate.estimated_credits} credits for "
        f"{estimate.document_count} files ({estimate.estimated_tokens} tokens)."
    )
    if status == "draft":
        console.print("Approve with: gumloop brain sources approve <source_id>")
