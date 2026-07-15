from __future__ import annotations

from datetime import datetime
from pathlib import Path

from gumloop.sync.errors import SyncError
from gumloop.sync.local_state import SyncConfig
from gumloop.sync.local_state import SyncState
from gumloop.sync.local_state import write_state
from gumloop.sync.results import SyncChange
from gumloop.sync.results import TargetOutcome
from gumloop.sync.targets import PhysicalTarget

_ACTIONS = (
    "adopted",
    "failed",
    "installed",
    "overwritten_collision",
    "overwritten_local_edit",
    "removed",
    "unchanged",
    "updated",
)


def build_result(
    *,
    organization_id: str,
    manifest_hash: str | None,
    targets: tuple[PhysicalTarget, ...],
    convergence: str,
    blocked_reason: str | None,
    changes: tuple[SyncChange, ...],
    outcomes: tuple[TargetOutcome, ...] = (),
    background: dict[str, object] | None = None,
) -> dict[str, object]:
    counts = {action: sum(change.action == action for change in changes) for action in _ACTIONS}
    counts["overwritten"] = counts["overwritten_collision"] + counts["overwritten_local_edit"]
    errors = {
        outcome.target: ({"code": outcome.error_code, "message": outcome.error} if outcome.error is not None else None)
        for outcome in outcomes
    }
    result: dict[str, object] = {
        "blocked_reason": blocked_reason,
        "changes": [change.to_dict() for change in changes],
        "convergence": convergence,
        "counts": counts,
        "detected_targets": sorted({name for target in targets for name in target.logical_targets}),
        "manifest_hash": manifest_hash,
        "organization_id": organization_id,
        "physical_targets": [
            {
                "error": errors.get(target),
                "path": str(target.skills_root),
                "targets": list(target.logical_targets),
            }
            for target in targets
        ],
    }
    if background is not None:
        result["background"] = background
    return result


def write_configured_state(
    *,
    home: Path,
    status: str,
    result: dict[str, object],
    attempted_at: datetime,
    previous_state: SyncState | None,
    manifest_hash: str | None,
    blocked_reason: str | None,
) -> None:
    successful = status in ("success", "departure_cleanup")
    write_state(
        {
            "blocked_reason": blocked_reason,
            "detected_targets": result["detected_targets"],
            "last_attempt_at": attempted_at.isoformat(),
            "last_result": result,
            "last_success_at": (
                attempted_at.isoformat()
                if successful
                else previous_state.last_success_at
                if previous_state is not None
                else None
            ),
            "manifest_hash": manifest_hash,
            "physical_targets": result["physical_targets"],
            "schema_version": 1,
            "status": status,
        },
        home,
    )


def record_failure_if_configured(
    *,
    error: SyncError,
    config: SyncConfig | None,
    targets: tuple[PhysicalTarget, ...],
    home: Path,
    attempted_at: datetime,
    previous_state: SyncState | None,
    background: dict[str, object] | None = None,
) -> None:
    if config is None:
        return
    manifest_hash = previous_state.manifest_hash if previous_state is not None else None
    result = build_result(
        organization_id=config.organization_id,
        manifest_hash=manifest_hash,
        targets=targets,
        convergence="none",
        blocked_reason=None,
        changes=(),
        background=background,
    )
    result["error"] = {
        "code": error.code,
        "details": error.details,
        "message": str(error),
    }
    try:
        write_configured_state(
            home=home,
            status="error",
            result=result,
            attempted_at=attempted_at,
            previous_state=previous_state,
            manifest_hash=manifest_hash,
            blocked_reason=None,
        )
    except SyncError:
        pass
