from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.errors import APIStatusError
from gumloop.types import WikiCardType
from gumloop.types import WikiQueryRequest
from tests.sdk.helpers import API_BASE

RESPONSE = {
    "cards": [
        {
            "type": "project",
            "entity_key": "launch",
            "name": "Launch",
            "facts": [
                {
                    "id": "fact-1",
                    "kind": "state",
                    "text": "Planning",
                    "origin": "user_stated",
                    "pinned": True,
                    "sources": [{"type": "user", "subject_id": "user-1"}],
                }
            ],
        }
    ]
}


@respx.mock
def test_wiki_query_types_and_filters(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/wiki/query").mock(return_value=httpx.Response(200, json=RESPONSE))
    response = client.wiki.query(WikiQueryRequest(type=WikiCardType.PROJECT, entity_key="launch"))
    assert json.loads(route.calls[0].request.content) == {"type": "project", "entity_key": "launch"}
    assert response.cards[0].facts[0].sources[0].subject_id == "user-1"
    assert response.cards[0].type is WikiCardType.PROJECT


@respx.mock
def test_async_wiki_query_without_filters(async_client: AsyncGumloop) -> None:
    route = respx.post(f"{API_BASE}/wiki/query").mock(return_value=httpx.Response(200, json={"cards": []}))
    assert asyncio.run(async_client.wiki.query()).cards == []
    assert json.loads(route.calls[0].request.content) == {}


@respx.mock
def test_wiki_not_found_preserves_api_error(client: Gumloop) -> None:
    respx.post(f"{API_BASE}/wiki/query").mock(
        return_value=httpx.Response(404, json={"error": {"code": "wiki_card_not_found", "message": "No card"}})
    )
    with pytest.raises(APIStatusError) as error:
        client.wiki.query(type="project", entity_key="missing")
    assert error.value.status_code == 404


@respx.mock
def test_wiki_accepts_new_response_card_types(client: Gumloop) -> None:
    respx.post(f"{API_BASE}/wiki/query").respond(200, json={"cards": [{"type": "new_backend_type"}]})
    card = client.wiki.query().cards[0]
    assert card.type == "new_backend_type"
    assert card.model_dump(mode="json")["type"] == "new_backend_type"
