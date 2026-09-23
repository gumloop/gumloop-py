from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers import modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from gumloop.browser_logins.discovery import BrowserKind

_SALT = b"saltysalt"
_IV = b" " * 16
_KEY_LENGTH = 16
_MAC_ITERATIONS = 1003
_LINUX_ITERATIONS = 1
_LINUX_DEFAULT_PASSWORD = b"peanuts"
_WEBKIT_EPOCH_OFFSET_US = 11_644_473_600 * 1_000_000
_SAME_SITE = {0: "None", 1: "Lax", 2: "Strict"}

_QUERY = (
    "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, "
    "samesite, has_expires, top_frame_site_key FROM cookies"
)
_LEGACY_QUERY = (
    "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, "
    "samesite, has_expires, '' FROM cookies"
)


class KeychainAccessError(RuntimeError):
    """The OS refused to hand over the browser's cookie encryption key."""


@dataclass
class ChromiumReadResult:
    cookies: list[dict[str, Any]]
    undecryptable: int = 0


def macos_safe_storage_password(
    service: str, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> bytes:
    completed = runner(
        ["security", "find-generic-password", "-w", "-s", service],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise KeychainAccessError(
            f"macOS Keychain did not release the '{service}' key (was the prompt denied?). "
            "Allow access when macOS asks, or use the Gumloop Chrome extension instead."
        )
    return completed.stdout.strip().encode("utf-8")


def linux_safe_storage_password(service: str) -> bytes:
    try:
        import secretstorage  # type: ignore[import-not-found]  # noqa: PLC0415 - optional, desktop-only dependency

        connection = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(connection)
        for item in collection.get_all_items():
            if item.get_label() == service:
                secret = item.get_secret()
                if secret:
                    return bytes(secret)
    except Exception:  # noqa: BLE001 - no bus, no keyring, no secretstorage: fall back to the default key
        pass
    return _LINUX_DEFAULT_PASSWORD


def derive_key(password: bytes, *, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=_KEY_LENGTH, salt=_SALT, iterations=iterations)
    return kdf.derive(password)


def resolve_key(browser: BrowserKind, *, platform: str | None = None) -> bytes:
    platform = platform or sys.platform
    if platform == "darwin":
        return derive_key(macos_safe_storage_password(browser.safe_storage_service), iterations=_MAC_ITERATIONS)
    return derive_key(linux_safe_storage_password(browser.safe_storage_service), iterations=_LINUX_ITERATIONS)


def decrypt_value(encrypted: bytes, key: bytes, host_key: str) -> str | None:
    """Chrome 130+ prefixes the plaintext with SHA-256(host_key)."""
    if len(encrypted) < 3:
        return None
    prefix, body = encrypted[:3], encrypted[3:]
    if prefix not in (b"v10", b"v11"):
        return None
    if len(body) % 16 != 0 or not body:
        return None
    decryptor = Cipher(algorithms.AES(key), modes.CBC(_IV)).decryptor()
    padded = decryptor.update(body) + decryptor.finalize()
    pad = padded[-1]
    if pad < 1 or pad > 16 or padded[-pad:] != bytes([pad]) * pad:
        return None
    plain = padded[:-pad]
    host_hash = hashlib.sha256(host_key.encode("utf-8")).digest()
    if plain[:32] == host_hash:
        plain = plain[32:]
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _webkit_to_unix(expires_utc: int) -> float | None:
    if not expires_utc:
        return None
    return (expires_utc - _WEBKIT_EPOCH_OFFSET_US) / 1_000_000


def copy_database(db_path: Path) -> tuple[Path, Path]:
    """Copy the database (and its journal/WAL) so a running browser's lock does not matter."""
    temp_dir = Path(tempfile.mkdtemp(prefix="gumloop-cookies-"))
    copied = temp_dir / db_path.name
    shutil.copy2(db_path, copied)
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, temp_dir / sidecar.name)
    return temp_dir, copied


def read_cookies(db_path: Path, key: bytes | None, *, keep: Callable[[str], bool] | None = None) -> ChromiumReadResult:
    """Cookies as CDP ``CookieParam``-shaped dicts; ``keep(host_key)`` filters before any value is decrypted."""
    temp_dir, copied = copy_database(db_path)
    try:
        connection = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
        try:
            try:
                rows = connection.execute(_QUERY).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute(_LEGACY_QUERY).fetchall()
        finally:
            connection.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    cookies: list[dict[str, Any]] = []
    undecryptable = 0
    for (
        host_key,
        name,
        value,
        encrypted_value,
        path,
        expires_utc,
        is_secure,
        is_httponly,
        samesite,
        has_expires,
        top_frame,
    ) in rows:
        if keep is not None and not keep(host_key):
            continue
        plain = value or ""
        if not plain and encrypted_value:
            decrypted = decrypt_value(bytes(encrypted_value), key, host_key) if key is not None else None
            if decrypted is None:
                undecryptable += 1
                continue
            plain = decrypted
        cookie: dict[str, Any] = {
            "name": name,
            "value": plain,
            "domain": host_key,
            "path": path or "/",
            "secure": bool(is_secure),
            "httpOnly": bool(is_httponly),
        }
        same_site = _SAME_SITE.get(samesite)
        if same_site:
            cookie["sameSite"] = same_site
        if has_expires:
            expires = _webkit_to_unix(expires_utc)
            if expires:
                cookie["expires"] = expires
        if top_frame:
            cookie["partitionKey"] = {"topLevelSite": top_frame}
        cookies.append(cookie)
    return ChromiumReadResult(cookies=cookies, undecryptable=undecryptable)
