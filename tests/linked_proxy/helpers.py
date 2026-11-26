from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import ModuleType

from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.frames import INITIAL_WINDOW
from gumloop.linked_proxy.frames import MAX_DATA_LENGTH
from gumloop.linked_proxy.frames import Frame
from gumloop.linked_proxy.frames import FrameType
from gumloop.linked_proxy.tunnel import Tunnel


class FakeGateway:
    """The gateway's end of the WebSocket. Frames pushed here reach the tunnel's
    ``recv``; frames the tunnel sends come back from ``next_frame``."""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._sent: asyncio.Queue[Frame] = asyncio.Queue()

    async def send(self, message: bytes) -> None:
        self._sent.put_nowait(Frame.decode(message))

    async def recv(self) -> bytes:
        message = await self._inbound.get()
        if message is None:
            raise ConnectionError("the WebSocket closed")
        return message

    def push(self, frame: Frame) -> None:
        self._inbound.put_nowait(frame.encode())

    def push_data(self, stream_id: int, data: bytes) -> None:
        """Pushes data as DATA frames of at most ``MAX_DATA_LENGTH`` bytes, without yielding."""
        for offset in range(0, len(data), MAX_DATA_LENGTH):
            self.push(Frame(type=FrameType.DATA, stream_id=stream_id, payload=data[offset : offset + MAX_DATA_LENGTH]))

    def close(self) -> None:
        self._inbound.put_nowait(None)

    async def next_frame(self) -> Frame:
        return await self._sent.get()

    def unread_frames(self) -> list[Frame]:
        frames = []
        while not self._sent.empty():
            frames.append(self._sent.get_nowait())
        return frames


async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()
    writer.close()


async def open_stream(
    gateway: FakeGateway, port: int, *, on_open: Callable[[Target], None] | None = None
) -> asyncio.Task[None]:
    """Opens stream 1 to the server on port and returns the running tunnel."""

    async def dial(target: Target) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_connection("127.0.0.1", port)

    run = asyncio.ensure_future(Tunnel(gateway, dial=dial, on_open=on_open).run())
    gateway.push(Frame(type=FrameType.OPEN, stream_id=1, payload=b"example.com:443"))
    opened = await gateway.next_frame()
    if opened.type is not FrameType.OPEN_OK:
        raise AssertionError(f"stream 1 did not open: {opened}")
    return run


async def relay_through_stream(gateway: FakeGateway, sent: bytes) -> bytes:
    """Sends ``sent`` on stream 1 as the gateway would, within the window the CLI grants,
    and returns what comes back, granting window as the gateway does."""
    offset, send_window, unacked = 0, INITIAL_WINDOW, 0
    received = bytearray()
    while len(received) < len(sent):
        while offset < len(sent) and send_window > 0:
            chunk = sent[offset : offset + min(MAX_DATA_LENGTH, send_window)]
            gateway.push(Frame(type=FrameType.DATA, stream_id=1, payload=chunk))
            offset, send_window = offset + len(chunk), send_window - len(chunk)
        frame = await gateway.next_frame()
        if frame.type is FrameType.WINDOW:
            send_window += frame.window_increment
        elif frame.type is FrameType.DATA:
            received += frame.payload
            unacked += len(frame.payload)
            if unacked >= INITIAL_WINDOW // 2:
                gateway.push(Frame.window(1, unacked))
                unacked = 0
    return bytes(received)


def tokens(*results: str | Exception) -> Callable[[], str]:
    """A gateway token fetch that returns, or raises, ``results`` in order."""
    remaining = list(results)

    def fetch() -> str:
        result = remaining.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


class UpperBoundRandom(ModuleType):
    """Stands in for a module's ``random`` name: ``uniform`` always picks its upper bound."""

    def __init__(self) -> None:
        super().__init__("random")

    def uniform(self, low: float, high: float) -> float:
        return high


class FrozenTime(ModuleType):
    """Stands in for a module's ``time`` name: ``monotonic`` and ``time`` never move."""

    def __init__(self, now: float = 1_800_000_000.0) -> None:
        super().__init__("time")
        self._now = now

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        return self._now


class RecordingWriter:
    def __init__(self, local: str, remote: str) -> None:
        self._addresses = {"sockname": (local, 50000), "peername": (remote, 443)}
        self.closed = False

    def get_extra_info(self, name: str) -> tuple[str, int]:
        return self._addresses[name]

    def close(self) -> None:
        self.closed = True


class AsyncioDialing(ModuleType):
    """Stands in for a module's ``asyncio`` name: every attribute is the real
    ``asyncio``'s except ``open_connection``, which hands back ``writer``."""

    def __init__(self, writer: RecordingWriter) -> None:
        super().__init__("asyncio")
        self._writer = writer

    def __getattr__(self, name: str) -> object:
        return getattr(asyncio, name)

    async def open_connection(self, host: str, port: int) -> tuple[asyncio.StreamReader, RecordingWriter]:
        return asyncio.StreamReader(), self._writer
