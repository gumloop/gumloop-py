from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import MemoryCard
from gumloop.types import MemoryCardDeleteResponse
from gumloop.types import MemoryCardListResponse
from gumloop.types import MemoryCardResponse
from gumloop.types import MemoryCardType
from gumloop.types import MemoryCardUpdateRequest
from gumloop.types import MemoryFact
from gumloop.types import MemoryFactCreateRequest
from gumloop.types import MemoryFactListResponse
from gumloop.types import MemoryFactUpdateRequest
from gumloop.types import MemoryOverviewResponse
from gumloop.types import MemoryQueryRequest
from gumloop.types import MemoryQueryResponse
from gumloop.types import MemoryRevisionListResponse
from gumloop.types import MemoryRuleCreateRequest
from gumloop.types import MemoryRulesResponse
from gumloop.types import MemorySync

CardType = MemoryCardType | str


def _card_path(card_type: CardType, entity_key: str | None, suffix: str = "") -> str:
    path = f"memory/cards/{quote(getattr(card_type, 'value', card_type), safe='')}"
    if entity_key is not None:
        path += f"/{quote(entity_key, safe='')}"
    return path + suffix


def _csv(values: Sequence[str] | str | None) -> str | None:
    if values is None:
        return None
    if isinstance(values, str):
        values = [values]
    return ",".join(getattr(value, "value", value) for value in values) or None


def _card_list_params(
    card_type: Sequence[CardType] | CardType | None,
    status: Sequence[str] | str | None,
    search: str | None,
    sort: str | None,
    page_size: int | None,
    cursor: str | None,
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": _csv(card_type),
        "status": _csv(status),
        "search": search,
        "sort": sort,
        "page_size": page_size,
        "cursor": cursor,
        **kwargs,
    }


def _fact_list_params(
    card_type: CardType | None,
    entity_key: str | None,
    kind: Sequence[str] | str | None,
    status: Sequence[str] | str | None,
    origin: Sequence[str] | str | None,
    pinned: bool | None,
    search: str | None,
    page_size: int | None,
    cursor: str | None,
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": _csv(card_type),
        "entity_key": entity_key,
        "kind": _csv(kind),
        "status": _csv(status),
        "origin": _csv(origin),
        "pinned": pinned,
        "search": search,
        "page_size": page_size,
        "cursor": cursor,
        **kwargs,
    }


def _revision_list_params(
    card_type: CardType | None,
    entity_key: str | None,
    fact_id: str | None,
    action: Sequence[str] | str | None,
    days: int | None,
    page_size: int | None,
    cursor: str | None,
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": _csv(card_type),
        "entity_key": entity_key,
        "fact_id": fact_id,
        "action": _csv(action),
        "days": days,
        "page_size": page_size,
        "cursor": cursor,
        **kwargs,
    }


