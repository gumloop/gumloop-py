from __future__ import annotations

from typing import Annotated

import typer

from gumloop import GumloopError
from gumloop.cli.console import console
from gumloop.cli.console import print_json
from gumloop.cli.context import CliContext
from gumloop.cli.errors import exit_with_error
from gumloop.types import WikiCardType

wiki_app = typer.Typer(help="Read your personal wiki (legacy name for `gumloop memory query`).", no_args_is_help=True)


@wiki_app.command("query", epilog="Example:\n  gumloop wiki query --type project --entity-key launch --json")
def query_wiki(
    ctx: typer.Context,
    card_type: Annotated[WikiCardType | None, typer.Option("--type", help="Filter by card type.")] = None,
    entity_key: Annotated[str | None, typer.Option("--entity-key", help="Read one entity's card.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print cards and facts as JSON.")] = False,
) -> None:
    """Read all cards, cards of one type, or one card by its type and key."""
    cli: CliContext = ctx.obj
    try:
        if entity_key is not None and card_type is None:
            raise GumloopError("Pass --type with --entity-key.")
        response = cli.call_with_refresh(lambda client: client.wiki.query(type=card_type, entity_key=entity_key))
    except GumloopError as error:
        exit_with_error(error, json_output=json_output)

    if json_output:
        print_json(response)
        return

    if not response.cards:
        console.print("No wiki cards found.")
    for card in response.cards:
        label = card.type.value if isinstance(card.type, WikiCardType) else card.type
        console.print(f"{label}: {card.name or card.entity_key or ''}", markup=False, highlight=False)
        if card.summary:
            console.print(card.summary, markup=False, highlight=False)
        for name, value in card.row_facts.items():
            console.print(f"  {name}: {value}", markup=False, highlight=False)
        for fact in card.facts:
            console.print(f"  {fact.kind}: {fact.text}", markup=False, highlight=False)
