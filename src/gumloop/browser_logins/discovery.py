"""Find browser profiles on this machine (macOS and Linux)."""

from __future__ import annotations

import configparser
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class BrowserKind(str, Enum):
    CHROME = "chrome"
    CHROMIUM = "chromium"
    BRAVE = "brave"
    EDGE = "edge"
    ARC = "arc"
    FIREFOX = "firefox"

    @property
    def is_chromium(self) -> bool:
        return self is not BrowserKind.FIREFOX

    @property
    def display_name(self) -> str:
        return {
            BrowserKind.CHROME: "Google Chrome",
            BrowserKind.CHROMIUM: "Chromium",
            BrowserKind.BRAVE: "Brave",
            BrowserKind.EDGE: "Microsoft Edge",
            BrowserKind.ARC: "Arc",
            BrowserKind.FIREFOX: "Firefox",
        }[self]

    @property
    def safe_storage_service(self) -> str:
        """The macOS Keychain item (and Linux Secret Service label) holding the cookie key."""
        return {
            BrowserKind.CHROME: "Chrome Safe Storage",
            BrowserKind.CHROMIUM: "Chromium Safe Storage",
            BrowserKind.BRAVE: "Brave Safe Storage",
            BrowserKind.EDGE: "Microsoft Edge Safe Storage",
            BrowserKind.ARC: "Arc Safe Storage",
            BrowserKind.FIREFOX: "",
        }[self]


@dataclass(frozen=True)
class LocalProfile:
    browser: BrowserKind
    name: str
    display_name: str
    path: Path

    @property
    def cookies_db(self) -> Path | None:
        if self.browser is BrowserKind.FIREFOX:
            candidate = self.path / "cookies.sqlite"
            return candidate if candidate.exists() else None
        for rel in ("Network/Cookies", "Cookies"):
            candidate = self.path / rel
            if candidate.exists():
                return candidate
        return None

    @property
    def label(self) -> str:
        suffix = "" if self.display_name == self.name else f" ({self.name})"
        return f"{self.browser.display_name}: {self.display_name}{suffix}"


def _user_data_dirs(home: Path, platform: str) -> dict[BrowserKind, Path]:
    if platform == "darwin":
        base = home / "Library" / "Application Support"
        return {
            BrowserKind.CHROME: base / "Google" / "Chrome",
            BrowserKind.CHROMIUM: base / "Chromium",
            BrowserKind.BRAVE: base / "BraveSoftware" / "Brave-Browser",
            BrowserKind.EDGE: base / "Microsoft Edge",
            BrowserKind.ARC: base / "Arc" / "User Data",
            BrowserKind.FIREFOX: base / "Firefox",
        }
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return {
        BrowserKind.CHROME: config / "google-chrome",
        BrowserKind.CHROMIUM: config / "chromium",
        BrowserKind.BRAVE: config / "BraveSoftware" / "Brave-Browser",
        BrowserKind.EDGE: config / "microsoft-edge",
        BrowserKind.FIREFOX: home / ".mozilla" / "firefox",
    }


def _chromium_profiles(kind: BrowserKind, user_data_dir: Path) -> list[LocalProfile]:
    if not user_data_dir.is_dir():
        return []
    names: dict[str, str] = {}
    local_state = user_data_dir / "Local State"
    if local_state.exists():
        try:
            info = json.loads(local_state.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
            names = {key: str(value.get("name") or key) for key, value in info.items() if isinstance(value, dict)}
        except (OSError, ValueError):
            names = {}
    profiles = []
    for child in sorted(user_data_dir.iterdir()):
        if not child.is_dir():
            continue
        if not ((child / "Cookies").exists() or (child / "Network" / "Cookies").exists()):
            continue
        profiles.append(LocalProfile(kind, child.name, names.get(child.name, child.name), child))
    return profiles


def _firefox_profiles(root: Path) -> list[LocalProfile]:
    ini = root / "profiles.ini"
    if not ini.exists():
        return []
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(ini, encoding="utf-8")
    except configparser.Error:
        return []
    profiles = []
    for section in parser.sections():
        if not section.lower().startswith("profile"):
            continue
        rel = parser.get(section, "Path", fallback=None)
        if not rel:
            continue
        is_relative = parser.get(section, "IsRelative", fallback="1") == "1"
        path = (root / rel) if is_relative else Path(rel)
        if not (path / "cookies.sqlite").exists():
            continue
        name = parser.get(section, "Name", fallback=path.name)
        profiles.append(LocalProfile(BrowserKind.FIREFOX, path.name, name, path))
    return profiles


def discover_profiles(
    *,
    home: Path | None = None,
    platform: str | None = None,
    browsers: list[BrowserKind] | None = None,
) -> list[LocalProfile]:
    """Every profile with a cookie database, Chromium family first."""
    home = home or Path.home()
    platform = platform or sys.platform
    wanted = set(browsers) if browsers else set(BrowserKind)
    found: list[LocalProfile] = []
    for kind, path in _user_data_dirs(home, platform).items():
        if kind not in wanted:
            continue
        if kind is BrowserKind.FIREFOX:
            found.extend(_firefox_profiles(path))
        else:
            found.extend(_chromium_profiles(kind, path))
    return found
