from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import typer

from gumloop import __version__
from gumloop.cli.console import console
from gumloop.cli.console import error_console

PYPI_JSON_URL = "https://pypi.org/pypi/gumloop/json"
UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60


def gumloop_home() -> Path:
    override = os.environ.get("GUMLOOP_INSTALL_DIR")
    return Path(override) if override else Path.home() / ".gumloop"


def is_managed_install() -> bool:
    try:
        prefix = Path(sys.prefix).resolve()
        return prefix == (gumloop_home() / "venv").resolve()
    except OSError:
        return False


def fetch_latest_version(timeout: float = 10.0) -> str:
    response = httpx.get(PYPI_JSON_URL, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.json()["info"]["version"]


def _version_tuple(version: str) -> tuple[int, ...] | None:
    parts: list[int] = []
    for part in version.split("."):
        digits = ""
        for char in part:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) if parts else None


def is_newer(latest: str, current: str) -> bool:
    latest_t = _version_tuple(latest)
    current_t = _version_tuple(current)
    if latest_t is None or current_t is None:
        return latest != current
    return latest_t > current_t


def _non_managed_hint() -> str:
    prefix = sys.prefix
    if "pipx" in prefix:
        return "pipx upgrade gumloop"
    if f"{os.sep}uv{os.sep}tools{os.sep}" in prefix:
        return "uv tool upgrade gumloop"
    return "uv pip install --upgrade gumloop"


def update() -> None:
    """Update the Gumloop CLI to the latest version."""
    try:
        latest = fetch_latest_version()
    except (httpx.HTTPError, KeyError, ValueError):
        error_console.print("[red]Error:[/red] could not reach PyPI to check for updates.")
        raise typer.Exit(1) from None

    if not is_newer(latest, __version__):
        console.print(f"gumloop {__version__} is already the latest version.")
        return

    if not is_managed_install():
        console.print(
            f"gumloop [bold]{latest}[/bold] is available (you have {__version__}).\n"
            f"This install is not managed by the Gumloop installer; update it with:\n"
            f"    [bold]{_non_managed_hint()}[/bold]"
        )
        return

    home = gumloop_home()
    uv = home / "bin" / "uv"
    python = home / "venv" / "bin" / "python"
    if not uv.is_file() or not python.is_file():
        error_console.print(
            "[red]Error:[/red] managed install is missing its uv or Python. Repair it by re-running:\n"
            "    curl -fsSL https://gumloop.com/cli/install.sh | sh"
        )
        raise typer.Exit(1)

    console.print(f"Updating gumloop {__version__} -> [bold]{latest}[/bold] ...")
    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(home / "python")
    env["UV_CACHE_DIR"] = str(home / "cache")
    result = subprocess.run(
        [str(uv), "pip", "install", "--python", str(python), "--quiet", f"gumloop=={latest}"],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error_console.print(f"[red]Error:[/red] update failed:\n{result.stderr.strip()}")
        raise typer.Exit(1)

    _write_check_state(latest)
    console.print(f"[green]Updated to gumloop {latest}.[/green]")


def _check_state_path() -> Path:
    return gumloop_home() / "update_check.json"


def _write_check_state(latest: str) -> None:
    try:
        path = _check_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"checked_at": time.time(), "latest": latest}))
    except OSError:
        pass


def _refresh_check_state() -> None:
    try:
        _write_check_state(fetch_latest_version(timeout=5.0))
    except Exception:
        pass


def maybe_notify_update() -> None:
    """Runs on every CLI invocation; must never block or raise."""
    try:
        if os.environ.get("GUMLOOP_NO_UPDATE_CHECK") or os.environ.get("CI"):
            return
        if not sys.stderr.isatty():
            return

        state: dict[str, object] = {}
        try:
            state = json.loads(_check_state_path().read_text())
        except (OSError, json.JSONDecodeError):
            pass

        checked_at = state.get("checked_at")
        stale = not isinstance(checked_at, (int, float)) or time.time() - checked_at > UPDATE_CHECK_INTERVAL_SECONDS
        if stale:
            threading.Thread(target=_refresh_check_state, daemon=True).start()

        latest = state.get("latest")
        if isinstance(latest, str) and is_newer(latest, __version__):
            command = "gumloop update" if is_managed_install() else _non_managed_hint()
            error_console.print(f"[dim]A new version of gumloop is available: {latest} (run `{command}`).[/dim]")
    except Exception:
        pass
