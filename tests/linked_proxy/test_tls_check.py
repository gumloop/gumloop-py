from __future__ import annotations

import contextlib
import socket
import ssl
import threading
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import NoEncryption
from cryptography.hazmat.primitives.serialization import PrivateFormat
from cryptography.x509.oid import NameOID

from gumloop.linked_proxy.tls_check import TlsInspected
from gumloop.linked_proxy.tls_check import check_tls_not_inspected


def _privately_signed_server(tmp_path) -> ssl.SSLContext:
    """What a TLS-inspecting proxy presents: a valid certificate for the host from a CA no public root trusts."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    certificate_path, key_path = tmp_path / "server.pem", tmp_path / "server.key"
    certificate_path.write_bytes(certificate.public_bytes(Encoding.PEM))
    key_path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_path, key_path)
    return context


def test_a_certificate_from_a_private_ca_means_inspection(tmp_path):
    context = _privately_signed_server(tmp_path)
    listener = socket.create_server(("127.0.0.1", 0))

    def serve() -> None:
        connection, _ = listener.accept()
        with connection, contextlib.suppress(OSError):
            context.wrap_socket(connection, server_side=True).close()

    server = threading.Thread(target=serve, daemon=True)
    server.start()
    with listener, pytest.raises(TlsInspected):
        check_tls_not_inspected("localhost", listener.getsockname()[1])
    server.join(timeout=5)


def test_an_unreachable_site_is_not_inspection():
    with socket.create_server(("127.0.0.1", 0)) as closed:
        port = closed.getsockname()[1]

    check_tls_not_inspected("127.0.0.1", port)
