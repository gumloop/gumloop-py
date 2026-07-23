from __future__ import annotations

import asyncio
from typing import Any

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
from tests.sdk.helpers import request_json


@respx.mock
def test_env_access_token_is_used_when_no_explicit_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-token")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    assert Gumloop().models.list().model_groups == []
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
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    client.models.list()

    assert auth_header(route.calls[0].request) == expected_header


@respx.mock
def test_explicit_credentials_win_for_async_client() -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

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
def test_env_sourced_token_follows_env_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client built from GUMLOOP_ACCESS_TOKEN must send the CURRENT env
    value per request: platforms (e.g. the agent sandbox) rotate the token
    between requests on a live client."""
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "tok-1")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))
    client = Gumloop()

    client.models.list()
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "tok-2")
    client.models.list()

    assert auth_header(route.calls[0].request) == "Bearer tok-1"
    assert auth_header(route.calls[1].request) == "Bearer tok-2"


@respx.mock
def test_env_sourced_token_falls_back_to_snapshot_when_env_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "tok-1")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))
    client = Gumloop()

    monkeypatch.delenv("GUMLOOP_ACCESS_TOKEN")
    client.models.list()

    assert auth_header(route.calls[0].request) == "Bearer tok-1"


@pytest.mark.parametrize(
    "kwargs, expected_header",
    [
        ({"access_token": "explicit-tok"}, "Bearer explicit-tok"),
        ({"api_key": "gum_xxx"}, "Bearer gum_xxx"),
    ],
)
@respx.mock
def test_explicit_credential_ignores_env_rotation(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], expected_header: str
) -> None:
    """Explicitly passed credentials are immutable — a env var appearing or
    rotating later must never hijack the client's identity."""
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-tok")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))
    client = Gumloop(**kwargs)

    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-tok-2")
    client.models.list()

    assert auth_header(route.calls[0].request) == expected_header


@respx.mock
def test_async_env_sourced_token_follows_env_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "tok-1")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    async def run() -> None:
        async with AsyncGumloop() as client:
            await client.models.list()
            monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "tok-2")
            await client.models.list()

    asyncio.run(run())

    assert auth_header(route.calls[0].request) == "Bearer tok-1"
    assert auth_header(route.calls[1].request) == "Bearer tok-2"


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


def test_flows_gumloop_client_warns_but_still_constructs() -> None:
    with pytest.warns(DeprecationWarning, match="flows client"):
        flows_client = GumloopClient(api_key="api-key", user_id="user-id")

    assert flows_client.api_key == "api-key"
    assert hasattr(flows_client, "run_flow")


@respx.mock
def test_user_id_sets_x_auth_key_header_for_personal_api_key_auth() -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop(api_key="gum_xxx", user_id="user_123").models.list()

    assert auth_header(route.calls[0].request) == "Bearer gum_xxx"
    assert route.calls[0].request.headers["x-auth-key"] == "user_123"


@respx.mock
def test_oauth_default_does_not_send_x_auth_key_header() -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop(access_token="oauth_token").models.list()

    assert "x-auth-key" not in route.calls[0].request.headers


@respx.mock
def test_env_user_id_is_used_when_not_passed_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_USER_ID", "env_user")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop(api_key="gum_xxx").models.list()

    assert route.calls[0].request.headers["x-auth-key"] == "env_user"


@respx.mock
def test_async_user_id_sets_x_auth_key_header() -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    async def run() -> None:
        async with AsyncGumloop(api_key="gum_xxx", user_id="user_123") as client:
            await client.models.list()

    asyncio.run(run())

    assert route.calls[0].request.headers["x-auth-key"] == "user_123"


_AGENT_JSON = {"agent": {"id": "agent_1", "name": "Agent"}}


