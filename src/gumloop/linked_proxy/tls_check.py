"""Whether this network inspects TLS. A proxy that re-signs traffic with its own
CA would show the agent's browser a certificate error on every site."""

from __future__ import annotations

import functools
import socket
import ssl

import certifi

CHECK_HOST = "example.com"
_TIMEOUT_SECONDS = 5.0


class TlsInspected(Exception):
    """A public site's certificate did not chain to a public CA."""


@functools.cache
def tls_context() -> ssl.SSLContext:
    """Trusts certifi's roots only: a CA that inspection software adds to the OS store must not pass."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def check_tls_not_inspected(host: str = CHECK_HOST, port: int = 443) -> None:
    """Raises ``TlsInspected`` on a certificate error. Any other failure passes,
    since the tunnel keeps retrying until the network is back."""
    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT_SECONDS) as raw:
            with tls_context().wrap_socket(raw, server_hostname=host):
                pass
    except ssl.SSLCertVerificationError as error:
        raise TlsInspected(error.verify_message) from error
    except OSError:
        return
