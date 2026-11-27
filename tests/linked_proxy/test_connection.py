from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.exceptions import InvalidStatus
from websockets.frames import Close
from websockets.http11 import Response

from gumloop.linked_proxy import connection
from gumloop.linked_proxy.connection import ERROR_HEADER
from gumloop.linked_proxy.connection import LOGIN_CHECK_SECONDS
from gumloop.linked_proxy.connection import REFRESH_BEFORE_EXPIRY_SECONDS
from gumloop.linked_proxy.connection import TUNNEL_VERSION
from gumloop.linked_proxy.connection import TUNNEL_VERSION_HEADER
from gumloop.linked_proxy.connection import GatewayConnection
from gumloop.linked_proxy.connection import GatewayTokenUnavailable
from gumloop.linked_proxy.connection import SignedOut
from gumloop.linked_proxy.connection import SignInRefused
from gumloop.linked_proxy.connection import UpgradeRequired
from gumloop.linked_proxy.frames import Frame
from gumloop.linked_proxy.frames import FrameType
from gumloop.types import CustomProxyGatewayToken
from tests.linked_proxy.helpers import FROZEN_NOW
from tests.linked_proxy.helpers import FrozenDatetime
from tests.linked_proxy.helpers import FrozenTime
from tests.linked_proxy.helpers import UpperBoundRandom
from tests.linked_proxy.helpers import tokens

GATEWAY_URL = "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect"


@dataclass(frozen=True)
class Outcome:
    """How one connect attempt ends: ``error`` is raised while opening the
    WebSocket, or by ``recv`` when ``opened``, after a READY frame when ``ready``."""

    error: BaseException
    opened: bool = False
    ready: bool = False


class FailingConnection:
    def __init__(self, error: BaseException, ready: bool = False) -> None:
        self._error = error
        self._ready = ready

    async def send(self, message: bytes) -> None:
        pass

    async def recv(self) -> bytes:
        # Lets the refresh task start before the tunnel ends.
        await asyncio.sleep(0)
        if self._ready:
            self._ready = False
            return Frame(type=FrameType.READY, stream_id=0).encode()
        raise self._error


class ScriptedGateway:
    def __init__(self, outcomes: list[Outcome]) -> None:
        self._outcomes = outcomes
        self.authorizations: list[str] = []
        self.versions: list[str] = []
        self.waits: list[float] = []

    @contextlib.asynccontextmanager
    async def open(self, url: str, headers: dict[str, str]) -> AsyncIterator[FailingConnection]:
        self.authorizations.append(headers["Authorization"])
        self.versions.append(headers[TUNNEL_VERSION_HEADER])
        outcome = self._outcomes.pop(0)
        if not outcome.opened:
            raise outcome.error
        yield FailingConnection(outcome.error, outcome.ready)

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


class OpenConnection:
    """Stays open until the CLI has sent ``closes_after`` frames, then its ``recv`` fails."""

    def __init__(self, closes_after: int) -> None:
        self.sent: list[Frame] = []
        self._closes_after = closes_after
        self._closed = asyncio.Event()

    async def send(self, message: bytes) -> None:
        self.sent.append(Frame.decode(message))
        if len(self.sent) >= self._closes_after:
            self._closed.set()

    async def recv(self) -> bytes:
        await self._closed.wait()
        raise OSError("closed")


class OpenGateway:
    def __init__(self, connection: OpenConnection) -> None:
        self.connection = connection
        self.waits: list[float] = []

    @contextlib.asynccontextmanager
    async def open(self, url: str, headers: dict[str, str]) -> AsyncIterator[OpenConnection]:
        yield self.connection

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


class RefreshSleep:
    """Records each wait before a refresh; the waits after the first ``returns`` never end."""

    def __init__(self, returns: int) -> None:
        self.waits: list[float] = []
        self._returns = returns

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)
        if len(self.waits) > self._returns:
            await asyncio.Event().wait()


def _refused_handshake(status: int, outcome: str) -> InvalidStatus:
    return InvalidStatus(Response(status, "", Headers({ERROR_HEADER: outcome})))


def _gateway_token_claim(authorization: str) -> str:
    claims = authorization.removeprefix("Bearer ").split(".")[1]
    return json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))["gateway_token"]


async def _never(seconds: float) -> None:
    await asyncio.Event().wait()


def _run(
    gateway: ScriptedGateway | OpenGateway,
    signed_in_checks: list[bool],
    events: list[str] | None = None,
    gateway_token: Callable[[], str | CustomProxyGatewayToken] = lambda: "token-1",
    refresh_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    login_sleep: Callable[[float], Awaitable[None]] = _never,
) -> None:
    recorded = events if events is not None else []

    def fetch() -> CustomProxyGatewayToken:
        token = gateway_token()
        return token if isinstance(token, CustomProxyGatewayToken) else CustomProxyGatewayToken(gateway_token=token)

    connection = GatewayConnection(
        gateway_url=GATEWAY_URL,
        linked_proxy_id="dp-1",
        key=Ed25519PrivateKey.generate(),
        signed_in=lambda: signed_in_checks.pop(0),
        gateway_token=fetch,
        on_connected=lambda: recorded.append("connected"),
        on_failed=recorded.append,
        open_websocket=gateway.open,
        sleep=gateway.sleep,
        refresh_sleep=refresh_sleep,
        login_sleep=login_sleep,
    )
    asyncio.run(connection.run())


@pytest.fixture
def pinned_backoff(monkeypatch):
    monkeypatch.setattr(connection, "random", UpperBoundRandom())
    monkeypatch.setattr(connection, "time", FrozenTime())