@respx.mock
def test_team_id_is_sent_as_query_param_on_every_request() -> None:
    # Team keys are validated against ``team_id`` — it must be on every request.
    route = respx.get(f"{API_BASE}/agents/agent_1").mock(return_value=httpx.Response(200, json=_AGENT_JSON))

    Gumloop(api_key="team_key", user_id="user_123", team_id="team_1").agents.retrieve("agent_1")

    assert route.calls[0].request.url.params["team_id"] == "team_1"


@respx.mock
def test_explicit_team_id_wins_over_client_team_id() -> None:
    route = respx.get(f"{API_BASE}/agents").mock(return_value=httpx.Response(200, json={"agents": []}))

    Gumloop(api_key="team_key", user_id="user_123", team_id="team_1").agents.list(team_id="team_2")

    assert route.calls[0].request.url.params["team_id"] == "team_2"


@respx.mock
def test_no_team_id_omits_query_param() -> None:
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop(api_key="gum_xxx", user_id="user_123").models.list()

    assert "team_id" not in route.calls[0].request.url.params


@respx.mock
def test_env_team_id_is_used_when_not_passed_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_TEAM_ID", "env_team")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop(api_key="team_key", user_id="user_123").models.list()

    assert route.calls[0].request.url.params["team_id"] == "env_team"


@respx.mock
def test_team_id_defaults_into_mcp_execute_body() -> None:
    # /mcp/tools/call reads team_id from the body — a query-only default would
    # authenticate as the team but silently execute with personal credentials.
    route = respx.post(f"{API_BASE}/mcp/tools/call").mock(return_value=httpx.Response(200, json={"results": []}))

    Gumloop(api_key="team_key", user_id="user_123", team_id="team_1").mcp.execute("server_1", "tool_1")

    assert request_json(route.calls[0].request)["team_id"] == "team_1"


@respx.mock
def test_team_id_defaults_into_agent_create_body() -> None:
    route = respx.post(f"{API_BASE}/agents").mock(return_value=httpx.Response(201, json=_AGENT_JSON))

    client = Gumloop(api_key="team_key", user_id="user_123", team_id="team_1")
    client.agents.create(name="Agent", model_name="model")
    client.agents.create(name="Agent", model_name="model", team_id="team_2")

    assert request_json(route.calls[0].request)["team_id"] == "team_1"
    assert request_json(route.calls[1].request)["team_id"] == "team_2"


@respx.mock
def test_async_team_id_is_sent_as_query_param() -> None:
    route = respx.get(f"{API_BASE}/agents/agent_1").mock(return_value=httpx.Response(200, json=_AGENT_JSON))

    async def run() -> None:
        async with AsyncGumloop(api_key="team_key", user_id="user_123", team_id="team_1") as client:
            await client.agents.retrieve("agent_1")

    asyncio.run(run())

    assert route.calls[0].request.url.params["team_id"] == "team_1"


@respx.mock
def test_traceparent_env_is_forwarded_as_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("TRACEPARENT", "00-11111111111111111111111111111111-2222222222222222-01")
    monkeypatch.setenv("TRACESTATE", "gumloop=1")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop().models.list()

    request = route.calls[0].request
    assert request.headers["traceparent"] == "00-11111111111111111111111111111111-2222222222222222-01"
    assert request.headers["tracestate"] == "gumloop=1"


@respx.mock
def test_no_trace_headers_without_traceparent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-token")
    monkeypatch.delenv("TRACEPARENT", raising=False)
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    Gumloop().models.list()

    request = route.calls[0].request
    assert "traceparent" not in request.headers
    assert "tracestate" not in request.headers


@respx.mock
def test_traceparent_env_is_forwarded_on_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMLOOP_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("TRACEPARENT", "00-11111111111111111111111111111111-2222222222222222-01")
    route = respx.get(f"{API_BASE}/models").mock(return_value=httpx.Response(200, json={"model_groups": []}))

    async def run() -> None:
        async with AsyncGumloop() as client:
            await client.models.list()

    asyncio.run(run())

    request = route.calls[0].request
    assert request.headers["traceparent"] == "00-11111111111111111111111111111111-2222222222222222-01"
