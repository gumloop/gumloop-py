from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gumloop import GumloopError


@contextmanager
def linked_proxy_lock(host: str, home: Path | None = None) -> Iterator[None]:
    """Held while the linked proxy runs, so a second one on this machine stops
    instead of competing for the gateway's one connection per linked proxy."""
    path = _lock_path(host, home)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
    except OSError as error:
        raise GumloopError(f"Could not create the lock file {path}: {error}") from error
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise GumloopError("This computer is already connected as a linked proxy.") from error
    try:
        yield
    finally:
        handle.close()


def is_running(host: str, home: Path | None = None) -> bool:
    if not _lock_path(host, home).exists():
        return False
    try:
        with linked_proxy_lock(host, home):
            return False
    except GumloopError:
        return True


def _lock_path(host: str, home: Path | None) -> Path:
    return (home or Path.home()) / ".gumloop" / "linked-proxy" / f"{host}.lock"
