from __future__ import annotations

from typing import Annotated

import typer
from rich.markup import escape as escape_markup

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import MemoryCard
from gumloop.types import MemoryCardRef
from gumloop.types import MemoryCardType
from gumloop.types import MemoryFact
from gumloop.types import MemoryRuleSet
from gumloop.types import MemorySync

memory_app = typer.Typer(help="Read and edit what Gumloop remembers about you.", no_args_is_help=True)
cards_app = typer.Typer(help="Browse and edit memory cards.", no_args_is_help=True)
facts_app = typer.Typer(help="Browse and edit memory facts.", no_args_is_help=True)
rules_app = typer.Typer(help="Read and state your tone and design rules.", no_args_is_help=True)
revisions_app = typer.Typer(help="Review and undo memory changes.", no_args_is_help=True)
sync_app = typer.Typer(help="Check or start a memory sync.", no_args_is_help=True)
memory_app.add_typer(cards_app, name="cards")
memory_app.add_typer(facts_app, name="facts")
memory_app.add_typer(rules_app, name="rules")
memory_app.add_typer(revisions_app, name="revisions")
memory_app.add_typer(sync_app, name="sync")

_JSON_OPTION = typer.Option("--json", help="Print the raw SDK response as JSON.")
_LIMIT_OPTION = typer.Option("--limit", help="Maximum number of rows to return (1-100).")
_CURSOR_OPTION = typer.Option("--cursor", help="Pagination cursor returned by a previous list call.")
_TYPE_ARGUMENT = typer.Argument(help="Card type, e.g. person, project, profile, tone.")
_ENTITY_KEY_ARGUMENT = typer.Argument(
    help="Entity key (email, slug or agent id); omit for profile, note, tone, design."
)


def _label(card_type: MemoryCardType | str) -> str:
    return card_type.value if isinstance(card_type, MemoryCardType) else card_type


def _card_name(card: MemoryCard | MemoryCardRef | None) -> str:
    if card is None:
        return ""
    name = card.name or card.entity_key
    return f"{_label(card.type)}:{name}" if name else _label(card.type)