class Memory:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def overview(self) -> MemoryOverviewResponse:
        return MemoryOverviewResponse.model_validate(self._client.get("memory", scoped=False))

    def query(
        self, request: MemoryQueryRequest | Mapping[str, Any] | None = None, **kwargs: Any
    ) -> MemoryQueryResponse:
        return MemoryQueryResponse.model_validate(
            self._client.post("memory/query", json=MemoryQueryRequest.build(request, **kwargs), scoped=False)
        )

    def list_cards(
        self,
        *,
        type: Sequence[CardType] | CardType | None = None,
        status: Sequence[str] | str | None = None,
        search: str | None = None,
        sort: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> MemoryCardListResponse:
        return MemoryCardListResponse.model_validate(
            self._client.get(
                "memory/cards",
                params=_card_list_params(type, status, search, sort, page_size, cursor, kwargs),
                scoped=False,
            )
        )

    def get_card(self, type: CardType, entity_key: str | None = None) -> MemoryCardResponse:
        return MemoryCardResponse.model_validate(self._client.get(_card_path(type, entity_key), scoped=False))

    def update_card(
        self,
        type: CardType,
        entity_key: str | None = None,
        *,
        name: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> MemoryCard:
        """``summary=""`` clears the summary."""
        return MemoryCard.model_validate(
            self._client.patch(
                _card_path(type, entity_key),
                json=MemoryCardUpdateRequest.build(name=name, summary=summary, status=status, **kwargs),
                scoped=False,
            )
        )

    def regenerate_card(self, type: CardType, entity_key: str | None = None) -> MemoryCard:
        return MemoryCard.model_validate(self._client.post(_card_path(type, entity_key, "/regenerate"), scoped=False))

    def delete_card(self, type: CardType, entity_key: str) -> MemoryCardDeleteResponse:
        return MemoryCardDeleteResponse.model_validate(self._client.delete(_card_path(type, entity_key), scoped=False))

    def list_facts(
        self,
        *,
        type: CardType | None = None,
        entity_key: str | None = None,
        kind: Sequence[str] | str | None = None,
        status: Sequence[str] | str | None = None,
        origin: Sequence[str] | str | None = None,
        pinned: bool | None = None,
        search: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> MemoryFactListResponse:
        return MemoryFactListResponse.model_validate(
            self._client.get(
                "memory/facts",
                params=_fact_list_params(
                    type, entity_key, kind, status, origin, pinned, search, page_size, cursor, kwargs
                ),
                scoped=False,
            )
        )

    def create_fact(
        self,
        request: MemoryFactCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> MemoryFact:
        return MemoryFact.model_validate(
            self._client.post("memory/facts", json=MemoryFactCreateRequest.build(request, **kwargs), scoped=False)
        )

    def get_fact(self, fact_id: str) -> MemoryFact:
        return MemoryFact.model_validate(self._client.get(f"memory/facts/{quote(fact_id, safe='')}", scoped=False))

    def update_fact(
        self,
        fact_id: str,
        *,
        text: str | None = None,
        pinned: bool | None = None,
        always_in_prompt: bool | None = None,
        **kwargs: Any,
    ) -> MemoryFact:
        return MemoryFact.model_validate(
            self._client.patch(
                f"memory/facts/{quote(fact_id, safe='')}",
                json=MemoryFactUpdateRequest.build(
                    text=text, pinned=pinned, always_in_prompt=always_in_prompt, **kwargs
                ),
                scoped=False,
            )
        )

    def delete_fact(self, fact_id: str) -> MemoryFact:
        return MemoryFact.model_validate(self._client.delete(f"memory/facts/{quote(fact_id, safe='')}", scoped=False))

    def get_rules(self) -> MemoryRulesResponse:
        return MemoryRulesResponse.model_validate(self._client.get("memory/rules", scoped=False))

    def create_rule(self, type: str, text: str) -> MemoryFact:
        return MemoryFact.model_validate(
            self._client.post("memory/rules", json=MemoryRuleCreateRequest.build(type=type, text=text), scoped=False)
        )

    def list_revisions(
        self,
        *,
        type: CardType | None = None,
        entity_key: str | None = None,
        fact_id: str | None = None,
        action: Sequence[str] | str | None = None,
        days: int | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> MemoryRevisionListResponse:
        return MemoryRevisionListResponse.model_validate(
            self._client.get(
                "memory/revisions",
                params=_revision_list_params(type, entity_key, fact_id, action, days, page_size, cursor, kwargs),
                scoped=False,
            )
        )

    def undo_revision(self, revision_id: str) -> MemoryFact:
        return MemoryFact.model_validate(
            self._client.post(f"memory/revisions/{quote(revision_id, safe='')}/undo", scoped=False)
        )

    def get_sync(self) -> MemorySync:
        return MemorySync.model_validate(self._client.get("memory/sync", scoped=False))

    def start_sync(self) -> MemorySync:
        """Spends the owner's credits; returns before the sync finishes."""
        return MemorySync.model_validate(self._client.post("memory/sync", scoped=False))


class AsyncMemory:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def overview(self) -> MemoryOverviewResponse:
        return MemoryOverviewResponse.model_validate(await self._client.get("memory", scoped=False))

    async def query(
        self, request: MemoryQueryRequest | Mapping[str, Any] | None = None, **kwargs: Any
    ) -> MemoryQueryResponse:
        data = await self._client.post("memory/query", json=MemoryQueryRequest.build(request, **kwargs), scoped=False)
        return MemoryQueryResponse.model_validate(data)

    async def list_cards(
        self,
        *,
        type: Sequence[CardType] | CardType | None = None,
        status: Sequence[str] | str | None = None,
        search: str | None = None,
        sort: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> MemoryCardListResponse:
        data = await self._client.get(
            "memory/cards",
            params=_card_list_params(type, status, search, sort, page_size, cursor, kwargs),
            scoped=False,
        )
        return MemoryCardListResponse.model_validate(data)

    async def get_card(self, type: CardType, entity_key: str | None = None) -> MemoryCardResponse:
        return MemoryCardResponse.model_validate(await self._client.get(_card_path(type, entity_key), scoped=False))

    async def update_card(
        self,
        type: CardType,
        entity_key: str | None = None,
        *,
        name: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> MemoryCard:
        """``summary=""`` clears the summary."""
        data = await self._client.patch(
            _card_path(type, entity_key),
            json=MemoryCardUpdateRequest.build(name=name, summary=summary, status=status, **kwargs),
            scoped=False,
        )
        return MemoryCard.model_validate(data)

    async def regenerate_card(self, type: CardType, entity_key: str | None = None) -> MemoryCard:
        data = await self._client.post(_card_path(type, entity_key, "/regenerate"), scoped=False)
        return MemoryCard.model_validate(data)

    async def delete_card(self, type: CardType, entity_key: str) -> MemoryCardDeleteResponse:
        data = await self._client.delete(_card_path(type, entity_key), scoped=False)
        return MemoryCardDeleteResponse.model_validate(data)

    async def list_facts(
        self,
        *,
        type: CardType | None = None,
        entity_key: str | None = None,
        kind: Sequence[str] | str | None = None,
        status: Sequence[str] | str | None = None,
        origin: Sequence[str] | str | None = None,
        pinned: bool | None = None,
        search: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> MemoryFactListResponse:
        data = await self._client.get(
            "memory/facts",
            params=_fact_list_params(type, entity_key, kind, status, origin, pinned, search, page_size, cursor, kwargs),
            scoped=False,
        )
        return MemoryFactListResponse.model_validate(data)

    async def create_fact(
        self,
        request: MemoryFactCreateRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> MemoryFact:
        data = await self._client.post(
            "memory/facts", json=MemoryFactCreateRequest.build(request, **kwargs), scoped=False
        )
        return MemoryFact.model_validate(data)

    async def get_fact(self, fact_id: str) -> MemoryFact:
        data = await self._client.get(f"memory/facts/{quote(fact_id, safe='')}", scoped=False)
        return MemoryFact.model_validate(data)

    async def update_fact(
        self,
        fact_id: str,
        *,
        text: str | None = None,
        pinned: bool | None = None,
        always_in_prompt: bool | None = None,
        **kwargs: Any,
    ) -> MemoryFact:
        data = await self._client.patch(
            f"memory/facts/{quote(fact_id, safe='')}",
            json=MemoryFactUpdateRequest.build(text=text, pinned=pinned, always_in_prompt=always_in_prompt, **kwargs),
            scoped=False,
        )
        return MemoryFact.model_validate(data)

    async def delete_fact(self, fact_id: str) -> MemoryFact:
        data = await self._client.delete(f"memory/facts/{quote(fact_id, safe='')}", scoped=False)
        return MemoryFact.model_validate(data)

    async def get_rules(self) -> MemoryRulesResponse:
        return MemoryRulesResponse.model_validate(await self._client.get("memory/rules", scoped=False))

    async def create_rule(self, type: str, text: str) -> MemoryFact:
        data = await self._client.post(
            "memory/rules", json=MemoryRuleCreateRequest.build(type=type, text=text), scoped=False
        )
        return MemoryFact.model_validate(data)

    async def list_revisions(
        self,
        *,
        type: CardType | None = None,
        entity_key: str | None = None,
        fact_id: str | None = None,
        action: Sequence[str] | str | None = None,
        days: int | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        **kwargs: Any,
    ) -> MemoryRevisionListResponse:
        data = await self._client.get(
            "memory/revisions",
            params=_revision_list_params(type, entity_key, fact_id, action, days, page_size, cursor, kwargs),
            scoped=False,
        )
        return MemoryRevisionListResponse.model_validate(data)

    async def undo_revision(self, revision_id: str) -> MemoryFact:
        data = await self._client.post(f"memory/revisions/{quote(revision_id, safe='')}/undo", scoped=False)
        return MemoryFact.model_validate(data)

    async def get_sync(self) -> MemorySync:
        return MemorySync.model_validate(await self._client.get("memory/sync", scoped=False))

    async def start_sync(self) -> MemorySync:
        """Spends the owner's credits; returns before the sync finishes."""
        return MemorySync.model_validate(await self._client.post("memory/sync", scoped=False))
