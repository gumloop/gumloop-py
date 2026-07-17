"""Test-only adapters for isolated Skill Sync command scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import respx

from gumloop.sync.errors import SyncError


@dataclass
class FakeScheduler:
    installed_executable: Path | None = None
    available: bool = True
    install_error: SyncError | None = None
    install_count: int = 0
    remove_count: int = 0

    def validate(self, executable_path: Path) -> None:
        if not self.available:
            raise SyncError(
                "scheduler_unavailable",
                "Background scheduling is unavailable.",
            )

    def install(self, executable_path: Path) -> None:
        if self.install_error is not None:
            raise self.install_error
        self.installed_executable = executable_path
        self.install_count += 1

    def remove(self) -> None:
        self.installed_executable = None
        self.remove_count += 1

    def is_current(self, executable_path: Path) -> bool:
        return self.installed_executable == executable_path


class FakeAdvisoryLock:
    def __init__(self) -> None:
        self.held = False

    def acquire(self) -> bool:
        if self.held:
            return False
        self.held = True
        return True

    def release(self) -> None:
        self.held = False


class DeterministicClock:
    def __init__(self, current: datetime) -> None:
        if current.tzinfo is None:
            raise ValueError("current must be timezone-aware")
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> datetime:
        self._current += delta
        return self._current


@dataclass
class SyncCliTestEnvironment:
    home: Path
    executable_path: Path
    target_root: Path
    scheduler: FakeScheduler
    clock: DeterministicClock
    lock: FakeAdvisoryLock
    http: respx.MockRouter

    def create_target(self, name: str) -> Path:
        target = self.target_root / name
        target.mkdir(parents=True, exist_ok=True)
        return target
