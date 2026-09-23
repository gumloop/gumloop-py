from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx
import respx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers import modes
from typer.testing import CliRunner

from gumloop.browser_logins import BrowserKind
from gumloop.browser_logins import LocalProfile
from gumloop.browser_logins import chromium_cookies
from gumloop.browser_logins import discover_profiles
from gumloop.browser_logins import extract_site_cookies
from gumloop.browser_logins.filter import registrable_domain
from gumloop.browser_logins.filter import site_of_url
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

KEY = chromium_cookies.derive_key(b"peanuts", iterations=1)
WEBKIT_2100 = (4_102_444_800 + 11_644_473_600) * 1_000_000
WEBKIT_2000 = (946_684_800 + 11_644_473_600) * 1_000_000


def _encrypt(value: str, host_key: str, *, with_hash: bool = True) -> bytes:
    plain = (hashlib.sha256(host_key.encode()).digest() if with_hash else b"") + value.encode()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + encryptor.update(padded) + encryptor.finalize()


def _make_chrome_profile(user_data: Path, rows: list[tuple]) -> Path:
    profile = user_data / "Default"
    (profile / "Network").mkdir(parents=True)
    (user_data / "Local State").write_text(json.dumps({"profile": {"info_cache": {"Default": {"name": "Person 1"}}}}))
    db = sqlite3.connect(profile / "Network" / "Cookies")
    db.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB, path TEXT, "
        "expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER, samesite INTEGER, has_expires INTEGER, "
        "top_frame_site_key TEXT)"
    )
    db.executemany("INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()
    return profile


def _chrome_rows():
    return [
        (".github.com", "sid", "", _encrypt("secret-1", ".github.com"), "/", WEBKIT_2100, 1, 1, 1, 1, ""),
        ("api.github.com", "plain", "visible", b"", "/", 0, 1, 0, -1, 0, ""),
        (".github.com", "old", "", _encrypt("gone", ".github.com"), "/", WEBKIT_2000, 1, 1, 0, 1, ""),
        (".google.com", "other", "", _encrypt("not-yours", ".google.com"), "/", WEBKIT_2100, 1, 1, 2, 1, ""),
        (".github.com", "broken", "", b"v20" + b"\x00" * 32, "/", WEBKIT_2100, 1, 1, 0, 1, ""),
    ]


def test_registrable_domain_and_site_of_url():
    assert registrable_domain("app.foo.co.uk") == "foo.co.uk"
    assert registrable_domain(".accounts.google.com") == "google.com"
    assert registrable_domain("localhost") == "localhost"
    assert site_of_url("https://gist.github.com/x") == "github.com"


def test_discover_finds_chromium_and_firefox_profiles(tmp_path: Path):
    home = tmp_path
    _make_chrome_profile(home / "Library" / "Application Support" / "Google" / "Chrome", _chrome_rows())
    firefox = home / "Library" / "Application Support" / "Firefox"
    (firefox / "Profiles" / "abc.default-release").mkdir(parents=True)
    (firefox / "Profiles" / "abc.default-release" / "cookies.sqlite").write_bytes(b"")
    (firefox / "profiles.ini").write_text(
        "[Profile0]\nName=default-release\nIsRelative=1\nPath=Profiles/abc.default-release\n"
    )

    profiles = discover_profiles(home=home, platform="darwin")

    assert [(p.browser, p.display_name) for p in profiles] == [
        (BrowserKind.CHROME, "Person 1"),
        (BrowserKind.FIREFOX, "default-release"),
    ]
    cookies_db = profiles[0].cookies_db
    assert cookies_db is not None and cookies_db.name == "Cookies"
    assert discover_profiles(home=home, platform="darwin", browsers=[BrowserKind.BRAVE]) == []


def test_extract_decrypts_only_the_sites_cookies(tmp_path: Path, monkeypatch):
    profile_dir = _make_chrome_profile(tmp_path / "chrome", _chrome_rows())
    monkeypatch.setattr(chromium_cookies, "resolve_key", lambda browser, platform=None: KEY)
    profile = LocalProfile(BrowserKind.CHROME, "Default", "Person 1", profile_dir)

    result = extract_site_cookies(profile, "https://github.com/gumloop", platform="linux")

    by_name = {c["name"]: c for c in result.cookies}
    assert set(by_name) == {"sid", "plain"}
    assert by_name["sid"] == {
        "name": "sid",
        "value": "secret-1",
        "domain": ".github.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "Lax",
        "expires": 4_102_444_800.0,
    }
    assert by_name["plain"]["value"] == "visible" and "expires" not in by_name["plain"]
    assert result.expired == 1 and result.undecryptable == 1
    assert result.per_domain == {".github.com": 1, "api.github.com": 1}


def test_decrypt_value_handles_legacy_values_and_rejects_garbage():
    assert chromium_cookies.decrypt_value(_encrypt("v", "h", with_hash=False), KEY, "h") == "v"
    assert chromium_cookies.decrypt_value(b"v10" + b"\x01" * 16, KEY, "h") is None
    assert chromium_cookies.decrypt_value(b"v20abc", KEY, "h") is None


def test_macos_keychain_denial_is_a_clear_error():
    denied = subprocess.CompletedProcess(args=["security"], returncode=44, stdout="", stderr="")

    try:
        chromium_cookies.macos_safe_storage_password("Chrome Safe Storage", runner=lambda *a, **k: denied)
    except chromium_cookies.KeychainAccessError as error:
        assert "Keychain" in str(error)
    else:
        raise AssertionError("expected KeychainAccessError")


@respx.mock
def test_import_logins_posts_only_site_cookies(cli_runner: CliRunner, tmp_path: Path, monkeypatch):
    profile_dir = _make_chrome_profile(tmp_path / "chrome", _chrome_rows())
    monkeypatch.setattr(chromium_cookies, "resolve_key", lambda browser, platform=None: KEY)
    monkeypatch.setattr(
        "gumloop.cli.commands.browser.discover_profiles",
        lambda browsers=None: [LocalProfile(BrowserKind.CHROME, "Default", "Person 1", profile_dir)],
    )
    route = respx.post(f"{API_BASE}/browser-profiles/default/cookies").mock(
        return_value=httpx.Response(
            200,
            json={
                "profile": {
                    "profile_id": "bp_1",
                    "owner_id": "u",
                    "owner_scope": "personal",
                    "name": "Default",
                    "is_default": True,
                    "version": 1,
                    "sites": [{"domain": "github.com", "cookie_count": 2}],
                },
                "imported": {"site": "github.com", "cookie_count": 2, "skipped": 0, "sites": ["github.com"]},
            },
        )
    )
    save_credentials(Credentials(api_key="key", user_id="u"))

    result = cli_runner.invoke(app, ["browser", "import-logins", "--url", "https://github.com", "--yes"])

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls[0].request.content)
    assert body["url"] == "https://github.com"
    assert sorted(c["name"] for c in body["cookies"]) == ["plain", "sid"]
    assert "secret-1" not in result.output and "Imported 2 cookie(s) for github.com" in result.output


