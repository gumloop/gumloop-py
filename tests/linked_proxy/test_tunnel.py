from __future__ import annotations

import asyncio
import os

import pytest

from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.frames import INITIAL_WINDOW
from gumloop.linked_proxy.frames import Frame
from gumloop.linked_proxy.frames import FrameType
from gumloop.linked_proxy.frames import ProtocolError
from gumloop.linked_proxy.tunnel import Tunnel
from tests.linked_proxy.helpers import FakeGateway
from tests.linked_proxy.helpers import echo
from tests.linked_proxy.helpers import open_stream
from tests.linked_proxy.helpers import relay_through_stream


def test_tunnel_relays_more_than_a_window_each_way() -> None:
    async def scenario() -> tuple[bytes, list[Target]]:
        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        gateway = FakeGateway()
        opened: list[Target] = []
        run = await open_stream(gateway, server.sockets[0].getsockname()[1], on_open=opened.append)

        received = await relay_through_stream(gateway, sent)

        gateway.close()
        with pytest.raises(ConnectionError):
            await run
        server.close()
        await server.wait_closed()
        return received, opened

    sent = os.urandom(4 * INITIAL_WINDOW)

    received, opened = asyncio.run(scenario())

    assert received == sent
    assert opened == [Target(host="example.com", port=443)]


def test_data_the_gateway_sent_before_its_close_still_reaches_the_destination() -> None:
    async def scenario() -> tuple[bytes, list[Frame]]:
        received: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

        async def record(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            received.set_result(await reader.read())
            writer.close()

        server = await asyncio.start_server(record, "127.0.0.1", 0)
        gateway = FakeGateway()
        run = await open_stream(gateway, server.sockets[0].getsockname()[1])

        gateway.push_data(1, sent)
        gateway.push(Frame(type=FrameType.CLOSE, stream_id=1))
        destination_received = await received

        unread = gateway.unread_frames()
        gateway.close()
        with pytest.raises(ConnectionError):
            await run
        server.close()
        await server.wait_closed()
        return destination_received, unread

    sent = os.urandom(INITIAL_WINDOW // 2)

    destination_received, unread = asyncio.run(scenario())

    assert destination_received == sent
    assert unread == []


def test_tunnel_refuses_a_private_destination_without_dialing() -> None:
    async def scenario() -> Frame:
        async def dial(target: Target) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
            dialed.append(target)
            raise AssertionError("a refused destination is never dialed")

        gateway = FakeGateway()
        run = asyncio.ensure_future(Tunnel(gateway, dial=dial).run())
        gateway.push(Frame(type=FrameType.OPEN, stream_id=1, payload=b"10.0.0.1:443"))

        answer = await gateway.next_frame()
        gateway.close()
        with pytest.raises(ConnectionError):
            await run
        return answer

    dialed: list[Target] = []

    answer = asyncio.run(scenario())

    assert answer == Frame(type=FrameType.OPEN_FAIL, stream_id=1, payload=b"address")
    assert dialed == []


def test_tunnel_ends_when_the_gateway_sends_past_the_window() -> None:
    async def scenario() -> None:
        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        gateway = FakeGateway()
        run = await open_stream(gateway, server.sockets[0].getsockname()[1])

        # Pushed without yielding, so the tunnel reads them back to back before granting anything.
        gateway.push_data(1, bytes(INITIAL_WINDOW + 1))
        gateway.close()

        try:
            await run
        finally:
            server.close()
            await server.wait_closed()

    with pytest.raises(ProtocolError):
        asyncio.run(scenario())