@pytest.mark.parametrize(
    ("refusal", "described"),
    [
        (
            Outcome(ConnectionClosed(Close(4001, "not_a_member"), None), opened=True),
            "the gateway closed the connection (not_a_member)",
        ),
        (
            Outcome(_refused_handshake(401, "sign_in_refused")),
            "the gateway refused the sign-in (is this computer's clock right?)",
        ),
    ],
)
def test_a_gateway_refusal_reconnects_and_gumloop_decides_whether_to_stop(pinned_backoff, refusal, described):
    gateway = ScriptedGateway([refusal])
    events: list[str] = []

    with pytest.raises(SignInRefused) as refused:
        _run(
            gateway,
            [True, True],
            events,
            gateway_token=tokens("token-1", SignInRefused("personal_custom_proxy_not_found")),
        )

    assert refused.value.reason == "personal_custom_proxy_not_found"
    assert events == [described]
    assert gateway.waits == [5.0]


@pytest.mark.parametrize(
    ("refused_token", "described"),
    [
        (
            Outcome(ConnectionClosed(Close(4004, "bad_token"), None), opened=True),
            "the gateway closed the connection (bad_token)",
        ),
        (Outcome(_refused_handshake(401, "gateway_token_refused")), "the gateway answered HTTP 401"),
    ],
)
def test_other_failures_reconnect_with_a_fresh_gateway_token_and_a_growing_wait_until_signed_out(
    pinned_backoff, refused_token, described
):
    gateway = ScriptedGateway(
        [
            Outcome(ConnectionClosed(Close(4002, "already_connected"), None), opened=True),
            refused_token,
            Outcome(OSError("unreachable")),
        ]
    )
    events: list[str] = []
    gateway_token = tokens(
        "token-1", "token-2", GatewayTokenUnavailable("Gumloop didn't give a gateway token (HTTP 503)"), "token-3"
    )

    with pytest.raises(SignedOut):
        _run(gateway, [True, True, True, True, False], events, gateway_token=gateway_token)

    assert events == [
        "the gateway closed the connection (already_connected)",
        described,
        "Gumloop didn't give a gateway token (HTTP 503)",
        "can't reach the gateway (unreachable)",
    ]
    assert gateway.waits == [5.0, 10.0, 20.0, 40.0]
    assert [_gateway_token_claim(authorization) for authorization in gateway.authorizations] == [
        "token-1",
        "token-2",
        "token-3",
    ]


def test_it_is_connected_only_once_the_gateway_says_the_tunnel_is_ready():
    gateway = ScriptedGateway(
        [
            Outcome(ConnectionClosed(Close(4002, "already_connected"), None), opened=True),
            Outcome(ConnectionClosed(None, None), opened=True, ready=True),
        ]
    )
    events: list[str] = []

    with pytest.raises(SignedOut):
        _run(gateway, [True, True, False], events)

    assert events == [
        "the gateway closed the connection (already_connected)",
        "connected",
        "the connection dropped",
    ]
    assert gateway.versions == [str(TUNNEL_VERSION)] * 2


def test_a_gateway_that_needs_a_newer_cli_stops_without_retrying():
    gateway = ScriptedGateway([Outcome(_refused_handshake(426, "cli_upgrade_required"))])

    with pytest.raises(UpgradeRequired):
        _run(gateway, [True])

    assert gateway.waits == []


def test_logging_out_ends_the_open_tunnel_before_the_next_refresh():
    gateway = OpenGateway(OpenConnection(closes_after=1))
    login_waits: list[float] = []

    async def login_sleep(seconds: float) -> None:
        login_waits.append(seconds)

    with pytest.raises(SignedOut):
        _run(gateway, [True, False], login_sleep=login_sleep)

    assert login_waits == [LOGIN_CHECK_SECONDS]
    assert gateway.waits == []


@pytest.mark.parametrize("utc_suffix", ["+00:00", "Z"])
def test_an_open_tunnel_sends_a_fresh_gateway_token_before_its_current_one_expires(monkeypatch, utc_suffix):
    monkeypatch.setattr(connection, "datetime", FrozenDatetime)
    gateway = OpenGateway(OpenConnection(closes_after=1))
    refresh_sleep = RefreshSleep(returns=1)
    expires_at = (FROZEN_NOW + timedelta(minutes=20)).isoformat().replace("+00:00", utc_suffix)
    expiring = CustomProxyGatewayToken(gateway_token="token-1", expires_at=expires_at)

    with pytest.raises(SignedOut):
        _run(gateway, [True, False], gateway_token=tokens(expiring, "token-2"), refresh_sleep=refresh_sleep)

    assert refresh_sleep.waits == [20 * 60 - REFRESH_BEFORE_EXPIRY_SECONDS]
    assert gateway.connection.sent == [Frame.gateway_token("token-2")]


def test_a_refresh_after_unlinking_ends_the_open_tunnel():
    gateway = OpenGateway(OpenConnection(closes_after=1))
    expiring = CustomProxyGatewayToken(gateway_token="token-1", expires_at="2027-01-15T12:20:00Z")

    with pytest.raises(SignInRefused) as refused:
        _run(
            gateway,
            [True],
            gateway_token=tokens(expiring, SignInRefused("personal_custom_proxy_not_found")),
            refresh_sleep=RefreshSleep(returns=1),
        )

    assert refused.value.reason == "personal_custom_proxy_not_found"
    assert gateway.connection.sent == []
    assert gateway.waits == []
