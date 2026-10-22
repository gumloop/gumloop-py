from __future__ import annotations

import asyncio
import json

import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop import GumloopError
from gumloop.types import BrowserSessionResponse
from tests.sdk.helpers import API_BASE

PROFILE = {"profile_id": "profile-1", "owner_id": "actor", "owner_scope": "personal", "name": "Work"}
OPERATIONS = [
    ("create", ("Work",), "POST", "browser-profiles", {"name": "Work"}),
    ("get", ("profile-1",), "GET", "browser-profiles/profile-1", None),
    ("update", ("profile-1",), "PATCH", "browser-profiles/profile-1", {"name": "Work"}),
    ("delete", ("profile-1",), "DELETE", "browser-profiles/profile-1", None),
]


@pytest.mark.parametrize(("operation", "args", "method", "path", "body"), OPERATIONS)
@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_personal_profile_operations(operation, args, method, path, body, asynchronous):
    payload = {"status": "success"} if operation == "delete" else PROFILE
    route = respx.request(method, f"{API_BASE}/{path}").respond(200, json=payload)
    kwargs = {"name": "Work"} if operation == "update" else {}

    async def run():
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            return await getattr(client.browser_profiles, operation)(*args, **kwargs)

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            response = getattr(client.browser_profiles, operation)(*args, **kwargs)

    assert response.model_dump(exclude_unset=True) == payload
    request = route.calls[0].request
    assert not request.url.params
    assert (json.loads(request.content) if request.content else None) == body


@pytest.mark.parametrize(("operation", "args", "method", "path", "body"), OPERATIONS)
@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_personal_profile_operations_reject_configured_team(operation, args, method, path, body, asynchronous):
    kwargs = {"name": "Work"} if operation == "update" else {}

    async def run():
        async with AsyncGumloop(api_key="key", team_id="team") as client:
            await getattr(client.browser_profiles, operation)(*args, **kwargs)

    with pytest.raises(GumloopError, match="without team_id"):
        if asynchronous:
            asyncio.run(run())
        else:
            with Gumloop(api_key="key", team_id="team") as client:
                getattr(client.browser_profiles, operation)(*args, **kwargs)
    assert not respx.calls


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
    with Gumloop(api_key="key") as client, pytest.raises(ValidationError):
        getattr(client.browser_profiles, operation)(*args, **kwargs)
    assert not respx.calls


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_session_browser_returns_only_authenticated_viewer_link(asynchronous):
    payload = {"session_id": "session-1", "viewer_url": "https://gumloop.com/agents/agent-1/chat/session-1"}
    route = respx.get(f"{API_BASE}/sessions/session-1/browser").respond(200, json=payload)

    async def run():
        async with AsyncGumloop(api_key="key") as client:
            return await client.sessions.browser("session-1")

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(api_key="key") as client:
            response = client.sessions.browser("session-1")
    assert isinstance(response, BrowserSessionResponse)
    assert response.model_dump() == payload
    assert not route.calls[0].request.url.params


@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_session_browser_rejects_configured_team(asynchronous):
    async def run():
        async with AsyncGumloop(api_key="key", team_id="team") as client:
            await client.sessions.browser("session")

    with pytest.raises(GumloopError, match="without team_id"):
        if asynchronous:
            asyncio.run(run())
        else:
            with Gumloop(api_key="key", team_id="team") as client:
                client.sessions.browser("session")
    assert not respx.calls
