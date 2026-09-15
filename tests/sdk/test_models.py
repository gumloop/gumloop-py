from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

_ROUTE_RESPONSE = {
    "router": "gumloop-chew",
    "route": {
        "model": "gpt-5.6-luna",
        "lane": "light",
        "verdict_lane": "light",
        "adjustment": None,
        "reasoning_effort": "medium",
        "fallback_models": ["claude-opus-5"],
        "fail_closed": False,
    },
    "candidates": [
        {
            "requested_model": "gpt-5.6-luna",
            "model": "gpt-5.6-luna",
            "lanes": ["light"],
            "lane_basis": "catalog",
            "status": "eligible",
        },
        {
            "requested_model": "claude-opus-5",
            "model": "claude-opus-5",
            "lanes": ["plus", "max"],
            "lane_basis": "catalog",
            "status": "eligible",
        },
    ],
}


@respx.mock
def test_models_route_posts_the_decision_request(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/models/route").mock(return_value=httpx.Response(200, json=_ROUTE_RESPONSE))

    result = client.models.route(
        input="Summarize this email thread",
        models=["gpt-5.6-luna", "claude-opus-5"],
        agent={"system_prompt": "You summarize email."},
    )

    assert result.route.model == "gpt-5.6-luna"
    assert result.route.fallback_models == ["claude-opus-5"]
    assert [c.status for c in result.candidates] == ["eligible", "eligible"]
    assert request_json(route.calls[0].request) == {
        "input": "Summarize this email thread",
        "models": ["gpt-5.6-luna", "claude-opus-5"],
        "agent": {"system_prompt": "You summarize email."},
    }


def test_models_route_requires_input_or_message(client: Gumloop) -> None:
    with pytest.raises(ValueError, match="input or message is required"):
        client.models.route(models=["gpt-5.6-luna"])


@respx.mock
def test_async_models_route(async_client: AsyncGumloop) -> None:
    respx.post(f"{API_BASE}/models/route").mock(return_value=httpx.Response(200, json=_ROUTE_RESPONSE))

    result = asyncio.run(async_client.models.route(message="Summarize this email thread"))

    assert result.router == "gumloop-chew"
    assert result.route.lane == "light"
