"""Keeps this machine's tunnel to the linked proxy gateway open: signs in, serves the
gateway's streams, and reconnects until the gateway refuses the sign-in or the
user signs out."""

from __future__ import annotations

import asyncio
import functools
import random
import ssl
import time
from collections.abc import Awaitable
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import certifi
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
from gumloop.linked_proxy.tunnel import Connection
from gumloop.linked_proxy.tunnel import Tunnel

# The gateway's close code and refusal header for a sign-in it won't accept.
CLOSE_SIGN_IN_REFUSED = 4001
ERROR_HEADER = "X-Gumloop-Linked-Proxy-Error"
SIGN_IN_REFUSED = "sign_in_refused"

FIRST_RETRY_SECONDS = 1.0
MAX_RETRY_SECONDS = 60.0
# A connection that stayed up this long starts the backoff over.
STABLE_SECONDS = 60.0
_OPEN_TIMEOUT_SECONDS = 10.0

Open = Callable[[str, dict[str, str]], AbstractAsyncContextManager[Connection]]


class SignInRefused(Exception):
    """The gateway won't accept this linked proxy: it was unlinked, or its owner can't use it anymore."""

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
        gateway_token: Callable[[], str],
        on_open: Callable[[Target], None] | None = None,
        open_websocket: Open | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._gateway_url = gateway_url
        self._linked_proxy_id = linked_proxy_id
        self._key = key
        self._signed_in = signed_in
        self._gateway_token = gateway_token
        self._on_open = on_open
        self._open = open_websocket or _open_websocket
        self._sleep = sleep

    async def run(self) -> None:
        """Runs until it raises ``SignInRefused`` or ``SignedOut``. Every other
        failure reconnects after a random wait whose cap doubles up to ``MAX_RETRY_SECONDS``.
        ``gateway_token`` runs in a thread before each connect, and raises
        ``SignInRefused`` or ``GatewayTokenUnavailable`` when it has no token."""
        retry_cap = FIRST_RETRY_SECONDS
        while True:
            if not self._signed_in():
                raise SignedOut()
            started = time.monotonic()
            try:
                await self._serve()
            except (OSError, asyncio.TimeoutError, WebSocketException, ProtocolError, GatewayTokenUnavailable) as error:
                reason = _sign_in_refusal(error)
                if reason is not None:
                    raise SignInRefused(reason) from error
            if time.monotonic() - started >= STABLE_SECONDS:
                retry_cap = FIRST_RETRY_SECONDS
            await self._sleep(random.uniform(FIRST_RETRY_SECONDS, retry_cap))
            retry_cap = min(retry_cap * 2, MAX_RETRY_SECONDS)

    async def _serve(self) -> None:
        gateway_token = await asyncio.to_thread(self._gateway_token)
        token = sign_in_token(
            self._key,
            linked_proxy_id=self._linked_proxy_id,
            audience=self._gateway_url,
            gateway_token=gateway_token,
        )
        async with self._open(self._gateway_url, {"Authorization": f"Bearer {token}"}) as websocket:
            await Tunnel(websocket, on_open=self._on_open).run()


def _sign_in_refusal(error: BaseException) -> str | None:
    if isinstance(error, ConnectionClosed) and error.rcvd is not None and error.rcvd.code == CLOSE_SIGN_IN_REFUSED:
        return error.rcvd.reason or SIGN_IN_REFUSED
    if (
        isinstance(error, InvalidStatus)
        and error.response.status_code == 401
        and error.response.headers.get(ERROR_HEADER) == SIGN_IN_REFUSED
    ):
        return SIGN_IN_REFUSED
    return None


def _open_websocket(url: str, headers: dict[str, str]) -> AbstractAsyncContextManager[Connection]:
    return websocket_connect(
        url,
        additional_headers=headers,
        user_agent_header=user_agent(),
        ssl=_tls_context() if url.startswith("wss://") else None,
        compression=None,
        max_size=MAX_FRAME_LENGTH,
        open_timeout=_OPEN_TIMEOUT_SECONDS,
    )


@functools.cache
def _tls_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())