def _print(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _print_card(card: MemoryCard) -> None:
    _print(
        f"{_label(card.type)}: {card.name or card.entity_key or ''}"
        + (" (archived)" if card.status == "archived" else "")
    )
    if card.summary:
        _print(card.summary)
    for name, value in card.row_facts.items():
        _print(f"  {name}: {value}")


def _print_fact_rows(facts: list[MemoryFact]) -> None:
    console.print("ID", "CARD", "KIND", "PINNED", "TEXT", sep="\t", soft_wrap=True)
    for fact in facts:
        console.print(
            fact.id,
            _card_name(fact.card),
            fact.kind,
            "yes" if fact.pinned else "no",
            fact.text,
            sep="\t",
            soft_wrap=True,
            markup=False,
            highlight=False,
        )


def _print_fact(fact: MemoryFact) -> None:
    for label, value in (
        ("ID", fact.id),
        ("Card", _card_name(fact.card)),
        ("Kind", fact.kind),
        ("Text", fact.text),
        ("Origin", fact.origin),
        ("Status", fact.status),
        ("Pinned", "yes" if fact.pinned else "no"),
        ("Always in prompt", "yes" if fact.always_in_prompt else "no"),
    ):
        _print(f"{label}:\t{value}")


def _print_sync(sync: MemorySync) -> None:
    line = f"Sync: {sync.status}" + (f" ({sync.stage})" if sync.stage else "")
    if sync.facts_written is not None:
        line += f", {sync.facts_written} facts written"
    _print(line)
    for stage in sync.failed_stages:
        _print(f"  failed: {stage}")


def _print_rule_set(name: str, rule_set: MemoryRuleSet) -> None:
    _print(f"{name}:" + (" (your own guide)" if rule_set.guide_pinned else ""))
    if rule_set.guide:
        _print(rule_set.guide)
    elif not rule_set.rules:
        _print("  (nothing yet)")
    for rule in rule_set.rules:
        _print(f"  - {rule.text} ({rule.id})")


def _print_next_cursor(next_cursor: str | None) -> None:
    if next_cursor:
        console.print(f"\n[dim]Next cursor:[/dim] {escape_markup(next_cursor)}")


@memory_app.command("overview", epilog="Example:\n  gumloop memory overview --json")
def overview(ctx: typer.Context, json_output: Annotated[bool, _JSON_OPTION] = False) -> None:
    """Show your memory summary, card counts and sync status."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.overview())
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if response.summary:
        _print(response.summary)
    for card_type, count in sorted(response.card_counts.items()):
        _print(f"  {card_type}: {count}")
    _print_sync(response.sync)


@memory_app.command("query", epilog="Example:\n  gumloop memory query --type project --entity-key launch --json")
def query(
    ctx: typer.Context,
    card_type: Annotated[MemoryCardType | None, typer.Option("--type", help="Filter by card type.")] = None,
    entity_key: Annotated[str | None, typer.Option("--entity-key", help="Read one entity's card.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print cards and facts as JSON.")] = False,
) -> None:
    """Read all cards with their facts, cards of one type, or one card by type and key."""
    cli: CliContext = ctx.obj
    try:
        if entity_key is not None and card_type is None:
            raise GumloopError("Pass --type with --entity-key.")
        response = cli.call_with_refresh(lambda client: client.memory.query(type=card_type, entity_key=entity_key))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if not response.cards:
        console.print("No memory cards found.")
    for card in response.cards:
        _print_card(card)
        for fact in card.facts:
            _print(f"  {fact.kind}: {fact.text}")


@cards_app.command(
    "list",
    epilog=(
        "Examples:\n"
        "  gumloop memory cards list --type person --sort weight\n"
        "  gumloop memory cards list --status archived --json"
    ),
)
def list_cards(
    ctx: typer.Context,
    card_type: Annotated[
        list[MemoryCardType] | None, typer.Option("--type", help="Filter by card type (repeatable).")
    ] = None,
    status: Annotated[
        list[str] | None, typer.Option("--status", help="active (default) or archived (repeatable).")
    ] = None,
    search: Annotated[str | None, typer.Option("--search", help="Match card names and keys.")] = None,
    sort: Annotated[str | None, typer.Option("--sort", help="weight, updated or name.")] = None,
    limit: Annotated[int | None, _LIMIT_OPTION] = None,
    cursor: Annotated[str | None, _CURSOR_OPTION] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List memory cards without their facts."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.memory.list_cards(
                type=card_type, status=status, search=search, sort=sort, page_size=limit, cursor=cursor
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if not response.data:
        console.print("No memory cards found.")
    else:
        console.print("TYPE", "KEY", "NAME", "STATUS", "UPDATED", sep="\t", soft_wrap=True)
        for card in response.data:
            console.print(
                _label(card.type),
                card.entity_key or "",
                card.name or "",
                card.status,
                card.updated_at or "",
                sep="\t",
                soft_wrap=True,
                markup=False,
                highlight=False,
            )
    _print_next_cursor(response.next_cursor)


@cards_app.command(
    "get", epilog="Examples:\n  gumloop memory cards get person ann@acme.com\n  gumloop memory cards get profile"
)
def get_card(
    ctx: typer.Context,
    card_type: Annotated[str, _TYPE_ARGUMENT],
    entity_key: Annotated[str | None, _ENTITY_KEY_ARGUMENT] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Show one card with its facts."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.get_card(card_type, entity_key))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if response.card is None:
        console.print(f"Nothing remembered for {escape_markup(card_type)} yet.")
        return
    _print_card(response.card)
    for fact in response.facts:
        _print(f"  {fact.kind}: {fact.text} ({fact.id})")


@cards_app.command(
    "update",
    epilog=(
        "Examples:\n"
        '  gumloop memory cards update project launch --name "Launch 2026"\n'
        '  gumloop memory cards update tone --summary "Short, direct, no filler."\n'
        '  gumloop memory cards update person ann@acme.com --summary "" --status archived'
    ),
)
def update_card(
    ctx: typer.Context,
    card_type: Annotated[str, _TYPE_ARGUMENT],
    entity_key: Annotated[str | None, _ENTITY_KEY_ARGUMENT] = None,
    name: Annotated[str | None, typer.Option("--name", help="Rename the card.")] = None,
    summary: Annotated[
        str | None, typer.Option("--summary", help='Write the summary in your own words; "" clears it.')
    ] = None,
    status: Annotated[str | None, typer.Option("--status", help="active or archived.")] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Rename a card, write or clear its summary, archive or restore it."""
    cli: CliContext = ctx.obj
    try:
        if name is None and summary is None and status is None:
            raise GumloopError("Pass at least one of --name, --summary or --status.")
        response = cli.call_with_refresh(
            lambda client: client.memory.update_card(card_type, entity_key, name=name, summary=summary, status=status)
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_card(response)


@cards_app.command("regenerate", epilog="Example:\n  gumloop memory cards regenerate tone")
def regenerate_card(
    ctx: typer.Context,
    card_type: Annotated[str, _TYPE_ARGUMENT],
    entity_key: Annotated[str | None, _ENTITY_KEY_ARGUMENT] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Rewrite a card's summary from its facts (tone and design: re-curate the guide)."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.regenerate_card(card_type, entity_key))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_card(response)


@cards_app.command("delete", epilog="Example:\n  gumloop memory cards delete person ann@acme.com")
def delete_card(
    ctx: typer.Context,
    card_type: Annotated[str, _TYPE_ARGUMENT],
    entity_key: Annotated[str, typer.Argument(help="Entity key (email, slug or agent id).")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Forget a card and every fact on it."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.delete_card(card_type, entity_key))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(
        f"[green]Forgot[/green] {escape_markup(card_type)} {escape_markup(entity_key)} "
        f"({response.forgotten_facts} facts)"
    )


@facts_app.command(
    "list",
    epilog=(
        "Examples:\n"
        "  gumloop memory facts list --type person --entity-key ann@acme.com\n"
        "  gumloop memory facts list --pinned --kind title --json"
    ),
)
def list_facts(
    ctx: typer.Context,
    card_type: Annotated[MemoryCardType | None, typer.Option("--type", help="Facts on cards of this type.")] = None,
    entity_key: Annotated[str | None, typer.Option("--entity-key", help="Facts on one card (with --type).")] = None,
    kind: Annotated[list[str] | None, typer.Option("--kind", help="Fact kind (repeatable).")] = None,
    status: Annotated[
        list[str] | None, typer.Option("--status", help="active (default), stale, retired or deleted (repeatable).")
    ] = None,
    origin: Annotated[list[str] | None, typer.Option("--origin", help="Fact origin (repeatable).")] = None,
    pinned: Annotated[
        bool | None, typer.Option("--pinned/--unpinned", help="Only pinned or only unpinned facts.")
    ] = None,
    search: Annotated[str | None, typer.Option("--search", help="Match fact text.")] = None,
    limit: Annotated[int | None, _LIMIT_OPTION] = None,
    cursor: Annotated[str | None, _CURSOR_OPTION] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List facts across your memory."""
    cli: CliContext = ctx.obj
    try:
        if entity_key is not None and card_type is None:
            raise GumloopError("Pass --type with --entity-key.")
        response = cli.call_with_refresh(
            lambda client: client.memory.list_facts(
                type=card_type,
                entity_key=entity_key,
                kind=kind,
                status=status,
                origin=origin,
                pinned=pinned,
                search=search,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if not response.data:
        console.print("No memory facts found.")
    else:
        _print_fact_rows(response.data)
    _print_next_cursor(response.next_cursor)


@facts_app.command(
    "create",
    epilog=(
        "Examples:\n"
        '  gumloop memory facts create --type person --entity-key ann@acme.com --kind title "Head of operations"\n'
        '  gumloop memory facts create --type profile --kind pattern "Prefers bullet points" --always-in-prompt'
    ),
)
def create_fact(
    ctx: typer.Context,
    text: Annotated[str, typer.Argument(help="What to remember.")],
    card_type: Annotated[str, typer.Option("--type", help="Card type the fact belongs to.")],
    kind: Annotated[
        str,
        typer.Option(
            "--kind",
            help="Fact kind for the card type: title or company on a person, state on a project, pattern on profile.",
        ),
    ],
    entity_key: Annotated[
        str | None, typer.Option("--entity-key", help="Entity key; omit for singleton types.")
    ] = None,
    name: Annotated[str | None, typer.Option("--name", help="Display name for a card that does not exist yet.")] = None,
    always_in_prompt: Annotated[
        bool, typer.Option("--always-in-prompt", help="Include the fact in every agent prompt.")
    ] = False,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Remember a fact on a card."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(
            lambda client: client.memory.create_fact(
                type=card_type,
                kind=kind,
                text=text,
                entity_key=entity_key,
                name=name,
                always_in_prompt=always_in_prompt or None,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Remembered[/green] {escape_markup(response.id)}")
    _print_fact(response)


@facts_app.command("get")
def get_fact(
    ctx: typer.Context,
    fact_id: Annotated[str, typer.Argument(help="Fact id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Show one fact."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.get_fact(fact_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_fact(response)


@facts_app.command(
    "update",
    epilog=(
        "Examples:\n"
        '  gumloop memory facts update fact_abc --text "Head of operations since May"\n'
        "  gumloop memory facts update fact_abc --pinned --always-in-prompt"
    ),
)
def update_fact(
    ctx: typer.Context,
    fact_id: Annotated[str, typer.Argument(help="Fact id.")],
    text: Annotated[str | None, typer.Option("--text", help="Replace the fact text.")] = None,
    pinned: Annotated[bool | None, typer.Option("--pinned/--unpinned", help="Pin or unpin the fact.")] = None,
    always_in_prompt: Annotated[
        bool | None,
        typer.Option("--always-in-prompt/--no-always-in-prompt", help="Include in or drop from every agent prompt."),
    ] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Edit a fact's text, pin or always-in-prompt setting."""
    cli: CliContext = ctx.obj
    try:
        if text is None and pinned is None and always_in_prompt is None:
            raise GumloopError("Pass at least one of --text, --pinned/--unpinned or --always-in-prompt.")
        response = cli.call_with_refresh(
            lambda client: client.memory.update_fact(
                fact_id, text=text, pinned=pinned, always_in_prompt=always_in_prompt
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_fact(response)


@facts_app.command("delete", epilog="Example:\n  gumloop memory facts delete fact_abc")
def delete_fact(
    ctx: typer.Context,
    fact_id: Annotated[str, typer.Argument(help="Fact id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Forget a fact. Undo it from `gumloop memory revisions`."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.delete_fact(fact_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Forgot[/green] {escape_markup(response.id)}")


@rules_app.command("list", epilog="Example:\n  gumloop memory rules list --json")
def list_rules(ctx: typer.Context, json_output: Annotated[bool, _JSON_OPTION] = False) -> None:
    """Show your tone and design guides with the rules behind them."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.get_rules())
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_rule_set("tone", response.tone)
    _print_rule_set("design", response.design)


@rules_app.command(
    "create",
    epilog='Example:\n  gumloop memory rules create --type tone "Never open with a greeting."',
)
def create_rule(
    ctx: typer.Context,
    text: Annotated[str, typer.Argument(help="The rule.")],
    rule_type: Annotated[str, typer.Option("--type", help="tone or design.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """State a tone or design rule. Edit or forget it with `gumloop memory facts`."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.create_rule(rule_type, text))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Added rule[/green] {escape_markup(response.id)}")
    _print_fact(response)


@revisions_app.command(
    "list",
    epilog=(
        "Examples:\n  gumloop memory revisions list --days 7\n  gumloop memory revisions list --fact-id fact_abc --json"
    ),
)
def list_revisions(
    ctx: typer.Context,
    card_type: Annotated[MemoryCardType | None, typer.Option("--type", help="Changes to cards of this type.")] = None,
    entity_key: Annotated[str | None, typer.Option("--entity-key", help="Changes to one card (with --type).")] = None,
    fact_id: Annotated[str | None, typer.Option("--fact-id", help="Changes to one fact.")] = None,
    action: Annotated[list[str] | None, typer.Option("--action", help="Revision action (repeatable).")] = None,
    days: Annotated[int | None, typer.Option("--days", help="Only the last N days (1-365).")] = None,
    limit: Annotated[int | None, _LIMIT_OPTION] = None,
    cursor: Annotated[str | None, _CURSOR_OPTION] = None,
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """List recent changes to your memory."""
    cli: CliContext = ctx.obj
    try:
        if entity_key is not None and card_type is None:
            raise GumloopError("Pass --type with --entity-key.")
        response = cli.call_with_refresh(
            lambda client: client.memory.list_revisions(
                type=card_type,
                entity_key=entity_key,
                fact_id=fact_id,
                action=action,
                days=days,
                page_size=limit,
                cursor=cursor,
            )
        )
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    if not response.data:
        console.print("No memory revisions found.")
    else:
        console.print("ID", "ACTION", "ACTOR", "CARD", "FACT", "UNDOABLE", "CREATED", sep="\t", soft_wrap=True)
        for revision in response.data:
            console.print(
                revision.id,
                revision.action,
                revision.actor,
                _card_name(revision.card),
                revision.fact_id or "",
                "yes" if revision.undoable else "no",
                revision.created_at or "",
                sep="\t",
                soft_wrap=True,
                markup=False,
                highlight=False,
            )
    _print_next_cursor(response.next_cursor)


@revisions_app.command("undo", epilog="Example:\n  gumloop memory revisions undo rev_abc")
def undo_revision(
    ctx: typer.Context,
    revision_id: Annotated[str, typer.Argument(help="Revision id.")],
    json_output: Annotated[bool, _JSON_OPTION] = False,
) -> None:
    """Undo one fact change."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.undo_revision(revision_id))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    console.print(f"[green]Undone[/green] {escape_markup(revision_id)}")
    _print_fact(response)


@sync_app.command("status", epilog="Example:\n  gumloop memory sync status --json")
def sync_status(ctx: typer.Context, json_output: Annotated[bool, _JSON_OPTION] = False) -> None:
    """Show the last or running memory sync."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.get_sync())
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_sync(response)


@sync_app.command("start", epilog="Example:\n  gumloop memory sync start")
def sync_start(ctx: typer.Context, json_output: Annotated[bool, _JSON_OPTION] = False) -> None:
    """Start a memory sync in the background. It spends credits."""
    cli: CliContext = ctx.obj
    try:
        response = cli.call_with_refresh(lambda client: client.memory.start_sync())
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return
    _print_sync(response)
