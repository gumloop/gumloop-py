"""Read a Firefox ``cookies.sqlite`` (values are stored in the clear)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from gumloop.browser_logins.chromium_cookies import copy_database

_SAME_SITE = {0: "None", 1: "Lax", 2: "Strict"}
_QUERY = "SELECT host, name, value, path, expiry, isSecure, isHttpOnly, sameSite FROM moz_cookies"


def read_cookies(db_path: Path) -> list[dict[str, Any]]:
    temp_dir, copied = copy_database(db_path)
    try:
        connection = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
        try:
            rows = connection.execute(_QUERY).fetchall()
        finally:
            connection.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    cookies: list[dict[str, Any]] = []
    for host, name, value, path, expiry, is_secure, is_http_only, same_site in rows:
        cookie: dict[str, Any] = {
            "name": name,
            "value": value or "",
            "domain": host,
            "path": path or "/",
            "secure": bool(is_secure),
            "httpOnly": bool(is_http_only),
        }
        if _SAME_SITE.get(same_site):
            cookie["sameSite"] = _SAME_SITE[same_site]
        if expiry:
            cookie["expires"] = float(expiry)
        cookies.append(cookie)
    return cookies
