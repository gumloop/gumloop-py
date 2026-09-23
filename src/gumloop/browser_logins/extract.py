"""One site's cookies from one local profile, ready for the import endpoint."""

from __future__ import annotations

import time
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from gumloop.browser_logins import chromium_cookies
from gumloop.browser_logins import firefox_cookies
from gumloop.browser_logins.discovery import BrowserKind
from gumloop.browser_logins.discovery import LocalProfile
from gumloop.browser_logins.filter import cookie_belongs_to_site
from gumloop.browser_logins.filter import site_of_url


@dataclass
class ExtractResult:
    site: str
    cookies: list[dict[str, Any]] = field(default_factory=list)
    undecryptable: int = 0
    expired: int = 0

    @property
    def per_domain(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cookie in self.cookies:
            counts[cookie["domain"]] = counts.get(cookie["domain"], 0) + 1
        return dict(sorted(counts.items()))


def extract_site_cookies(profile: LocalProfile, url: str, *, platform: str | None = None) -> ExtractResult:
    """Never returns values for other sites; they are dropped before the result exists."""
    site = site_of_url(url)
    db_path = profile.cookies_db
    if db_path is None:
        raise FileNotFoundError(f"{profile.label} has no cookie database")

    if profile.browser is BrowserKind.FIREFOX:
        all_cookies = firefox_cookies.read_cookies(db_path)
        undecryptable = 0
    else:
        key = chromium_cookies.resolve_key(profile.browser, platform=platform)
        read = chromium_cookies.read_cookies(db_path, key, keep=lambda host: cookie_belongs_to_site(host, site))
        all_cookies, undecryptable = read.cookies, read.undecryptable

    now = time.time()
    kept: list[dict[str, Any]] = []
    expired = 0
    for cookie in all_cookies:
        if not cookie_belongs_to_site(cookie["domain"], site):
            continue
        expires = cookie.get("expires")
        if isinstance(expires, (int, float)) and expires <= now:
            expired += 1
            continue
        kept.append(cookie)
    return ExtractResult(site=site, cookies=kept, undecryptable=undecryptable, expired=expired)
