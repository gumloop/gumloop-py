from __future__ import annotations

import fcntl
import hashlib
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gumloop.sync.errors import SyncError


@contextmanager
def sync_lock(*, home: Path) -> Iterator[None]:
    """Hold one advisory lock across all local one-shot sync writes."""
    path = _lock_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
        path.chmod(0o600)
    except OSError as error:
        raise SyncError(
            "target_failed",
            f"Could not acquire the Skill sync lock: {path}",
            details={"path": str(path), "reason": str(error)},
        ) from error
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise SyncError("sync_in_progress", "Another Gumloop Skill sync is already running.") from error
    except OSError as error:
        handle.close()
        raise SyncError(
            "target_failed",
            f"Could not acquire the Skill sync lock: {path}",
            details={"path": str(path), "reason": str(error)},
        ) from error
    try:
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _lock_path(home: Path) -> Path:
    home_key = hashlib.sha256(str(home.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"gumloop-sync-{home_key}.lock"
