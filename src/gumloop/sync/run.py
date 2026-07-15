from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal

import httpx

from gumloop import APIStatusError
from gumloop import AuthenticationError
from gumloop.sync.bundle import StagedSyncBundle
from gumloop.sync.bundle import stage_sync_bundle
from gumloop.sync.errors import SyncError
from gumloop.sync.hashing import compute_manifest_hash
from gumloop.sync.installed import matching_manifest_changes
from gumloop.sync.local_state import SyncConfig
from gumloop.sync.local_state import SyncState
from gumloop.sync.local_state import backup_root
from gumloop.sync.local_state import load_state
from gumloop.sync.reconcile import prepare_target_reconciliation
from gumloop.sync.reporting import build_result
from gumloop.sync.reporting import record_failure_if_configured
from gumloop.sync.reporting import write_configured_state
from gumloop.sync.results import SyncChange
from gumloop.sync.results import SyncExecution
from gumloop.sync.results import SyncProgress
from gumloop.sync.results import SyncProgressCallback
from gumloop.sync.results import TargetOutcome
from gumloop.sync.targets import PhysicalTarget
from gumloop.sync.targets import detect_targets
from gumloop.types import CliSyncPlanResponse

if TYPE_CHECKING:
    from gumloop.cli.context import CliContext

_CONTEXT_CHANGE_RETRIES = 3

BeforeTargetWrites = Callable[
    [CliSyncPlanResponse, tuple[PhysicalTarget, ...]],
    SyncConfig,
]
DepartureCleanup = Callable[[], None]