@respx.mock
def test_import_logins_resolves_a_named_team_profile(cli_runner: CliRunner, tmp_path: Path, monkeypatch):
    profile_dir = _make_chrome_profile(tmp_path / "chrome", _chrome_rows())
    monkeypatch.setattr(chromium_cookies, "resolve_key", lambda browser, platform=None: KEY)
    monkeypatch.setattr(
        "gumloop.cli.commands.browser.discover_profiles",
        lambda browsers=None: [LocalProfile(BrowserKind.CHROME, "Default", "Person 1", profile_dir)],
    )
    respx.get(f"{API_BASE}/browser-profiles").mock(
        return_value=httpx.Response(
            200,
            json={
                "profiles": [
                    {"profile_id": "bp_team", "owner_id": "proj", "owner_scope": "team", "name": "Ops", "sites": []},
                ]
            },
        )
    )
    route = respx.post(f"{API_BASE}/browser-profiles/bp_team/cookies").mock(
        return_value=httpx.Response(
            200,
            json={
                "profile": {
                    "profile_id": "bp_team",
                    "owner_id": "proj",
                    "owner_scope": "team",
                    "name": "Ops",
                    "sites": [],
                },
                "imported": {"site": "github.com", "cookie_count": 2, "skipped": 0, "sites": ["github.com"]},
            },
        )
    )
    save_credentials(Credentials(api_key="key", user_id="u"))

    result = cli_runner.invoke(
        app,
        [
            "browser",
            "import-logins",
            "--url",
            "https://github.com",
            "--into",
            "ops",
            "--team",
            "proj",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content)["project_id"] == "proj"


def test_import_logins_with_no_site_cookies_fails_before_any_request(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch
):
    profile_dir = _make_chrome_profile(tmp_path / "chrome", _chrome_rows())
    monkeypatch.setattr(chromium_cookies, "resolve_key", lambda browser, platform=None: KEY)
    monkeypatch.setattr(
        "gumloop.cli.commands.browser.discover_profiles",
        lambda browsers=None: [LocalProfile(BrowserKind.CHROME, "Default", "Person 1", profile_dir)],
    )
    save_credentials(Credentials(api_key="key", user_id="u"))

    result = cli_runner.invoke(app, ["browser", "import-logins", "--url", "https://linear.app", "--yes"])

    assert result.exit_code == 1
    assert "No logins for linear.app" in result.output


@respx.mock
def test_profiles_list_and_remove_site(cli_runner: CliRunner):
    respx.get(f"{API_BASE}/browser-profiles").mock(
        return_value=httpx.Response(
            200,
            json={
                "profiles": [
                    {
                        "profile_id": "bp_1",
                        "owner_id": "u",
                        "owner_scope": "personal",
                        "name": "Default",
                        "is_default": True,
                        "sites": [{"domain": "github.com", "cookie_count": 3}],
                    },
                ]
            },
        )
    )
    removal = respx.delete(f"{API_BASE}/browser-profiles/bp_1/sites/github.com").mock(
        return_value=httpx.Response(
            200,
            json={
                "profile_id": "bp_1",
                "owner_id": "u",
                "owner_scope": "personal",
                "name": "Default",
                "is_default": True,
                "sites": [],
            },
        )
    )
    save_credentials(Credentials(api_key="key", user_id="u"))

    listed = cli_runner.invoke(app, ["browser", "profiles", "list"])
    assert listed.exit_code == 0 and "github.com" in listed.output

    removed = cli_runner.invoke(app, ["browser", "profiles", "remove-site", "bp_1", "github.com"])
    assert removed.exit_code == 0 and removal.called
