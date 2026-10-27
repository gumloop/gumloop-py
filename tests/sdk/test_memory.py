from __future__ import annotations

import asyncio
import json

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import APIStatusError
from gumloop.types import MemoryCardType
from gumloop.types import WikiCard
from tests.sdk.helpers import API_BASE

CARD = {
    "type": "person",
    "entity_key": "ann@acme.com",
    "key": "person:ann@acme.com",
    "name": "Ann",
    "summary": "Head of operations.",
    "summary_pinned": False,
    "status": "active",
    "row_facts": {"title": "Head of operations"},
    "weight": 0.8,
    "sighting_count": 12,
    "updated_at": "2026-10-27T09:00:00Z",
}

FACT = {
    "id": "fact_1",
    "kind": "title",
    "text": "Head of operations",
    "origin": "user_stated",
    "pinned": True,
    "always_in_prompt": False,
    "status": "active",
    "card": {"type": "person", "entity_key": "ann@acme.com", "name": "Ann"},
    "sources": [{"type": "user", "subject_id": "user_1"}],
}


@respx.mock
def test_list_cards_sends_csv_filters_and_parses_page(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/memory/cards").respond(
        200, json={"data": [CARD], "page_size": 20, "next_cursor": "c2", "has_more": True}
    )
    page = client.memory.list_cards(
        type=[MemoryCardType.PERSON, "project"], status="archived", sort="weight", page_size=20, cursor="c1"
    )
    assert dict(route.calls[0].request.url.params) == {
        "type": "person,project",
        "status": "archived",
        "sort": "weight",
        "page_size": "20",
        "cursor": "c1",
    }
    assert page.has_more and page.next_cursor == "c2"
    assert page.data[0].type is MemoryCardType.PERSON
    assert page.data[0].weight == 0.8


@respx.mock
def test_card_paths_quote_entity_keys_and_skip_team_scope() -> None:
    client = Gumloop(access_token="token", team_id="team_1")
    get = respx.get(f"{API_BASE}/memory/cards/person/ann%40acme.com").respond(
        200,
        json={
            "card": CARD,
            "facts": [FACT],
            "rank": {"weight": 0.8, "by_source": [{"type": "chat", "sightings": 9, "weight": 0.6}]},
        },
    )
    patch = respx.patch(f"{API_BASE}/memory/cards/tone").respond(200, json={"type": "tone", "summary": ""})
    regenerate = respx.post(f"{API_BASE}/memory/cards/design/regenerate").respond(200, json={"type": "design"})
    delete = respx.delete(f"{API_BASE}/memory/cards/project/launch").respond(200, json={"forgotten_facts": 3})

    detail = client.memory.get_card("person", "ann@acme.com")
    assert detail.card is not None and detail.card.entity_key == "ann@acme.com"
    assert detail.facts[0].card is not None and detail.facts[0].card.type is MemoryCardType.PERSON
    assert detail.rank is not None and detail.rank.by_source[0].sightings == 9
    assert "team_id" not in get.calls[0].request.url.params

    client.memory.update_card(MemoryCardType.TONE, summary="")
    assert json.loads(patch.calls[0].request.content) == {"summary": ""}
    client.memory.regenerate_card("design")
    assert regenerate.called
    assert client.memory.delete_card("project", "launch").forgotten_facts == 3
    assert "team_id" not in delete.calls[0].request.url.params


@respx.mock
def test_fact_writes_send_only_given_fields(client: Gumloop) -> None:
    create = respx.post(f"{API_BASE}/memory/facts").respond(201, json=FACT)
    update = respx.patch(f"{API_BASE}/memory/facts/fact_1").respond(200, json=FACT)
    delete = respx.delete(f"{API_BASE}/memory/facts/fact_1").respond(200, json={**FACT, "status": "deleted"})
    rule = respx.post(f"{API_BASE}/memory/rules").respond(201, json={**FACT, "kind": "rule"})

    fact = client.memory.create_fact(type="person", kind="title", text="Head of operations", entity_key="ann@acme.com")
    assert json.loads(create.calls[0].request.content) == {
        "type": "person",
        "kind": "title",
        "text": "Head of operations",
        "entity_key": "ann@acme.com",
    }
    assert fact.pinned is True
    client.memory.update_fact("fact_1", pinned=False)
    assert json.loads(update.calls[0].request.content) == {"pinned": False}
    assert client.memory.delete_fact("fact_1").status == "deleted"
    assert delete.called
    assert client.memory.create_rule("tone", "No greetings.").kind == "rule"
    assert json.loads(rule.calls[0].request.content) == {"type": "tone", "text": "No greetings."}


