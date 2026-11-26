"""This machine's personal proxy on one backend: the Ed25519 key it signs in to the
linked proxy gateway with, kept in the OS keychain, the personal proxy that key
registered as, and whether its tunnel is connected."""

from __future__ import annotations

import base64
import os
from datetime import datetime
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


class CustomProxyRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    custom_proxy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    gateway_url: str = Field(min_length=1)
    # The key it registered, which the keychain no longer has if it was reset.
    public_key: str = Field(min_length=1)
    # The Gumloop user who linked it; None when their login didn't say.
    user_id: str | None = None

    @field_validator("gateway_url")
    @classmethod
    def _require_encrypted_gateway(cls, gateway_url: str) -> str:
        """Over plain ws:// the sign-in token and the tunnelled traffic are readable on the network."""
        parts = urlsplit(gateway_url)
        if parts.scheme == "wss" or (parts.scheme == "ws" and parts.hostname in _LOOPBACK_HOSTS):
            return gateway_url
        raise ValueError("the linked proxy gateway must use wss:// unless it runs on this computer")


class CustomProxyConnectionStatus(BaseModel):
    """Written by the running personal proxy; stale once it no longer holds the lock."""

    model_config = ConfigDict(extra="forbid")

    connected: bool
    # When this status was recorded: the connect, or the start of the current attempt or failure.
    since: datetime
    last_error: str | None = None


def backend_host(base_url: str) -> str:
    """Each backend gets its own key and registration, so staging and production never share one."""
    return urlsplit(base_url).netloc


def load_or_create_key(host: str) -> Ed25519PrivateKey:
    key = load_key(host)
    if key is not None:
        return key
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    try:
        keyring.set_password(KEYRING_SERVICE, _key_account(host), base64.urlsafe_b64encode(raw).decode())
    except keyring.errors.KeyringError as error:
        raise GumloopError(f"Could not use the personal proxy key in the OS keychain: {error}") from error
    return key


def load_key(host: str) -> Ed25519PrivateKey | None:
    """None when the keychain has no key for this backend."""
    require_keyring()
    try:
        stored = keyring.get_password(KEYRING_SERVICE, _key_account(host))
    except keyring.errors.KeyringError as error:
        raise GumloopError(f"Could not use the personal proxy key in the OS keychain: {error}") from error
    if stored is None:
        return None
    try:
        return Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(stored))
    except ValueError as error:
        raise GumloopError(f"The personal proxy key for {host} in the OS keychain is unreadable.") from error


def load_registration(host: str, home: Path | None = None) -> CustomProxyRegistration | None:
    try:
        return CustomProxyRegistration.model_validate_json(_registration_path(host, home).read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def save_registration(host: str, registration: CustomProxyRegistration, home: Path | None = None) -> None:
    _write_private(_registration_path(host, home), registration.model_dump_json())


def forget_registration(host: str, home: Path | None = None) -> None:
    _registration_path(host, home).unlink(missing_ok=True)


def load_connection_status(host: str, home: Path | None = None) -> CustomProxyConnectionStatus | None:
    try:
        return CustomProxyConnectionStatus.model_validate_json(_status_path(host, home).read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def save_connection_status(host: str, status: CustomProxyConnectionStatus, home: Path | None = None) -> None:
    _write_private(_status_path(host, home), status.model_dump_json())


def forget_connection_status(host: str, home: Path | None = None) -> None:
    _status_path(host, home).unlink(missing_ok=True)


def forget(host: str, home: Path | None = None) -> None:
    """Deletes the key, the registration and the connection status. The personal proxy
    stays in Gumloop until it is deleted there."""
    try:
        keyring.delete_password(KEYRING_SERVICE, _key_account(host))
    except keyring.errors.PasswordDeleteError:
        pass
    except keyring.errors.KeyringError as error:
        raise GumloopError(f"Could not delete the personal proxy key from the OS keychain: {error}") from error
    forget_registration(host, home)
    forget_connection_status(host, home)


def _key_account(host: str) -> str:
    return f"custom-proxy:{host}"


def _write_private(destination: Path, text: str) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.tmp")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)
    staging.replace(destination)


def _registration_path(host: str, home: Path | None) -> Path:
    return (home or Path.home()) / ".gumloop" / "custom-proxy" / f"{host}.json"


def _status_path(host: str, home: Path | None) -> Path:
    return (home or Path.home()) / ".gumloop" / "custom-proxy" / f"{host}.status.json"
