from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import auth_header


@respx.mock
def test_organizations_list(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/organizations").mock(
        return_value=httpx.Response(200, json={"organizations": [{"id": "org_1", "name": "Acme"}]})
    )

    result = client.organizations.list()

    assert [(o.id, o.name) for o in result.organizations] == [("org_1", "Acme")]
    assert auth_header(route.calls[0].request) == "Bearer token"


@respx.mock
def test_async_organizations_list() -> None:
    respx.get(f"{API_BASE}/organizations").mock(return_value=httpx.Response(200, json={"organizations": []}))

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            assert (await client.organizations.list()).organizations == []

    asyncio.run(run())
