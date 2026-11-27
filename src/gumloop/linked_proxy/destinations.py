"""Which destinations the tunnel may connect to. These are the linked proxy gateway's
own checks, applied again here because names resolve on this machine, whose
network may route ranges the gateway can't see."""

from __future__ import annotations

import asyncio
import enum
import ipaddress
import re
import socket
import string
from dataclasses import dataclass

ALLOWED_PORTS = frozenset({80, 443})
DIAL_TIMEOUT_SECONDS = 10.0

# Special-use IPv4 ranges (RFC 6890) that the linked proxy gateway also refuses.
_DENIED_NETWORKS = tuple(
    ipaddress.IPv4Network(network)
    for network in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "0.0.0.0/8",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "240.0.0.0/4",
        # Azure's host endpoint, which answers VMs on that public address.
        "168.63.129.16/32",
    )
)
_PORT = re.compile(r"[0-9]+")
_LABEL_CHARACTERS = frozenset(string.ascii_lowercase + string.digits + "-_")


class Refusal(str, enum.Enum):
    PORT = "port"
    ADDRESS = "address"
    HOST = "host"


class RefusedError(Exception):
    """A destination the tunnel may not reach. It never carries the destination."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(f"destination refused: {reason.value}")
        self.reason = reason


@dataclass(frozen=True)
class Target:
    """A lower-case hostname, or a public IPv4 literal, on port 80 or 443."""

    host: str
    port: int


def parse_target(hostport: str) -> Target:
    host, separator, port_text = hostport.rpartition(":")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    elif ":" in host:
        raise RefusedError(Refusal.HOST)
    if not separator or not host:
        raise RefusedError(Refusal.HOST)
    if not _PORT.fullmatch(port_text) or int(port_text) not in ALLOWED_PORTS:
        raise RefusedError(Refusal.PORT)
    port = int(port_text)

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if not is_public_ipv4(address):
            raise RefusedError(Refusal.ADDRESS)
        return Target(host=str(_unmap(address)), port=port)

    host = host.lower().removesuffix(".")
    if not _is_hostname(host):
        raise RefusedError(Refusal.HOST)

    return Target(host=host, port=port)


def is_public_ipv4(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    address = _unmap(address)
    if not isinstance(address, ipaddress.IPv4Address):
        return False
    if address.is_multicast or address == ipaddress.IPv4Address("255.255.255.255"):
        return False

    return not any(address in network for network in _DENIED_NETWORKS)


def _unmap(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_hostname(host: str) -> bool:
    """DNS names only. A last label of digits is refused because some resolvers
    read names like "2130706433" or "127.1" as addresses."""
    if not host or len(host) > 253:
        return False
    labels = host.split(".")
    for label in labels:
        if not label or len(label) > 63 or label[0] == "-" or label[-1] == "-":
            return False
        if not set(label) <= _LABEL_CHARACTERS:
            return False

    return labels[-1].strip(string.digits) != ""


async def connect(target: Target) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Resolves the target here, refuses it if any address is not public, then
    tries the addresses in the resolver's order."""
    addresses = await _resolve(target)
    errors: list[OSError] = []
    for address in addresses:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(address, target.port), DIAL_TIMEOUT_SECONDS)
        except (OSError, asyncio.TimeoutError) as error:
            errors.append(error if isinstance(error, OSError) else TimeoutError("dial timed out"))
            continue
        if _reaches_this_machine(writer):
            writer.close()
            raise RefusedError(Refusal.ADDRESS)
        return reader, writer

    raise OSError(f"could not connect to any of {len(addresses)} addresses") from (errors[-1] if errors else None)


def _reaches_this_machine(writer: asyncio.StreamWriter) -> bool:
    """A public address on one of this machine's own interfaces, such as a VPS's, would reach its local services."""
    local = writer.get_extra_info("sockname")
    remote = writer.get_extra_info("peername")
    return local is not None and remote is not None and local[0] == remote[0]


async def _resolve(target: Target) -> list[str]:
    try:
        literal = ipaddress.ip_address(target.host)
    except ValueError:
        literal = None
    if literal is not None:
        candidates = [literal]
    else:
        infos = await asyncio.get_running_loop().getaddrinfo(
            target.host, target.port, family=socket.AF_INET, type=socket.SOCK_STREAM
        )
        candidates = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not candidates:
        raise OSError("no IPv4 addresses for the target")

    addresses: list[str] = []
    for candidate in candidates:
        if not is_public_ipv4(candidate):
            raise RefusedError(Refusal.ADDRESS)
        text = str(_unmap(candidate))
        if text not in addresses:
            addresses.append(text)

    return addresses
