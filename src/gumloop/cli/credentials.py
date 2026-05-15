"""Keychain-backed credential storage. No file fallback - ``save_credentials``
raises if the OS keychain is unavailable."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields

import keyring
import keyring.backends.fail
import keyring.errors

from gumloop import GumloopError

KEYRING_SERVICE = "gumloop-cli"
DEFAULT_PROFILE = "default"


@dataclass
class Credentials:
    access_token: str | None = None
    refresh_token: str | None = None
    api_key: str | None = None
    # Required for API key auth; sent as the ``x-auth-key`` header.
    user_id: str | None = None
    # Backend the credentials were issued against. ``None`` = SDK default.
    base_url: str | None = None

    @property
    def bearer_token(self) -> str | None:
        return self.access_token or self.api_key

    @property
    def has_any(self) -> bool:
        return bool(self.bearer_token)

    @property
    def auth_method(self) -> str | None:
        """``access_token`` wins over a residual ``api_key``."""
        if self.access_token:
            return "oauth"
        if self.api_key:
            return "api_key"
        return None


_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Credentials))


def _account(profile: str, field: str) -> str:
    return f"{profile}:{field}"


def keyring_backend_name() -> str:
    backend = keyring.get_keyring()
    return getattr(backend, "name", backend.__class__.__name__)


def is_keyring_available() -> bool:
    return not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring)


def _require_keyring() -> None:
    if is_keyring_available():
        return
    raise GumloopError(
        "No OS keychain backend is available on this machine. The Gumloop "
        "CLI refuses to store credentials in a plaintext file.\n"
        "\n"
        "  macOS:    the system Keychain should always be available.\n"
        "  Linux:    install one of:\n"
        "              apt install gnome-keyring libsecret-1-0\n"
        "              apt install kwalletmanager\n"
        "  Headless: pass credentials per-invocation via\n"
        "            GUMLOOP_ACCESS_TOKEN / GUMLOOP_API_KEY (+ GUMLOOP_USER_ID)\n"
        "            instead of running `gumloop login`."
    )


def load_credentials(profile: str = DEFAULT_PROFILE) -> Credentials:
    """Best-effort load. Returns an empty ``Credentials`` when no keychain so
    the env-var-only path and ``gumloop --help`` still work on bare boxes."""
    if not is_keyring_available():
        return Credentials()
    values: dict[str, str | None] = {
        field: keyring.get_password(KEYRING_SERVICE, _account(profile, field)) for field in _FIELDS
    }
    return Credentials(**values)


def save_credentials(creds: Credentials, profile: str = DEFAULT_PROFILE) -> None:
    """Persist ``creds``. Fields set to ``None`` delete their keychain entry."""
    _require_keyring()
    for field in _FIELDS:
        value = getattr(creds, field)
        account = _account(profile, field)
        if value:
            keyring.set_password(KEYRING_SERVICE, account, value)
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, account)
            except keyring.errors.PasswordDeleteError:
                pass


def clear_credentials(profile: str = DEFAULT_PROFILE) -> None:
    """Delete every keychain entry for ``profile``. Best-effort; never raises."""
    if not is_keyring_available():
        return
    for field in _FIELDS:
        try:
            keyring.delete_password(KEYRING_SERVICE, _account(profile, field))
        except keyring.errors.PasswordDeleteError:
            pass
