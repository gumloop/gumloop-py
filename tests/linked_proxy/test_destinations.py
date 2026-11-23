from __future__ import annotations

import asyncio

import pytest

from gumloop.linked_proxy.destinations import Refusal
from gumloop.linked_proxy.destinations import RefusedError
from gumloop.linked_proxy.destinations import Target
from gumloop.linked_proxy.destinations import connect
from gumloop.linked_proxy.destinations import parse_target


@pytest.mark.parametrize(
    ("hostport", "reason"),
    [
        ("example.com:22", Refusal.PORT),
        ("10.0.0.1:443", Refusal.ADDRESS),
        ("[::1]:443", Refusal.ADDRESS),
        ("127.1:443", Refusal.HOST),
        ("example.com", Refusal.HOST),
    ],
)
def test_parse_target_refuses_what_the_gateway_refuses(hostport: str, reason: Refusal) -> None:
    with pytest.raises(RefusedError) as refused:
        parse_target(hostport)

    assert refused.value.reason is reason


def test_parse_target_accepts_a_hostname_and_a_public_address() -> None:
    assert parse_target("Example.COM.:443") == Target(host="example.com", port=443)
    assert parse_target("93.184.215.14:80") == Target(host="93.184.215.14", port=80)


def test_connect_refuses_a_name_that_resolves_to_a_private_address() -> None:
    with pytest.raises(RefusedError) as refused:
        asyncio.run(connect(Target(host="localhost", port=443)))

    assert refused.value.reason is Refusal.ADDRESS


class _Writer:
    def __init__(self, local: str, remote: str) -> None:
        self._addresses = {"sockname": (local, 50000), "peername": (remote, 443)}
        self.closed = False

    def get_extra_info(self, name: str) -> tuple[str, int]:
        return self._addresses[name]

    def close(self) -> None:
        self.closed = True


def test_connect_refuses_a_public_address_of_this_machine(monkeypatch) -> None:
    writer = _Writer(local="93.184.215.14", remote="93.184.215.14")

    async def open_connection(host: str, port: int) -> tuple[asyncio.StreamReader, _Writer]:
        return asyncio.StreamReader(), writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)

    with pytest.raises(RefusedError) as refused:
        asyncio.run(connect(Target(host="93.184.215.14", port=443)))

    assert refused.value.reason is Refusal.ADDRESS
    assert writer.closed
