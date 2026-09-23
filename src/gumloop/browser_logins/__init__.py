"""Read logins (cookies) out of the browsers installed on this machine.

The equivalent of Browser Use's ``profile-use``: copy the browser's cookie database, decrypt it
with the OS keychain, keep the cookies for one site, and hand them to the Gumloop API so an
agent's sandbox browser starts logged in. Cookie values never leave this process except in
that request.
"""

from __future__ import annotations

from gumloop.browser_logins.discovery import BrowserKind
from gumloop.browser_logins.discovery import LocalProfile
from gumloop.browser_logins.discovery import discover_profiles
from gumloop.browser_logins.extract import ExtractResult
from gumloop.browser_logins.extract import extract_site_cookies
from gumloop.browser_logins.filter import site_of_url

__all__ = [
    "BrowserKind",
    "ExtractResult",
    "LocalProfile",
    "discover_profiles",
    "extract_site_cookies",
    "site_of_url",
]
