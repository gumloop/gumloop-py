from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import auth_header


@respx.mock
def test_teams_list_hits_teams_endpoint_with_bearer_header(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/teams").mock(
        return_value=httpx.Response(200, json={"teams": [{"id": "team_123", "name": "Acme"}]})
    )

    result = client.teams.list()

    assert [(t.id, t.name) for t in result.teams] == [("team_123", "Acme")]
    assert auth_header(route.calls[0].request) == "Bearer token"


@respx.mock
def test_async_teams_list() -> None:
    respx.get(f"{API_BASE}/teams").mock(return_value=httpx.Response(200, json={"teams": []}))

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            result = await client.teams.list()
            assert result.teams == []

    asyncio.run(run())