def run_sync(
    *,
    cli: CliContext,
    home: Path,
    config: SyncConfig | None,
    now: datetime | None = None,
    on_progress: SyncProgressCallback | None = None,
    before_target_writes: BeforeTargetWrites | None = None,
    on_departure: DepartureCleanup | None = None,
    background: dict[str, object] | None = None,
) -> SyncExecution:
    attempted_at = now or datetime.now(timezone.utc)
    targets = detect_targets(home=home)
    organization_id = config.organization_id if config is not None else None
    previous_state = load_state(home) if config is not None else None
    active_config = config
    persistent = config is not None or before_target_writes is not None

    try:
        for attempt in range(_CONTEXT_CHANGE_RETRIES):
            _emit_progress(
                on_progress,
                SyncProgress(
                    stage="resolving_plan",
                    attempt=attempt + 1,
                    max_attempts=_CONTEXT_CHANGE_RETRIES,
                ),
            )
            plan_outcome = _fetch_plan(
                cli=cli,
                organization_id=organization_id,
                config=config,
                targets=targets,
                home=home,
                attempted_at=attempted_at,
                previous_state=previous_state,
                on_progress=on_progress,
                background=background,
                on_departure=on_departure,
            )
            if isinstance(plan_outcome, SyncExecution):
                return plan_outcome
            plan = plan_outcome
            _validate_plan_context(
                plan,
                requested_organization_id=organization_id,
            )
            _emit_progress(
                on_progress,
                SyncProgress(
                    stage="plan_resolved",
                    attempt=attempt + 1,
                    skill_count=plan.skill_count,
                    agent_count=_agent_count(targets),
                ),
            )

            if plan.skill_count == 0:
                if before_target_writes is not None:
                    active_config = before_target_writes(plan, targets)
                return _reconcile_plan(
                    plan=plan,
                    bundle=None,
                    targets=targets,
                    home=home,
                    configured=active_config is not None,
                    attempted_at=attempted_at,
                    previous_state=previous_state,
                    on_progress=on_progress,
                    background=background,
                )
            unchanged_changes = _unchanged_changes_if_current(
                plan=plan,
                targets=targets,
                config=config,
                previous_state=previous_state,
            )
            if unchanged_changes is not None:
                _emit_progress(
                    on_progress,
                    SyncProgress(
                        stage="already_current",
                        skill_count=plan.skill_count,
                        agent_count=_agent_count(targets),
                    ),
                )
                return _record_unchanged_plan(
                    plan=plan,
                    targets=targets,
                    home=home,
                    attempted_at=attempted_at,
                    previous_state=previous_state,
                    changes=unchanged_changes,
                    background=background,
                )
            if not targets and not persistent:
                raise SyncError(
                    "no_targets",
                    "No coding agents detected. Skills were not written. Install an agent or check PATH, then retry.",
                )

            try:
                _emit_progress(
                    on_progress,
                    SyncProgress(
                        stage="downloading_bundle",
                        skill_count=plan.skill_count,
                    ),
                )
                download = cli.call_with_refresh(
                    lambda client: client.sync.download(
                        organization_id=organization_id,
                    )
                )
            except APIStatusError as error:
                if error.code == "sync_context_changed" and attempt + 1 < _CONTEXT_CHANGE_RETRIES:
                    continue
                raise

            with tempfile.TemporaryDirectory(prefix="gumloop-sync-stage-") as staging_parent:
                bundle = stage_sync_bundle(
                    download,
                    expected_organization_id=plan.organization.organization_id,
                    plan_limits=plan.limits,
                    staging_parent=Path(staging_parent),
                )
                _emit_progress(
                    on_progress,
                    SyncProgress(
                        stage="bundle_verified",
                        skill_count=len(bundle.manifest.skills),
                    ),
                )
                if before_target_writes is not None:
                    active_config = before_target_writes(plan, targets)
                return _reconcile_plan(
                    plan=plan,
                    bundle=bundle,
                    targets=targets,
                    home=home,
                    configured=active_config is not None,
                    attempted_at=attempted_at,
                    previous_state=previous_state,
                    on_progress=on_progress,
                    background=background,
                )
        raise SyncError("download_failed", "The sync context kept changing. Retry the sync.")
    except APIStatusError as error:
        translated = _translate_api_error(error)
        record_failure_if_configured(
            error=translated,
            config=active_config,
            targets=targets,
            home=home,
            attempted_at=attempted_at,
            previous_state=previous_state,
            background=background,
        )
        raise translated from error
    except AuthenticationError as error:
        translated = SyncError("auth_required", "Not authenticated. Run `gumloop login` to sign in.")
        record_failure_if_configured(
            error=translated,
            config=active_config,
            targets=targets,
            home=home,
            attempted_at=attempted_at,
            previous_state=previous_state,
            background=background,
        )
        raise translated from error
    except httpx.HTTPError as error:
        translated = SyncError("download_failed", f"Skill sync could not reach Gumloop: {error}")
        record_failure_if_configured(
            error=translated,
            config=active_config,
            targets=targets,
            home=home,
            attempted_at=attempted_at,
            previous_state=previous_state,
            background=background,
        )
        raise translated from error
    except SyncError as error:
        record_failure_if_configured(
            error=error,
            config=active_config,
            targets=targets,
            home=home,
            attempted_at=attempted_at,
            previous_state=previous_state,
            background=background,
        )
        raise


def _fetch_plan(
    *,
    cli: CliContext,
    organization_id: str | None,
    config: SyncConfig | None,
    targets: tuple[PhysicalTarget, ...],
    home: Path,
    attempted_at: datetime,
    previous_state: SyncState | None,
    on_progress: SyncProgressCallback | None = None,
    background: dict[str, object] | None = None,
    on_departure: DepartureCleanup | None = None,
) -> CliSyncPlanResponse | SyncExecution:
    try:
        return cli.call_with_refresh(
            lambda client: client.sync.plan(
                organization_id=organization_id,
            )
        )
    except APIStatusError as error:
        if error.code == "organization_sync_requires_pro" and config is not None:
            result = build_result(
                organization_id=config.organization_id,
                manifest_hash=_manifest_hash(previous_state),
                targets=targets,
                convergence="none",
                blocked_reason="organization_sync_requires_pro",
                changes=(),
                background=background,
            )
            write_configured_state(
                home=home,
                status="blocked",
                result=result,
                attempted_at=attempted_at,
                previous_state=previous_state,
                manifest_hash=_manifest_hash(previous_state),
                blocked_reason="organization_sync_requires_pro",
            )
            return SyncExecution(status="blocked", result=result)
        if error.code == "insufficient_organization_permissions" and config is not None:
            return _departure_cleanup(
                organization_id=config.organization_id,
                targets=targets,
                home=home,
                attempted_at=attempted_at,
                previous_state=previous_state,
                on_progress=on_progress,
                background=background,
                on_departure=on_departure,
            )
        raise


