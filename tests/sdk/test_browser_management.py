from __future__ import annotations

import asyncio
import json

import pytest
import respx
from pydantic import ValidationError

from gumloop import AsyncGumloop
from gumloop import Gumloop
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
@pytest.mark.parametrize("team_source", ["unset", "explicit", "environment"])
def test_personal_profile_operations(operation, args, method, path, body, asynchronous, team_source, monkeypatch):
    if team_source == "environment":
        monkeypatch.setenv("GUMLOOP_TEAM_ID", "team")
    configured_team = "team" if team_source == "explicit" else None
    payload = {"status": "success"} if operation == "delete" else PROFILE
    route = respx.request(method, f"{API_BASE}/{path}").respond(200, json=payload)
    kwargs = {"name": "Work"} if operation == "update" else {}

    async def run():
        async with AsyncGumloop(api_key="key", user_id="actor", team_id=configured_team) as client:
            return await getattr(client.browser_profiles, operation)(*args, **kwargs)

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor", team_id=configured_team) as client:
            response = getattr(client.browser_profiles, operation)(*args, **kwargs)

    assert response.model_dump(exclude_unset=True) == payload
    request = route.calls[0].request
    assert not request.url.params
    assert (json.loads(request.content) if request.content else None) == body


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
