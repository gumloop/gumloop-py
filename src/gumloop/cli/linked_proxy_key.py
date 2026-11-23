"""This machine's linked proxy on one backend: the Ed25519 key it signs in to the
linked proxy gateway with, kept in the OS keychain, and the linked proxy that key
registered as."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from urllib.parse import urlsplit

import keyring
import keyring.errors
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import NoEncryption
from cryptography.hazmat.primitives.serialization import PrivateFormat
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError
from pydantic import field_validator

from gumloop import GumloopError
from gumloop.cli.credentials import KEYRING_SERVICE
from gumloop.cli.credentials import require_keyring

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class LinkedProxyRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linked_proxy_id: str = Field(min_length=1)
    gateway_url: str = Field(min_length=1)

    @field_validator("gateway_url")
    @classmethod
    def _require_encrypted_gateway(cls, gateway_url: str) -> str:
        """Over plain ws:// the sign-in token and the tunnelled traffic are readable on the network."""
        parts = urlsplit(gateway_url)
        if parts.scheme == "wss" or (parts.scheme == "ws" and parts.hostname in _LOOPBACK_HOSTS):
            return gateway_url
        raise ValueError("the linked proxy gateway must use wss:// unless it runs on this computer")


def backend_host(base_url: str) -> str:
    """Each backend gets its own key and registration, so staging and production never share one."""
    return urlsplit(base_url).netloc


def load_or_create_key(host: str) -> Ed25519PrivateKey:
    require_keyring()
    account = _key_account(host)
    try:
        stored = keyring.get_password(KEYRING_SERVICE, account)
        if stored is None:
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            keyring.set_password(KEYRING_SERVICE, account, base64.urlsafe_b64encode(raw).decode())
            return key
    except keyring.errors.KeyringError as error:
        raise GumloopError(f"Could not use the linked proxy key in the OS keychain: {error}") from error
    try:
        return Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(stored))
    except ValueError as error:
        raise GumloopError(f"The linked proxy key for {host} in the OS keychain is unreadable.") from error


def load_registration(host: str, home: Path | None = None) -> LinkedProxyRegistration | None:
    try:
        return LinkedProxyRegistration.model_validate_json(_registration_path(host, home).read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def save_registration(host: str, registration: LinkedProxyRegistration, home: Path | None = None) -> None:
    destination = _registration_path(host, home)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.tmp")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(registration.model_dump_json())
    os.replace(staging, destination)


def _key_account(host: str) -> str:
    return f"linked-proxy:{host}"


def _registration_path(host: str, home: Path | None) -> Path:
    return (home or Path.home()) / ".gumloop" / "linked-proxy" / f"{host}.json"
