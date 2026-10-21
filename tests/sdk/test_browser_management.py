from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.types import BrowserSessionResponse
from tests.sdk.helpers import API_BASE

PROFILE = {"profile_id": "profile-1", "owner_id": "team-1", "owner_scope": "team", "name": "Work"}
OPERATIONS = [
    ("create", ("Work",), "POST", "browser-profiles", {"name": "Work", "team_id": "team-1"}),
    ("get", ("profile-1",), "GET", "browser-profiles/profile-1", None),
    ("update", ("profile-1",), "PATCH", "browser-profiles/profile-1", {"name": "Work", "team_id": "team-1"}),
    ("delete", ("profile-1",), "DELETE", "browser-profiles/profile-1", None),
    (
        "remove_site",
        ("profile-1", "example.com?scope=other"),
        "DELETE",
        "browser-profiles/profile-1/sites/example.com%3Fscope%3Dother",
        None,
    ),
]


@pytest.mark.parametrize(("operation", "args", "method", "path", "body"), OPERATIONS)
@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_browser_profile_operations_preserve_scope_and_parse_results(operation, args, method, path, body, asynchronous):
    payload = {"status": "success"} if operation == "delete" else PROFILE
    route = respx.request(method, f"{API_BASE}/{path}").mock(return_value=httpx.Response(200, json=payload))
    kwargs = {"team_id": "team-1", **({"name": "Work"} if operation == "update" else {})}

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            return await getattr(client.browser_profiles, operation)(*args, **kwargs)

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            response = getattr(client.browser_profiles, operation)(*args, **kwargs)

    assert response.model_dump(exclude_unset=True) == payload
    request = route.calls[0].request
    assert dict(request.url.params) == {"team_id": "team-1"}
    assert (json.loads(request.content) if request.content else None) == body
    assert request.url.raw_path.split(b"?")[0] == ("/api/v1/" + path).encode()


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("override", [None, "team-override"])
@respx.mock
def test_profile_body_and_query_use_one_effective_team(asynchronous, operation, override):
    method = "POST" if operation == "create" else "PATCH"
    path = "browser-profiles" if operation == "create" else "browser-profiles/profile-1"
    route = respx.request(method, f"{API_BASE}/{path}").respond(200, json=PROFILE)
    kwargs = {"team_id": override} if override else {}
    args = ("Work",) if operation == "create" else ("profile-1",)
    if operation == "update":
        kwargs["name"] = "Work"

    async def run():
        async with AsyncGumloop(api_key="key", team_id="team-default") as client:
            return await getattr(client.browser_profiles, operation)(*args, **kwargs)

    if asynchronous:
        asyncio.run(run())
    else:
        with Gumloop(api_key="key", team_id="team-default") as client:
            getattr(client.browser_profiles, operation)(*args, **kwargs)

    request = route.calls[0].request
    assert dict(request.url.params) == {"team_id": override or "team-default"}
    assert json.loads(request.content)["team_id"] == (override or "team-default")


@pytest.mark.parametrize(
    ("operation", "args", "kwargs"),
    [
        ("create", ("",), {}),
        ("create", ("  ",), {}),
        ("update", ("profile-1",), {}),
        ("update", ("profile-1",), {"name": "  "}),
        ("update", ("profile-1",), {"is_default": False}),
    ],
)
@respx.mock
def test_profile_validation_happens_before_http(operation, args, kwargs):
    with Gumloop(api_key="key") as client, pytest.raises(ValidationError) as raised:
        getattr(client.browser_profiles, operation)(*args, **kwargs)

    assert raised.value.errors()
    assert list(respx.calls) == []


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_session_browser_returns_typed_authenticated_ui_links(asynchronous):
    payload = {
        "session_id": "session-1",
        "available": False,
        "viewer_url": "https://gumloop.com/agents/agent-1/chat/session-1",
        "handoffs": [{"action_request_id": "ask-1", "manage_url": "https://gumloop.com/requests/ask-1/manage"}],
    }
    route = respx.get(f"{API_BASE}/sessions/session-1/browser").mock(return_value=httpx.Response(200, json=payload))

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            return await client.sessions.browser("session-1")

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            response = client.sessions.browser("session-1")

    assert isinstance(response, BrowserSessionResponse)
    assert response.handoffs[0].action_request_id == "ask-1"
    assert response.viewer_url == "https://gumloop.com/agents/agent-1/chat/session-1"
    assert route.calls[0].request.method == "GET"
