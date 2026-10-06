"""Decisions resource — OpenRouter request shape."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.errors import GumloopError
from gumloop.spec import DecisionsQuestion
from gumloop.spec import DecisionsRequest
from gumloop.spec import DecisionsResponse
from gumloop.spec._compat import to_wire_dict
from gumloop.spec._decisions import Json

_PATH = "decisions"


def _build_request(
    request: DecisionsRequest | Mapping[str, Any] | None,
    kwargs: dict[str, Any],
) -> DecisionsRequest:
    if isinstance(request, DecisionsRequest):
        base = to_wire_dict(request)
    elif request is None:
        base = {}
    else:
        base = dict(request)
    base.update({k: v for k, v in kwargs.items() if v is not None})
    try:
        return DecisionsRequest.model_validate(base)
    except ValidationError as exc:
        raise GumloopError(f"invalid decisions request: {exc}") from exc


class Decisions:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def create(
        self,
        request: DecisionsRequest | Mapping[str, Any] | None = None,
        *,
        model: str | None = None,
        state: Json | None = None,
        questions: Mapping[str, DecisionsQuestion | Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> DecisionsResponse:
        body = _build_request(request, {"model": model, "state": state, "questions": questions, **kwargs})
        data = self._client.post(_PATH, json=to_wire_dict(body))
        return DecisionsResponse.model_validate(data)


class AsyncDecisions:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def create(
        self,
        request: DecisionsRequest | Mapping[str, Any] | None = None,
        *,
        model: str | None = None,
        state: Json | None = None,
        questions: Mapping[str, DecisionsQuestion | Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> DecisionsResponse:
        body = _build_request(request, {"model": model, "state": state, "questions": questions, **kwargs})
        data = await self._client.post(_PATH, json=to_wire_dict(body))
        return DecisionsResponse.model_validate(data)
