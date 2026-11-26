"""Serves the streams the linked proxy gateway opens over the CLI's WebSocket: each
one becomes a connection from this machine to an allowed destination."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Protocol

from gumloop.linked_proxy.destinations import RefusedError
from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.destinations import connect
from gumloop.linked_proxy.destinations import parse_target
from gumloop.linked_proxy.frames import INITIAL_WINDOW
from gumloop.linked_proxy.frames import MAX_DATA_LENGTH
from gumloop.linked_proxy.frames import OPEN_FAIL_DIAL
from gumloop.linked_proxy.frames import Frame
from gumloop.linked_proxy.frames import FrameType
from gumloop.linked_proxy.frames import ProtocolError

# Bounds the credit the gateway may grant, so a stream's window stays sane.
_MAX_SEND_WINDOW = 64 * 1024 * 1024
# How long a destination gets to take the data the gateway sent before its CLOSE.
_CLOSE_WRITE_SECONDS = 10.0

Dial = Callable[[Target], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


class Connection(Protocol):
    """The WebSocket to the gateway. ``websockets``' client connection is one."""

    async def send(self, message: bytes) -> None: ...

    async def recv(self) -> bytes | str: ...


class Tunnel:
    def __init__(
        self,
        connection: Connection,
        *,
        dial: Dial = connect,
        on_open: Callable[[Target], None] | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        self._connection = connection
        self._dial = dial
        self._on_open = on_open
        self._on_ready = on_ready
        self._ready = False
        self._send_lock = asyncio.Lock()
        self._streams: dict[int, _Stream] = {}
        self._last_id = 0
        self._tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        """Serves streams until ``recv`` raises: the WebSocket closed, or the
        gateway broke the protocol (``ProtocolError``). Every stream ends with it."""
        try:
            while True:
                message = await self._connection.recv()
                if isinstance(message, str):
                    raise ProtocolError("a text message")
                self._deliver(Frame.decode(message))
        finally:
            for stream in list(self._streams.values()):
                stream.shut()
            for task in self._tasks:
                task.cancel()

    def _deliver(self, frame: Frame) -> None:
        if frame.type is FrameType.READY:
            if self._ready:
                raise ProtocolError("a second READY")
            self._ready = True
            if self._on_ready is not None:
                self._on_ready()
            return
        if frame.type is FrameType.OPEN:
            # Stream ids only grow, so a late frame can't reach a newer stream.
            if frame.stream_id <= self._last_id:
                raise ProtocolError(f"stream {frame.stream_id} opened again")
            self._last_id = frame.stream_id
            stream = _Stream(self, frame.stream_id)
            self._streams[frame.stream_id] = stream
            stream.start(self._spawn(stream.open(frame.payload.decode("utf-8", errors="replace"))))
            return
        if frame.type in (FrameType.OPEN_OK, FrameType.OPEN_FAIL, FrameType.GATEWAY_TOKEN):
            raise ProtocolError(f"the gateway sent {frame.type.name}")

        stream = self._streams.get(frame.stream_id)
        if stream is None:
            if frame.stream_id <= self._last_id:
                # The stream already ended here; the gateway's frames crossed its CLOSE.
                return
            raise ProtocolError(f"a frame for stream {frame.stream_id}, which was never opened")
        if frame.type is FrameType.DATA:
            stream.receive(frame.payload)
        elif frame.type is FrameType.WINDOW:
            stream.grant(frame.window_increment)
        elif frame.type is FrameType.CLOSE:
            stream.close_from_gateway()

    async def send_gateway_token(self, token: str) -> None:
        """The gateway checks it right away and uses it for its rechecks from then on."""
        await self._send(Frame.gateway_token(token))

    def _spawn(self, coroutine: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        # A stream fails when the WebSocket does; run() reports that once.
        if not task.cancelled():
            task.exception()

    async def _send(self, frame: Frame) -> None:
        async with self._send_lock:
            await self._connection.send(frame.encode())

    def _forget(self, stream_id: int) -> None:
        self._streams.pop(stream_id, None)


class _Stream:
    """One connection to a destination. Its frames arrive on the tunnel's read
    loop; its own tasks dial and relay."""

    def __init__(self, tunnel: Tunnel, stream_id: int) -> None:
        self._tunnel = tunnel
        self.id = stream_id
        self._tasks: list[asyncio.Task[None]] = []
        self._writer: asyncio.StreamWriter | None = None
        self._download_task: asyncio.Task[None] | None = None
        self._open = False
        self._ended = False
        self._send_window = INITIAL_WINDOW
        self._can_send = asyncio.Event()
        self._can_send.set()
        self._recv_window = INITIAL_WINDOW
        # None marks the gateway's CLOSE.
        self._incoming: asyncio.Queue[bytes | None] = asyncio.Queue()

    def start(self, task: asyncio.Task[None]) -> None:
        self._tasks.append(task)

    async def open(self, hostport: str) -> None:
        try:
            target = parse_target(hostport)
            if self._tunnel._on_open is not None:
                self._tunnel._on_open(target)
            reader, writer = await self._tunnel._dial(target)
        except RefusedError as error:
            await self._fail(error.reason.value)
            return
        except OSError:
            await self._fail(OPEN_FAIL_DIAL)
            return
        if self._ended:
            writer.close()
            return

        self._writer = writer
        self._open = True
        await self._tunnel._send(Frame(type=FrameType.OPEN_OK, stream_id=self.id))
        self._tasks.append(self._tunnel._spawn(self._upload(reader)))
        self._download_task = self._tunnel._spawn(self._download(writer))
        self._tasks.append(self._download_task)

    async def _fail(self, reason: str) -> None:
        self._ended = True
        self._tunnel._forget(self.id)
        await self._tunnel._send(Frame(type=FrameType.OPEN_FAIL, stream_id=self.id, payload=reason.encode()))

    def receive(self, data: bytes) -> None:
        if not self._open:
            raise ProtocolError(f"data before OPEN_OK on stream {self.id}")
        if len(data) > self._recv_window:
            raise ProtocolError(f"data past the window on stream {self.id}")
        self._recv_window -= len(data)
        self._incoming.put_nowait(data)

    def grant(self, increment: int) -> None:
        self._send_window += increment
        if self._send_window > _MAX_SEND_WINDOW:
            raise ProtocolError(f"a window past {_MAX_SEND_WINDOW} bytes on stream {self.id}")
        self._can_send.set()

    async def _upload(self, reader: asyncio.StreamReader) -> None:
        """Destination to gateway, within the gateway's window."""
        try:
            while True:
                await self._can_send.wait()
                data = await reader.read(min(self._send_window, MAX_DATA_LENGTH))
                if not data:
                    break
                self._send_window -= len(data)
                if self._send_window == 0:
                    self._can_send.clear()
                await self._tunnel._send(Frame(type=FrameType.DATA, stream_id=self.id, payload=data))
        except OSError:
            pass
        await self._close()

    async def _download(self, writer: asyncio.StreamWriter) -> None:
        """Gateway to destination. Credit goes back once half the window is written."""
        unacked = 0
        try:
            while (data := await self._incoming.get()) is not None:
                writer.write(data)
                await writer.drain()
                unacked += len(data)
                if unacked >= INITIAL_WINDOW // 2:
                    self._recv_window += unacked
                    await self._tunnel._send(Frame.window(self.id, unacked))
                    unacked = 0
        except OSError:
            await self._close()
        finally:
            writer.close()

    def close_from_gateway(self) -> None:
        """Stops reading from the destination but still writes it what the gateway
        sent first, aborting the connection if that takes too long."""
        if self._ended:
            return
        if self._download_task is None or self._writer is None:
            self.shut()
            return
        self._ended = True
        self._tunnel._forget(self.id)
        for task in self._tasks:
            if task is not self._download_task:
                task.cancel()
        self._incoming.put_nowait(None)
        deadline = asyncio.get_running_loop().call_later(_CLOSE_WRITE_SECONDS, self._writer.transport.abort)
        self._download_task.add_done_callback(lambda _task: deadline.cancel())

    async def _close(self) -> None:
        """Ends the stream from this side and tells the gateway."""
        if self._ended:
            return
        self.shut()
        await self._tunnel._send(Frame(type=FrameType.CLOSE, stream_id=self.id))

    def shut(self) -> None:
        """Ends the stream without telling the gateway: it closed the stream, or the tunnel ended."""
        if self._ended:
            return
        self._ended = True
        self._tunnel._forget(self.id)
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()
        if self._writer is not None:
            self._writer.close()
