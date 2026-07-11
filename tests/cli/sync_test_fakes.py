"""Test-only CLI fakes that do not define production interfaces.

Later CLI phases must adapt these helpers to approved scheduler, clock, and
locking protocols before production code consumes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import respx


@dataclass
class FakeScheduler:
    installed_command: list[str] | None = None
    interval: timedelta | None = None

    def install(self, command: list[str], interval: timedelta) -> None:
        self.installed_command = list(command)
        self.interval = interval

    def remove(self) -> None:
        self.installed_command = None
        self.interval = None

    def is_installed(self) -> bool:
        return self.installed_command is not None


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
