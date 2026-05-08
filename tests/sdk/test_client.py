from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop import GumloopClient
from gumloop.errors import APIStatusError
from gumloop.errors import AuthenticationError
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import auth_header


@respx.mock
def test_env_access_token_is_used_when_no_explicit_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-token")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"object": "list", "data": []}))

    assert Gumloop().models.list() == {"object": "list", "data": []}
    assert auth_header(route.calls[0].request) == "Bearer env-token"


@pytest.mark.parametrize(
    "client, expected_header",
    [
        (Gumloop(access_token="access-token", api_key="api-key"), "Bearer access-token"),
        (Gumloop(api_key="api-key"), "Bearer api-key"),
    ],
)
@respx.mock
def test_explicit_credentials_win_for_sync_client(client: Gumloop, expected_header: str) -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"object": "list", "data": []}))

    client.models.list()

    assert auth_header(route.calls[0].request) == expected_header


@respx.mock
def test_explicit_credentials_win_for_async_client() -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"object": "list", "data": []}))

    async def run() -> None:
        async with AsyncGumloop(api_key="api-key") as client:
            await client.models.list()

    asyncio.run(run())

    assert auth_header(route.calls[0].request) == "Bearer api-key"


def test_missing_credential_raises_clear_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUMLOOP_ACCESS_TOKEN", raising=False)

    with pytest.raises(AuthenticationError, match="access_token"):
        Gumloop().models.list()


@respx.mock
def test_non_success_response_raises_gumloop_status_error(client: Gumloop) -> None:
    error = {
        "error": {
            "code": "insufficient_scope",
            "message": "Required scope(s): gumloop",
            "type": "permission_error",
            "param": None,
            "details": {},
        }
    }
    respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(403, json=error))

    with pytest.raises(APIStatusError) as exc_info:
        client.models.list()

    assert exc_info.value.status_code == 403
    assert exc_info.value.body == error
    assert str(exc_info.value) == "Required scope(s): gumloop"
    assert exc_info.value.code == "insufficient_scope"
    assert exc_info.value.type == "permission_error"
    assert exc_info.value.param is None
    assert exc_info.value.details == {}


def test_legacy_gumloop_client_warns_but_still_constructs() -> None:
    with pytest.warns(DeprecationWarning, match="legacy flows client"):
        legacy_client = GumloopClient(api_key="api-key", user_id="user-id")

    assert legacy_client.api_key == "api-key"
    assert hasattr(legacy_client, "run_flow")
