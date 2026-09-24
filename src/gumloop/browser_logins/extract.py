from __future__ import annotations

import time
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from gumloop.browser_logins import chromium_cookies
from gumloop.browser_logins import firefox_cookies
from gumloop.browser_logins.discovery import BrowserKind
from gumloop.browser_logins.discovery import LocalProfile
from gumloop.browser_logins.filter import cookie_belongs_to_site
from gumloop.browser_logins.filter import registrable_domain
from gumloop.browser_logins.filter import site_of_url


@dataclass
class ExtractResult:
    site: str | None
    cookies: list[dict[str, Any]] = field(default_factory=list)
    undecryptable: int = 0
    expired: int = 0

    @property
    def per_domain(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cookie in self.cookies:
            counts[cookie["domain"]] = counts.get(cookie["domain"], 0) + 1

        return dict(sorted(counts.items()))

    @property
    def per_site(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cookie in self.cookies:
            site = registrable_domain(cookie["domain"])
            counts[site] = counts.get(site, 0) + 1

        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def extract_site_cookies(profile: LocalProfile, url: str, *, platform: str | None = None) -> ExtractResult:
    site = site_of_url(url)
    return _extract(profile, site=site, keep=lambda host: cookie_belongs_to_site(host, site), platform=platform)


def extract_profile_cookies(
    profile: LocalProfile,
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
    platform: str | None = None,
) -> ExtractResult:
    included = _normalized_domains(include)
    excluded = _normalized_domains(exclude)

    def keep(host: str) -> bool:
        if any(cookie_belongs_to_site(host, domain) for domain in excluded):
            return False

        return not included or any(cookie_belongs_to_site(host, domain) for domain in included)

    return _extract(profile, site=None, keep=keep, platform=platform)


def _normalized_domains(domains: Iterable[str]) -> list[str]:
    return [domain.strip().lower().lstrip(".") for domain in domains if domain and domain.strip()]


def _extract(
    profile: LocalProfile,
    *,
    site: str | None,
    keep: Callable[[str], bool],
    platform: str | None,
) -> ExtractResult:
    db_path = profile.cookies_db
    if db_path is None:
        raise FileNotFoundError(f"{profile.label} has no cookie database")

    if profile.browser is BrowserKind.FIREFOX:
        all_cookies = firefox_cookies.read_cookies(db_path)
        undecryptable = 0
    else:
        key = chromium_cookies.resolve_key(profile.browser, platform=platform)
        read = chromium_cookies.read_cookies(db_path, key, keep=keep)
        all_cookies, undecryptable = read.cookies, read.undecryptable

    now = time.time()
    kept: list[dict[str, Any]] = []
    expired = 0
    for cookie in all_cookies:
        if not keep(cookie["domain"]):
            continue

        expires = cookie.get("expires")
        if isinstance(expires, (int, float)) and expires <= now:
            expired += 1
            continue

        kept.append(cookie)

    return ExtractResult(site=site, cookies=kept, undecryptable=undecryptable, expired=expired)