def _unchanged_changes_if_current(
    *,
    plan: CliSyncPlanResponse,
    targets: tuple[PhysicalTarget, ...],
    config: SyncConfig | None,
    previous_state: SyncState | None,
) -> tuple[SyncChange, ...] | None:
    if config is None or previous_state is None:
        return None
    if previous_state.manifest_hash != plan.manifest.hash:
        return None

    changes: list[SyncChange] = []
    for target in targets:
        target_changes = matching_manifest_changes(
            target=target,
            organization_id=plan.organization.organization_id,
            manifest_hash=plan.manifest.hash,
            skill_count=plan.skill_count,
            other_target_roots=_other_target_roots(target, targets),
        )
        if target_changes is None:
            return None
        changes.extend(target_changes)
    return tuple(changes)


def _validate_plan_context(
    plan: CliSyncPlanResponse,
    *,
    requested_organization_id: str | None,
) -> None:
    if requested_organization_id is not None and plan.organization.organization_id != requested_organization_id:
        raise SyncError("invalid_desired_state", "The sync plan returned a different organization.")
    if plan.skill_count == 0 and plan.manifest.hash != compute_manifest_hash(()):
        raise SyncError("invalid_desired_state", "The empty sync plan has an invalid manifest hash.")


def _translate_api_error(error: APIStatusError) -> SyncError:
    if error.status_code == 401:
        return SyncError("auth_required", "Not authenticated. Run `gumloop login` to sign in.")
    if error.status_code == 426 or error.code == "cli_upgrade_required":
        return SyncError("unsupported_version", str(error), details=error.details)
    if error.code in ("invalid_server_sync_plan", "invalid_sync_bundle"):
        return SyncError("invalid_desired_state", str(error), details=error.details)
    return SyncError(
        "download_failed",
        str(error),
        details={"server_code": error.code, **error.details},
    )


def _reconcile_plan(
    *,
    plan: CliSyncPlanResponse,
    bundle: StagedSyncBundle | None,
    targets: tuple[PhysicalTarget, ...],
    home: Path,
    configured: bool,
    attempted_at: datetime,
    previous_state: SyncState | None,
    on_progress: SyncProgressCallback | None = None,
    background: dict[str, object] | None = None,
) -> SyncExecution:
    organization_id = plan.organization.organization_id
    manifest_hash = bundle.manifest.manifest.hash if bundle is not None else plan.manifest.hash
    outcomes = _reconcile_targets(
        targets=targets,
        organization_id=organization_id,
        bundle=bundle,
        backup_base=backup_root(home) if configured else None,
        installed_at=attempted_at,
        on_progress=on_progress,
    )
    changes = tuple(change for outcome in outcomes for change in outcome.changes)
    failed = any(outcome.error is not None for outcome in outcomes)
    result = build_result(
        organization_id=organization_id,
        manifest_hash=manifest_hash,
        targets=targets,
        convergence="partial" if failed else "full",
        blocked_reason=None,
        changes=changes,
        outcomes=outcomes,
        background=background,
    )
    status: Literal["ok", "partial"] = "partial" if failed else "ok"
    if configured:
        write_configured_state(
            home=home,
            status="partial" if failed else "success",
            result=result,
            attempted_at=attempted_at,
            previous_state=previous_state,
            manifest_hash=manifest_hash if not failed else _manifest_hash(previous_state),
            blocked_reason=None,
        )
    return SyncExecution(status=status, result=result)


