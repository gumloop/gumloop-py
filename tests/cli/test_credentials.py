from __future__ import annotations

import keyring
import keyring.backends.fail
import pytest

from gumloop import GumloopError
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import clear_credentials
from gumloop.cli.credentials import load_credentials
from gumloop.cli.credentials import save_credentials


def test_bearer_token_prefers_access_token_over_api_key() -> None:
    assert Credentials(access_token="tok", api_key="key").bearer_token == "tok"
    assert Credentials(api_key="key").bearer_token == "key"
    assert Credentials().bearer_token is None
    assert not Credentials().has_any
    assert Credentials(api_key="key").has_any


def test_auth_method_is_derived_from_cred_presence() -> None:
    assert Credentials(access_token="tok").auth_method == "oauth"
    assert Credentials(api_key="key").auth_method == "api_key"
    assert Credentials(access_token="tok", api_key="key").auth_method == "oauth"
    assert Credentials().auth_method is None


def test_keyring_round_trip_persists_every_field() -> None:
    save_credentials(
        Credentials(
            access_token="tok",
            refresh_token="ref",
            api_key="key",
            user_id="user_abc",
            base_url="https://example.com/api/v1",
        )
    )

    loaded = load_credentials()
    assert loaded.access_token == "tok"
    assert loaded.refresh_token == "ref"
    assert loaded.api_key == "key"
    assert loaded.user_id == "user_abc"
    assert loaded.base_url == "https://example.com/api/v1"


def test_keyring_save_clears_fields_set_to_none() -> None:
    save_credentials(Credentials(access_token="tok", refresh_token="ref"))
    save_credentials(Credentials(access_token="tok2", refresh_token=None))

    loaded = load_credentials()
    assert loaded.access_token == "tok2"
    assert loaded.refresh_token is None


def test_profiles_are_isolated_in_keyring() -> None:
    save_credentials(Credentials(access_token="alice"), profile="alice")
    save_credentials(Credentials(access_token="bob"), profile="bob")

    assert load_credentials(profile="alice").access_token == "alice"
    assert load_credentials(profile="bob").access_token == "bob"
    assert load_credentials(profile="default").access_token is None


def test_clear_credentials_wipes_every_field() -> None:
    save_credentials(
        Credentials(
            access_token="tok",
            refresh_token="ref",
            api_key="key",
            user_id="u",
            base_url="https://x/api/v1",
        )
    )
    clear_credentials()

    loaded = load_credentials()
    assert loaded.access_token is None
    assert loaded.refresh_token is None
    assert loaded.api_key is None
    assert loaded.user_id is None
    assert loaded.base_url is None


def test_save_raises_when_no_keychain_backend_available() -> None:
    """No file fallback: refusing to persist secrets is the whole point."""
    previous = keyring.get_keyring()
    keyring.set_keyring(keyring.backends.fail.Keyring())
    try:
        with pytest.raises(GumloopError, match="No OS keychain"):
            save_credentials(Credentials(access_token="tok"))
    finally:
        keyring.set_keyring(previous)


def test_load_returns_empty_credentials_when_no_keychain() -> None:
    """`gumloop --help` and env-only paths must still work on bare boxes."""
    previous = keyring.get_keyring()
    keyring.set_keyring(keyring.backends.fail.Keyring())
    try:
        loaded = load_credentials()
        assert not loaded.has_any
    finally:
        keyring.set_keyring(previous)
