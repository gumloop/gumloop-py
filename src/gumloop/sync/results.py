from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gumloop.sync.targets import PhysicalTarget


@dataclass(frozen=True)
class SyncChange:
    skill_id: str
    name: str
    action: str
    targets: tuple[str, ...]
    physical_path: Path
    backup_path: Path | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "backup_path": str(self.backup_path) if self.backup_path is not None else None,
            "error": self.error,
            "name": self.name,
            "physical_path": str(self.physical_path),
            "skill_id": self.skill_id,
            "targets": list(self.targets),
        }


@dataclass(frozen=True)
class TargetOutcome:
    target: PhysicalTarget
    changes: tuple[SyncChange, ...]
    error: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class SyncProgress:
    stage: Literal[
        "resolving_plan",
        "plan_resolved",
        "downloading_bundle",
        "bundle_verified",
        "reconciling_target",
        "target_complete",
        "already_current",
    ]
    attempt: int = 1
    max_attempts: int | None = None
    skill_count: int | None = None
    agent_count: int | None = None
    target: PhysicalTarget | None = None
    outcome: TargetOutcome | None = None


# Progress observers are best-effort presentation only; their failures never affect sync.
SyncProgressCallback = Callable[[SyncProgress], None]


@dataclass(frozen=True)
class SyncExecution:
    status: Literal["ok", "partial", "blocked"]
    result: dict[str, object]