@respx.mock
def test_revisions_rules_sync_and_overview(client: Gumloop) -> None:
    revisions = respx.get(f"{API_BASE}/memory/revisions").respond(
        200,
        json={
            "data": [
                {
                    "id": "rev_1",
                    "action": "update",
                    "actor": "user",
                    "fact_id": "fact_1",
                    "undoable": True,
                    "before": {"text": "x"},
                },
                {"id": "rev_2", "action": "rename", "actor": "user", "fact_id": None, "undoable": False},
            ],
            "next_cursor": None,
            "has_more": False,
        },
    )
    undo = respx.post(f"{API_BASE}/memory/revisions/rev_1/undo").respond(200, json=FACT)
    respx.post(f"{API_BASE}/memory/revisions/rev_2/undo").respond(
        409, json={"error": {"code": "memory_revision_not_undoable", "message": "Card revision"}}
    )
    respx.get(f"{API_BASE}/memory/rules").respond(
        200, json={"tone": {"guide": "Short.", "guide_pinned": True, "rules": [FACT]}, "design": {"rules": []}}
    )
    respx.get(f"{API_BASE}/memory/sync").respond(200, json={"status": "completed", "facts_written": 4})
    start = respx.post(f"{API_BASE}/memory/sync").respond(202, json={"status": "queued"})
    respx.get(f"{API_BASE}/memory").respond(
        200, json={"summary": "You.", "card_counts": {"person": 2}, "sync": {"status": "never"}}
    )

    page = client.memory.list_revisions(fact_id="fact_1", action=["update", "delete"], days=7)
    assert dict(revisions.calls[0].request.url.params) == {"fact_id": "fact_1", "action": "update,delete", "days": "7"}
    assert page.data[0].before is not None and page.data[0].before.text == "x"
    assert page.data[0].undoable is True and page.data[1].undoable is False
    assert client.memory.undo_revision("rev_1").id == "fact_1"
    assert undo.called
    with pytest.raises(APIStatusError) as error:
        client.memory.undo_revision("rev_2")
    assert error.value.status_code == 409 and error.value.code == "memory_revision_not_undoable"
    rules = client.memory.get_rules()
    assert rules.tone.guide_pinned and rules.tone.rules[0].id == "fact_1" and rules.design.guide is None
    assert client.memory.get_sync().facts_written == 4
    assert client.memory.start_sync().status == "queued"
    assert start.called
    overview = client.memory.overview()
    assert overview.card_counts == {"person": 2}
    assert overview.sync.status == "never"


@respx.mock
def test_async_query_and_not_found_passthrough(async_client: AsyncGumloop) -> None:
    query = respx.post(f"{API_BASE}/memory/query").respond(200, json={"cards": [{**CARD, "facts": [FACT]}]})
    respx.get(f"{API_BASE}/memory/facts/missing").respond(
        404, json={"error": {"code": "memory_fact_not_found", "message": "No fact"}}
    )

    respx.post(f"{API_BASE}/memory/facts").respond(
        400,
        json={
            "error": {
                "code": "memory_card_key_invalid",
                "message": "That name does not form a card key.",
                "param": "entity_key",
            }
        },
    )

    cards = asyncio.run(async_client.memory.query(type=MemoryCardType.PERSON, entity_key="ann@acme.com")).cards
    assert json.loads(query.calls[0].request.content) == {"type": "person", "entity_key": "ann@acme.com"}
    assert cards[0].facts[0].sources[0].subject_id == "user_1"
    with pytest.raises(APIStatusError) as error:
        asyncio.run(async_client.memory.get_fact("missing"))
    assert error.value.status_code == 404 and error.value.code == "memory_fact_not_found"
    with pytest.raises(APIStatusError) as error:
        asyncio.run(async_client.memory.create_fact(type="organization", kind="domain", text="acme.com", name="---"))
    assert error.value.status_code == 400
    assert error.value.code == "memory_card_key_invalid" and error.value.param == "entity_key"


def test_wiki_types_are_memory_types() -> None:
    card = WikiCard.model_validate({"type": "connector", "entity_key": "slack"})
    assert card.type is MemoryCardType.CONNECTOR
    assert WikiCard.model_validate({"type": "new_backend_type"}).type == "new_backend_type"
