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
from gumloop.browser_logins import extract_profile_cookies
from gumloop.browser_logins import extract_site_cookies
from gumloop.browser_logins.filter import registrable_domain
from gumloop.browser_logins.filter import site_of_url
from gumloop.cli.commands import browser as browser_command
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


def test_extract_profile_cookies_takes_every_site_and_honours_domain_filters(tmp_path: Path, monkeypatch):
    profile_dir = _make_chrome_profile(tmp_path / "chrome", _chrome_rows())
    monkeypatch.setattr(chromium_cookies, "resolve_key", lambda browser, platform=None: KEY)
    profile = LocalProfile(BrowserKind.CHROME, "Default", "Person 1", profile_dir)

    everything = extract_profile_cookies(profile, platform="linux")
    assert everything.site is None
    assert sorted(c["name"] for c in everything.cookies) == ["other", "plain", "sid"]
    assert everything.per_site == {"github.com": 2, "google.com": 1}
    assert everything.expired == 1 and everything.undecryptable == 1

    only_google = extract_profile_cookies(profile, include=["google.com"], platform="linux")
    assert [c["name"] for c in only_google.cookies] == ["other"]

    without_google = extract_profile_cookies(profile, exclude=[".google.com"], platform="linux")
    assert sorted(c["name"] for c in without_google.cookies) == ["plain", "sid"]


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
    assert json.loads(route.calls[0].request.content)["team_id"] == "proj"


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
    assert "No cookies for linear.app" in result.output


@respx.mock
def test_profiles_list(cli_runner: CliRunner):
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
    save_credentials(Credentials(api_key="key", user_id="u"))

    listed = cli_runner.invoke(app, ["browser", "profiles", "list"])
    assert listed.exit_code == 0 and "github.com" in listed.output


def _import_response(profile_id: str, *, site: str | None, cookie_count: int, sites: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "profile": {
                "profile_id": profile_id,
                "owner_id": "u",
                "owner_scope": "personal",
                "name": "Default",
                "is_default": True,
                "version": 1,
                "sites": [{"domain": s, "cookie_count": 1} for s in sites],
            },
            "imported": {"site": site, "cookie_count": cookie_count, "skipped": 0, "sites": sites},
        },
    )


def _patch_local_chrome(tmp_path: Path, monkeypatch) -> None:
    profile_dir = _make_chrome_profile(tmp_path / "chrome", _chrome_rows())
    monkeypatch.setattr(chromium_cookies, "resolve_key", lambda browser, platform=None: KEY)
    monkeypatch.setattr(
        "gumloop.cli.commands.browser.discover_profiles",
        lambda browsers=None: [LocalProfile(BrowserKind.CHROME, "Default", "Person 1", profile_dir)],
    )


@respx.mock
def test_import_logins_without_url_posts_every_site(cli_runner: CliRunner, tmp_path: Path, monkeypatch):
    _patch_local_chrome(tmp_path, monkeypatch)
    route = respx.post(f"{API_BASE}/browser-profiles/default/cookies").mock(
        return_value=_import_response("bp_1", site=None, cookie_count=3, sites=["github.com", "google.com"])
    )
    save_credentials(Credentials(api_key="key", user_id="u"))

    result = cli_runner.invoke(app, ["browser", "import-logins", "--yes"])

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls[0].request.content)
    assert "url" not in body
    assert sorted(c["name"] for c in body["cookies"]) == ["other", "plain", "sid"]
    assert "across 2 site(s)" in result.output
    assert "secret-1" not in result.output and "not-yours" not in result.output


@respx.mock
def test_import_logins_uploads_a_large_profile_in_chunks(cli_runner: CliRunner, tmp_path: Path, monkeypatch):
    _patch_local_chrome(tmp_path, monkeypatch)
    monkeypatch.setattr(browser_command, "_IMPORT_CHUNK", 2)
    first = respx.post(f"{API_BASE}/browser-profiles/default/cookies").mock(
        return_value=_import_response("bp_1", site=None, cookie_count=2, sites=["github.com"])
    )
    second = respx.post(f"{API_BASE}/browser-profiles/bp_1/cookies").mock(
        return_value=_import_response("bp_1", site=None, cookie_count=1, sites=["google.com"])
    )
    save_credentials(Credentials(api_key="key", user_id="u"))

    result = cli_runner.invoke(app, ["browser", "import-logins", "--yes"])

    assert result.exit_code == 0, result.output
    assert first.call_count == 1 and second.call_count == 1
    assert "Imported 3 cookie(s) across 2 site(s)" in result.output


def test_import_logins_rejects_url_with_domain_filters(cli_runner: CliRunner):
    result = cli_runner.invoke(
        app, ["browser", "import-logins", "--url", "https://github.com", "--include-domain", "github.com", "--yes"]
    )
    assert result.exit_code == 1
    assert "--include-domain" in result.output
