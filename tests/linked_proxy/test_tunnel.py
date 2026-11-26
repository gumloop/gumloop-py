from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

import pytest

from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.frames import INITIAL_WINDOW
from gumloop.linked_proxy.frames import MAX_DATA_LENGTH
from gumloop.linked_proxy.frames import Frame
from gumloop.linked_proxy.frames import FrameType
from gumloop.linked_proxy.frames import ProtocolError
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

    def close(self) -> None:
        self._inbound.put_nowait(None)

    async def next_frame(self) -> Frame:
        return await asyncio.wait_for(self._sent.get(), 5)


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()
    writer.close()


async def _open(
    gateway: FakeGateway, port: int, *, on_open: Callable[[Target], None] | None = None
) -> asyncio.Task[None]:
    """Opens stream 1 to the echo server on port and returns the running tunnel."""

    async def dial(target: Target) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_connection("127.0.0.1", port)

    run = asyncio.ensure_future(Tunnel(gateway, dial=dial, on_open=on_open).run())
    gateway.push(Frame(type=FrameType.OPEN, stream_id=1, payload=b"example.com:443"))
    assert (await gateway.next_frame()).type is FrameType.OPEN_OK

    return run


@pytest.mark.timeout(10)
def test_tunnel_relays_more_than_a_window_each_way() -> None:
    async def scenario() -> None:
        server = await asyncio.start_server(_echo, "127.0.0.1", 0)
        gateway = FakeGateway()
        opened: list[Target] = []
        run = await _open(gateway, server.sockets[0].getsockname()[1], on_open=opened.append)

        sent = os.urandom(4 * INITIAL_WINDOW)
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

        assert bytes(received) == sent
        assert opened == [Target(host="example.com", port=443)]
        gateway.close()
        with pytest.raises(ConnectionError):
            await run
        server.close()
        await server.wait_closed()

    asyncio.run(scenario())


@pytest.mark.timeout(10)
def test_data_the_gateway_sent_before_its_close_still_reaches_the_destination() -> None:
    async def scenario() -> None:
        received: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

        async def record(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            received.set_result(await reader.read())
            writer.close()

        server = await asyncio.start_server(record, "127.0.0.1", 0)
        gateway = FakeGateway()
        run = await _open(gateway, server.sockets[0].getsockname()[1])

        sent = os.urandom(INITIAL_WINDOW // 2)
        for offset in range(0, len(sent), MAX_DATA_LENGTH):
            gateway.push(Frame(type=FrameType.DATA, stream_id=1, payload=sent[offset : offset + MAX_DATA_LENGTH]))
        gateway.push(Frame(type=FrameType.CLOSE, stream_id=1))

        assert await asyncio.wait_for(received, 5) == sent
        gateway.close()
        with pytest.raises(ConnectionError):
            await run
        server.close()
        await server.wait_closed()

    asyncio.run(scenario())


@pytest.mark.timeout(10)
def test_tunnel_refuses_a_private_destination_without_dialing() -> None:
    async def scenario() -> None:
        dialed: list[Target] = []

        async def dial(target: Target) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
            dialed.append(target)
            raise AssertionError("a refused destination is never dialed")

        gateway = FakeGateway()
        run = asyncio.ensure_future(Tunnel(gateway, dial=dial).run())
        gateway.push(Frame(type=FrameType.OPEN, stream_id=1, payload=b"10.0.0.1:443"))

        assert await gateway.next_frame() == Frame(type=FrameType.OPEN_FAIL, stream_id=1, payload=b"address")
        assert dialed == []
        gateway.close()
        with pytest.raises(ConnectionError):
            await run

    asyncio.run(scenario())


@pytest.mark.timeout(10)
def test_tunnel_ends_when_the_gateway_sends_past_the_window() -> None:
    async def scenario() -> None:
        server = await asyncio.start_server(_echo, "127.0.0.1", 0)
        gateway = FakeGateway()
        run = await _open(gateway, server.sockets[0].getsockname()[1])

        # Pushed without yielding, so the tunnel reads them back to back before granting anything.
        for _ in range(INITIAL_WINDOW // MAX_DATA_LENGTH):
            gateway.push(Frame(type=FrameType.DATA, stream_id=1, payload=bytes(MAX_DATA_LENGTH)))
        gateway.push(Frame(type=FrameType.DATA, stream_id=1, payload=b"\x00"))

        with pytest.raises(ProtocolError):
            await run
        server.close()
        await server.wait_closed()

    asyncio.run(scenario())


@pytest.mark.timeout(10)
def test_tunnel_sends_a_gateway_token_and_ends_when_the_gateway_sends_one() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        tunnel = Tunnel(gateway)
        run = asyncio.ensure_future(tunnel.run())

        await tunnel.send_gateway_token("fresh-token")
        gateway.push(Frame.gateway_token("from-the-gateway"))

        assert await gateway.next_frame() == Frame.gateway_token("fresh-token")
        with pytest.raises(ProtocolError):
            await run

    asyncio.run(scenario())


@pytest.mark.timeout(10)
def test_tunnel_reports_ready_once_and_ends_on_a_second_ready() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        readies: list[None] = []
        run = asyncio.ensure_future(Tunnel(gateway, on_ready=lambda: readies.append(None)).run())

        gateway.push(Frame(type=FrameType.READY, stream_id=0))
        gateway.push(Frame(type=FrameType.READY, stream_id=0))

        with pytest.raises(ProtocolError):
            await run
        assert len(readies) == 1

    asyncio.run(scenario())
