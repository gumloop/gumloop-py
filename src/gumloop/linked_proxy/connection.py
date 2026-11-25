"""Keeps this machine's tunnel to the linked proxy gateway open: signs in, serves the
gateway's streams, and reconnects until Gumloop refuses a gateway token or the
user signs out."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from datetime import timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed
from websockets.exceptions import InvalidStatus
from websockets.exceptions import WebSocketException

from gumloop._http import user_agent
from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.frames import MAX_FRAME_LENGTH
from gumloop.linked_proxy.frames import ProtocolError
from gumloop.linked_proxy.sign_in import sign_in_token
from gumloop.linked_proxy.tls_check import tls_context
from gumloop.linked_proxy.tunnel import Connection
from gumloop.linked_proxy.tunnel import Tunnel
from gumloop.types import LinkedProxyGatewayToken

# The gateway's refusal header for a sign-in it won't accept.
ERROR_HEADER = "X-Gumloop-Linked-Proxy-Error"
SIGN_IN_REFUSED = "sign_in_refused"

FIRST_RETRY_SECONDS = 1.0
# Spreads out the linked proxies that all reconnect at once when a gateway replica restarts.
FIRST_RETRY_CAP_SECONDS = 5.0
MAX_RETRY_SECONDS = 60.0
# A connection that stayed up this long starts the backoff over.
STABLE_SECONDS = 60.0
_OPEN_TIMEOUT_SECONDS = 10.0

# An open tunnel sends a fresh gateway token this long before its current one expires.
REFRESH_BEFORE_EXPIRY_SECONDS = 15 * 60.0
# The least time between refreshes, which is also the wait before retrying a failed one.
MIN_REFRESH_SECONDS = 60.0

Open = Callable[[str, dict[str, str]], AbstractAsyncContextManager[Connection]]


class SignInRefused(Exception):
    """Gumloop won't give this linked proxy a gateway token: it was unlinked, or its owner can't use it anymore."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SignedOut(Exception):
    """The user has no stored login for this backend."""


class GatewayTokenUnavailable(Exception):
    """Gumloop didn't hand out a gateway token this time; the connection retries."""


class GatewayConnection:
    def __init__(
        self,
        *,
        gateway_url: str,
        linked_proxy_id: str,
        key: Ed25519PrivateKey,
        signed_in: Callable[[], bool],
        gateway_token: Callable[[], LinkedProxyGatewayToken],
        on_open: Callable[[Target], None] | None = None,
        on_connected: Callable[[], None] | None = None,
        on_failed: Callable[[str], None] | None = None,
        open_websocket: Open | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        refresh_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._gateway_url = gateway_url
        self._linked_proxy_id = linked_proxy_id
        self._key = key
        self._signed_in = signed_in
        self._gateway_token = gateway_token
        self._on_open = on_open
        self._on_connected = on_connected
        self._on_failed = on_failed
        self._open = open_websocket or _open_websocket
        self._sleep = sleep
        self._refresh_sleep = refresh_sleep

    async def run(self) -> None:
        """Runs until it raises ``SignInRefused`` or ``SignedOut``. Every other
        failure reconnects after a random wait whose cap doubles up to ``MAX_RETRY_SECONDS``.
        ``gateway_token`` runs in a thread before each connect and each refresh, and raises
        ``SignInRefused`` or ``GatewayTokenUnavailable`` when it has no token. A gateway
        refusal reconnects too: a wrong clock looks the same to the gateway as an unlinked
        linked proxy, and the next gateway token request tells them apart."""
        retry_cap = FIRST_RETRY_CAP_SECONDS
        while True:
            if not self._signed_in():
                raise SignedOut()
            started = time.monotonic()
            try:
                await self._serve()
            except (OSError, asyncio.TimeoutError, WebSocketException, ProtocolError, GatewayTokenUnavailable) as error:
                if self._on_failed is not None:
                    self._on_failed(describe_failure(error))
            if time.monotonic() - started >= STABLE_SECONDS:
                retry_cap = FIRST_RETRY_CAP_SECONDS
            await self._sleep(random.uniform(FIRST_RETRY_SECONDS, retry_cap))
            retry_cap = min(retry_cap * 2, MAX_RETRY_SECONDS)

    async def _serve(self) -> None:
        gateway_token = await asyncio.to_thread(self._gateway_token)
        token = sign_in_token(
            self._key,
            linked_proxy_id=self._linked_proxy_id,
            audience=self._gateway_url,
            gateway_token=gateway_token.gateway_token,
        )
        async with self._open(self._gateway_url, {"Authorization": f"Bearer {token}"}) as websocket:
            if self._on_connected is not None:
                self._on_connected()
            tunnel = Tunnel(websocket, on_open=self._on_open)
            refresh = asyncio.ensure_future(self._refresh(tunnel, gateway_token))
            try:
                await tunnel.run()
            finally:
                refresh.cancel()
                await asyncio.gather(refresh, return_exceptions=True)

    async def _refresh(self, tunnel: Tunnel, gateway_token: LinkedProxyGatewayToken) -> None:
        """Sends a fresh gateway token before each one expires. When Gumloop refuses one, the
        gateway's own recheck closes the tunnel. A gateway token without ``expires_at`` comes
        from a backend older than refreshes, whose gateway would reject one."""
        while gateway_token.expires_at is not None:
            await self._refresh_sleep(_seconds_until_refresh(gateway_token.expires_at))
            try:
                gateway_token = await asyncio.to_thread(self._gateway_token)
            except GatewayTokenUnavailable:
                continue
            except (SignInRefused, SignedOut):
                return
            await tunnel.send_gateway_token(gateway_token.gateway_token)


def _seconds_until_refresh(expires_at: str) -> float:
    # Python 3.10's fromisoformat rejects a trailing Z.
    expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
    return max(remaining - REFRESH_BEFORE_EXPIRY_SECONDS, MIN_REFRESH_SECONDS)


def describe_failure(error: BaseException) -> str:
    """Why a connection attempt or an open tunnel ended, in words for ``gumloop browser proxy status``."""
    if isinstance(error, ConnectionClosed):
        if error.rcvd is None:
            return "the connection dropped"
        return f"the gateway closed the connection ({error.rcvd.reason or error.rcvd.code})"
    if isinstance(error, InvalidStatus):
        if error.response.headers.get(ERROR_HEADER) == SIGN_IN_REFUSED:
            return "the gateway refused the sign-in (is this computer's clock right?)"
        return f"the gateway answered HTTP {error.response.status_code}"
    if isinstance(error, asyncio.TimeoutError):
        return "the gateway didn't answer in time"
    if isinstance(error, ProtocolError):
        return f"the gateway sent an invalid message ({error})"
    if isinstance(error, OSError):
        return f"can't reach the gateway ({(error.strerror or str(error) or type(error).__name__).lower()})"
    return str(error) or type(error).__name__


def _open_websocket(url: str, headers: dict[str, str]) -> AbstractAsyncContextManager[Connection]:
    return websocket_connect(
        url,
        additional_headers=headers,
        user_agent_header=user_agent(),
        ssl=tls_context() if url.startswith("wss://") else None,
        compression=None,
        max_size=MAX_FRAME_LENGTH,
        open_timeout=_OPEN_TIMEOUT_SECONDS,
    )
