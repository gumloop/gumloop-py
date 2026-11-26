from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncIterator
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.exceptions import InvalidStatus
from websockets.frames import Close
from websockets.http11 import Response

from gumloop.linked_proxy import connection
from gumloop.linked_proxy.connection import ERROR_HEADER
from gumloop.linked_proxy.connection import GatewayConnection
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignedOut
from gumloop.linked_proxy.connection import SignInRefused
from tests.linked_proxy.helpers import FrozenTime
from tests.linked_proxy.helpers import UpperBoundRandom
from tests.linked_proxy.helpers import tokens

GATEWAY_URL = "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect"


@dataclass(frozen=True)
class Outcome:
    """How one connect attempt ends: ``error`` is raised while opening the
    WebSocket, or by its first ``recv`` when ``opened``."""

    error: BaseException
    opened: bool = False


class FailingConnection:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    async def send(self, message: bytes) -> None:
        pass

    async def recv(self) -> bytes:
        raise self._error


class ScriptedGateway:
    def __init__(self, outcomes: list[Outcome]) -> None:
        self._outcomes = outcomes
        self.authorizations: list[str] = []
        self.waits: list[float] = []

    @contextlib.asynccontextmanager
    async def open(self, url: str, headers: dict[str, str]) -> AsyncIterator[FailingConnection]:
        self.authorizations.append(headers["Authorization"])
        outcome = self._outcomes.pop(0)
        if not outcome.opened:
            raise outcome.error
        yield FailingConnection(outcome.error)

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


def _refused_handshake(status: int, outcome: str) -> InvalidStatus:
    return InvalidStatus(Response(status, "", Headers({ERROR_HEADER: outcome})))


def _gateway_token_claim(authorization: str) -> str:
    claims = authorization.removeprefix("Bearer ").split(".")[1]
    return json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))["gateway_token"]


def _run(
    gateway: ScriptedGateway,
    signed_in_checks: list[bool],
    gateway_token: Callable[[], str] = lambda: "token-1",
) -> None:
    connection = GatewayConnection(
        gateway_url=GATEWAY_URL,
        linked_proxy_id="dp-1",
        key=Ed25519PrivateKey.generate(),
        signed_in=lambda: signed_in_checks.pop(0),
        gateway_token=gateway_token,
        open_websocket=gateway.open,
        sleep=gateway.sleep,
    )
    asyncio.run(connection.run())


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (Outcome(ConnectionClosed(Close(4001, "not_a_member"), None), opened=True), "not_a_member"),
        (Outcome(_refused_handshake(401, "sign_in_refused")), "sign_in_refused"),
    ],
)
def test_refused_sign_in_stops_without_reconnecting(outcome, reason):
    gateway = ScriptedGateway([outcome])

    with pytest.raises(SignInRefused) as refused:
        _run(gateway, [True])

    assert refused.value.reason == reason
    assert gateway.waits == []


@pytest.mark.parametrize(
    "refused_token",
    [
        Outcome(ConnectionClosed(Close(4004, "bad_token"), None), opened=True),
        Outcome(_refused_handshake(401, "gateway_token_refused")),
    ],
)
def test_other_failures_reconnect_with_a_fresh_gateway_token_and_a_growing_wait_until_signed_out(
    monkeypatch, refused_token
):
    monkeypatch.setattr(connection, "random", UpperBoundRandom())
    monkeypatch.setattr(connection, "time", FrozenTime())
    gateway = ScriptedGateway(
        [
            Outcome(ConnectionClosed(Close(4002, "already_connected"), None), opened=True),
            refused_token,
            Outcome(OSError("unreachable")),
        ]
    )
    gateway_token = tokens("token-1", "token-2", GatewayTokenUnavailable("HTTP 503"), "token-3")

    with pytest.raises(SignedOut):
        _run(gateway, [True, True, True, True, False], gateway_token=gateway_token)

    assert gateway.waits == [1.0, 2.0, 4.0, 8.0]
    assert [_gateway_token_claim(authorization) for authorization in gateway.authorizations] == [
        "token-1",
        "token-2",
        "token-3",
    ]


def test_a_gateway_token_refused_by_gumloop_stops_without_connecting():
    gateway = ScriptedGateway([])

    def gateway_token() -> str:
        raise SignInRefused("removed")

    with pytest.raises(SignInRefused):
        _run(gateway, [True], gateway_token=gateway_token)

    assert gateway.authorizations == []
    assert gateway.waits == []
