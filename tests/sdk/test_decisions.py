from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.spec import DecisionsChoiceAnswer
from gumloop.spec import DecisionsNoulAnswer
from gumloop.spec import DecisionsRequest
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import request_json

RESPONSE = {
    "id": "dec-1",
    "model": "typesafe/jev-1.13",
    "answers": {
        "is_bug": {"type": "noul", "noul": 0.91},
        "segment": {"type": "choice", "choice": "enterprise", "probabilities": {"enterprise": 0.8, "smb": 0.2}},
    },
    "usage": {"input_tokens": 120, "output_tokens": 0, "cost": 0.0001},
}

QUESTIONS = {
    "is_bug": {"type": "noul", "instructions": "Is this a software defect?"},
    "segment": {"type": "choice", "instructions": "Which segment?", "criteria": {"enterprise": None, "smb": None}},
}


@respx.mock
def test_decisions_create_returns_typed_answers(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/decisions").mock(return_value=httpx.Response(200, json=RESPONSE))

    result = client.decisions.create(model="typesafe/jev-1.13", state={"ticket": "blank screen"}, questions=QUESTIONS)

    is_bug, segment = result.answers["is_bug"], result.answers["segment"]
    assert isinstance(is_bug, DecisionsNoulAnswer) and is_bug.noul == 0.91
    assert isinstance(segment, DecisionsChoiceAnswer) and segment.choice == "enterprise"
    assert result.usage.input_tokens == 120
    body = request_json(route.calls[0].request)
    assert body["model"] == "typesafe/jev-1.13"
    assert body["state"] == {"ticket": "blank screen"}
    assert body["questions"]["segment"]["criteria"] == {"enterprise": None, "smb": None}
    assert "provider" not in body


@respx.mock
def test_decisions_accepts_request_instance(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/decisions").mock(return_value=httpx.Response(200, json=RESPONSE))
    request = DecisionsRequest(model="typesafe/jev-1.13", state="x", questions=QUESTIONS)

    client.decisions.create(request)

    assert request_json(route.calls[0].request)["state"] == "x"


@respx.mock
def test_async_decisions_create(async_client: AsyncGumloop) -> None:
    respx.post(f"{API_BASE}/decisions").mock(return_value=httpx.Response(200, json=RESPONSE))

    result = asyncio.run(
        async_client.decisions.create(model="typesafe/jev-1.13", state={"ticket": "x"}, questions=QUESTIONS)
    )

    assert result.model == "typesafe/jev-1.13"