def _record_unchanged_plan(
    *,
    plan: CliSyncPlanResponse,
    targets: tuple[PhysicalTarget, ...],
    home: Path,
    attempted_at: datetime,
    previous_state: SyncState | None,
    changes: tuple[SyncChange, ...],
    background: dict[str, object] | None = None,
) -> SyncExecution:
    result = build_result(
        organization_id=plan.organization.organization_id,
        manifest_hash=plan.manifest.hash,
        targets=targets,
        convergence="full",
        blocked_reason=None,
        changes=changes,
        background=background,
    )
    write_configured_state(
        home=home,
        status="success",
        result=result,
        attempted_at=attempted_at,
        previous_state=previous_state,
        manifest_hash=plan.manifest.hash,
        blocked_reason=None,
    )
    return SyncExecution(status="ok", result=result)


def _departure_cleanup(
    *,
    organization_id: str,
    targets: tuple[PhysicalTarget, ...],
    home: Path,
    attempted_at: datetime,
    previous_state: SyncState | None,
    on_progress: SyncProgressCallback | None = None,
    background: dict[str, object] | None = None,
    on_departure: DepartureCleanup | None = None,
) -> SyncExecution:
    backups = backup_root(home)
    outcomes = _reconcile_targets(
        targets=targets,
        organization_id=organization_id,
        bundle=None,
        backup_base=backups,
        installed_at=attempted_at,
        on_progress=on_progress,
    )
    failed = any(outcome.error is not None for outcome in outcomes)
    changes = tuple(change for outcome in outcomes for change in outcome.changes)
    if not failed and on_departure is not None:
        on_departure()
    result = build_result(
        organization_id=organization_id,
        manifest_hash=None,
        targets=targets,
        convergence="partial" if failed else "full",
        blocked_reason=None,
        changes=changes,
        outcomes=outcomes,
        background=background,
    )
    result["departure_cleanup"] = True
    write_configured_state(
        home=home,
        status="partial" if failed else "departure_cleanup",
        result=result,
        attempted_at=attempted_at,
        previous_state=previous_state,
        manifest_hash=None,
        blocked_reason=None,
    )
    if not failed:
        shutil.rmtree(backups, ignore_errors=True)
    return SyncExecution(status="partial" if failed else "ok", result=result)


def _other_target_roots(
    target: PhysicalTarget,
    targets: tuple[PhysicalTarget, ...],
) -> tuple[Path, ...]:
    return tuple(other.skills_root for other in targets if other != target)


def _reconcile_targets(
    *,
    targets: tuple[PhysicalTarget, ...],
    organization_id: str,
    bundle: StagedSyncBundle | None,
    backup_base: Path | None,
    installed_at: datetime,
    on_progress: SyncProgressCallback | None = None,
) -> tuple[TargetOutcome, ...]:
    outcomes: list[TargetOutcome] = []
    for target in targets:
        prepared = None
        _emit_progress(
            on_progress,
            SyncProgress(
                stage="reconciling_target",
                target=target,
            ),
        )
        try:
            prepared = prepare_target_reconciliation(
                target=target,
                organization_id=organization_id,
                bundle=bundle,
                backup_base=backup_base,
                installed_at=installed_at,
                other_target_roots=_other_target_roots(target, targets),
            )
            outcome = prepared.apply()
        except (OSError, SyncError) as error:
            outcome = TargetOutcome(
                target=target,
                changes=(),
                error=str(error),
                error_code=error.code if isinstance(error, SyncError) else "target_failed",
            )
        finally:
            if prepared is not None:
                prepared.cleanup()
        outcomes.append(outcome)
        _emit_progress(
            on_progress,
            SyncProgress(
                stage="target_complete",
                target=target,
                outcome=outcome,
            ),
        )
    return tuple(outcomes)


def _emit_progress(
    callback: SyncProgressCallback | None,
    progress: SyncProgress,
) -> None:
    """Notify a best-effort progress observer without affecting sync correctness."""
    if callback is None:
        return
    try:
        callback(progress)
    except Exception:
        return


def _agent_count(targets: tuple[PhysicalTarget, ...]) -> int:
    return sum(len(target.logical_targets) for target in targets)


def _manifest_hash(state: SyncState | None) -> str | None:
    return state.manifest_hash if state is not None else None
