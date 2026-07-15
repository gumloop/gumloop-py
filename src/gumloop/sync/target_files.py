from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gumloop.sync.bundle import StagedSyncBundle
from gumloop.sync.errors import SyncError
from gumloop.sync.markers import OwnershipMarker
from gumloop.sync.markers import is_safe_install_name
from gumloop.sync.markers import write_marker_atomic
from gumloop.sync.results import SyncChange
from gumloop.sync.results import TargetOutcome
from gumloop.sync.targets import PhysicalTarget
from gumloop.sync.wire import SYNC_WORKSPACE_DIRNAME
from gumloop.types import CliSyncBundleSkill

_WORKSPACE_SENTINEL_FILENAME = "workspace.json"
_WORKSPACE_OWNER = "gumloop-skill-sync"
_WORKSPACE_SCHEMA_VERSION = 1
_WORKSPACE_OPERATION_DIRS = ("displaced", "prepared", "removed")


@dataclass
class Mutation:
    kind: Literal["replace", "adopt", "remove"]
    destination: Path
    skill: CliSyncBundleSkill | None
    marker: OwnershipMarker | None
    action: str
    prepared_path: Path | None = None
    backup_path: Path | None = None
    backup_required: bool = False


class PreparedTargetReconciliation:
    """A complete target plan whose managed destinations are still untouched."""

    def __init__(
        self,
        *,
        target: PhysicalTarget,
        mutations: list[Mutation],
        unchanged: list[SyncChange],
    ) -> None:
        self.target = target
        self._mutations = mutations
        self._unchanged = unchanged

    def apply(self) -> TargetOutcome:
        changes = list(self._unchanged)
        failure_code: str | None = None
        for mutation in self._mutations:
            try:
                self._prepare_backup(mutation)
                self._apply_mutation(mutation)
                changes.append(_change_for(mutation, self.target))
            except (OSError, SyncError, RuntimeError) as error:
                changes.append(_failed_change(mutation, self.target, error))
                failure_code = error.code if isinstance(error, SyncError) else "target_failed"
                break
        failure = next((change.error for change in changes if change.action == "failed"), None)
        return TargetOutcome(
            target=self.target,
            changes=tuple(changes),
            error=failure,
            error_code=failure_code,
        )

    def cleanup(self) -> None:
        for mutation in self._mutations:
            if mutation.prepared_path is not None:
                shutil.rmtree(mutation.prepared_path, ignore_errors=True)
        _remove_empty_workspace(self.target.skills_root)

    @staticmethod
    def _prepare_backup(mutation: Mutation) -> None:
        if not mutation.backup_required or mutation.backup_path is None:
            return
        try:
            _replace_rolling_backup(mutation.destination, mutation.backup_path)
        except OSError as error:
            raise SyncError(
                "backup_failed",
                f"Could not back up {mutation.destination}. The installed Skill was not changed.",
                details={
                    "backup_path": str(mutation.backup_path),
                    "path": str(mutation.destination),
                    "reason": str(error),
                },
            ) from error

    @staticmethod
    def _apply_mutation(mutation: Mutation) -> None:
        if mutation.kind == "replace":
            if mutation.prepared_path is None:
                raise RuntimeError("replacement was not prepared")
            _atomic_replace(mutation.prepared_path, mutation.destination)
            mutation.prepared_path = None
        elif mutation.kind == "adopt":
            if mutation.marker is None:
                raise RuntimeError("adoption marker was not prepared")
            write_marker_atomic(mutation.destination, mutation.marker)
        else:
            _atomic_remove(mutation.destination)


def prepare_replacement(
    *,
    skills_root: Path,
    bundle: StagedSyncBundle | None,
    skill: CliSyncBundleSkill,
    marker: OwnershipMarker,
) -> Path:
    if bundle is None:
        raise SyncError("target_failed", "A non-empty reconciliation requires a staged bundle.")
    source = bundle.skill_roots[skill.install_name]
    prepared: Path | None = None
    try:
        skills_root.mkdir(parents=True, exist_ok=True)
        workspace = _open_workspace(skills_root, create=True)
        if workspace is None:
            raise RuntimeError("temporary workspace was not created")
        prepared_root = workspace / "prepared"
        prepared_root.mkdir(exist_ok=True)
        prepared = Path(tempfile.mkdtemp(prefix="skill-", dir=prepared_root))
        shutil.copytree(source, prepared, dirs_exist_ok=True, symlinks=False)
        write_marker_atomic(prepared, marker)
        return prepared
    except (OSError, SyncError) as error:
        if prepared is not None:
            shutil.rmtree(prepared, ignore_errors=True)
        _remove_empty_workspace(skills_root)
        raise SyncError(
            "target_failed",
            f"Could not prepare Skill replacement for {skill.install_name}.",
            details={"path": str(skills_root / skill.install_name), "reason": str(error)},
        ) from error


def backup_path(backup_base: Path, skills_root: Path, name: str) -> Path:
    target_key = hashlib.sha256(str(skills_root).encode("utf-8")).hexdigest()[:16]
    return backup_base / target_key / name


def recover_stale_temporary_entries(skills_root: Path) -> None:
    if not skills_root.exists() or not skills_root.is_dir():
        return
    workspace = _open_workspace(skills_root, create=False)
    if workspace is None:
        return

    allowed_entries = {_WORKSPACE_SENTINEL_FILENAME, *_WORKSPACE_OPERATION_DIRS}
    unknown_entries = sorted(entry.name for entry in workspace.iterdir() if entry.name not in allowed_entries)
    if unknown_entries:
        raise SyncError(
            "target_failed",
            f"The Gumloop temporary workspace contains unknown entries: {workspace}",
            details={"entries": unknown_entries, "path": str(workspace)},
        )

    displaced_root = _operation_root(workspace, "displaced", create=False)
    if displaced_root is not None:
        for entry in _operation_entries(displaced_root, install_names=True):
            destination = skills_root / entry.name
            if not destination.exists() and not destination.is_symlink():
                entry.replace(destination)
            else:
                _remove_path(entry)

    prepared_root = _operation_root(workspace, "prepared", create=False)
    if prepared_root is not None:
        for entry in _operation_entries(prepared_root, prepared_names=True):
            _remove_path(entry)

    removed_root = _operation_root(workspace, "removed", create=False)
    if removed_root is not None:
        for entry in _operation_entries(removed_root, install_names=True):
            _remove_path(entry)

    _remove_empty_workspace(skills_root)


def temporary_workspace_path(skills_root: Path) -> Path:
    return skills_root / SYNC_WORKSPACE_DIRNAME


def has_temporary_workspace(skills_root: Path) -> bool:
    workspace = temporary_workspace_path(skills_root)
    return workspace.exists() or workspace.is_symlink()


def _open_workspace(skills_root: Path, *, create: bool) -> Path | None:
    workspace = temporary_workspace_path(skills_root)
    try:
        if workspace.is_symlink():
            raise SyncError("target_failed", f"Refusing to use a symlinked Gumloop workspace: {workspace}")
        if not workspace.exists():
            if not create:
                return None
            workspace.mkdir(mode=0o700)
        if not workspace.is_dir():
            raise SyncError("target_failed", f"The Gumloop temporary workspace is not a directory: {workspace}")

        sentinel = workspace / _WORKSPACE_SENTINEL_FILENAME
        if sentinel.is_symlink():
            raise SyncError("target_failed", f"The Gumloop workspace sentinel is not a regular file: {sentinel}")
        if not sentinel.exists():
            if any(workspace.iterdir()):
                raise SyncError(
                    "target_failed",
                    f"Refusing to claim a non-empty Gumloop temporary workspace: {workspace}",
                )
            sentinel.write_text(
                json.dumps(
                    {
                        "owner": _WORKSPACE_OWNER,
                        "schema_version": _WORKSPACE_SCHEMA_VERSION,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            sentinel.chmod(0o600)
        elif not sentinel.is_file():
            raise SyncError("target_failed", f"The Gumloop workspace sentinel is not a regular file: {sentinel}")
        else:
            _validate_workspace_sentinel(sentinel)
        workspace.chmod(0o700)
        return workspace
    except SyncError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SyncError(
            "target_failed",
            f"Could not use the Gumloop temporary workspace: {workspace}",
            details={"path": str(workspace), "reason": str(error)},
        ) from error


def _validate_workspace_sentinel(sentinel: Path) -> None:
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("owner") != _WORKSPACE_OWNER:
        raise SyncError("target_failed", f"The Gumloop workspace sentinel is invalid: {sentinel}")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, int) and schema_version > _WORKSPACE_SCHEMA_VERSION:
        raise SyncError(
            "unsupported_version",
            f"The Gumloop temporary workspace uses an unsupported schema: {sentinel}",
        )
    if schema_version != _WORKSPACE_SCHEMA_VERSION:
        raise SyncError("target_failed", f"The Gumloop workspace sentinel is invalid: {sentinel}")


def _operation_root(
    workspace: Path,
    name: str,
    *,
    create: bool,
) -> Path | None:
    root = workspace / name
    if root.is_symlink():
        raise SyncError("target_failed", f"Refusing to use a symlinked Gumloop operation directory: {root}")
    if not root.exists():
        if not create:
            return None
        root.mkdir()
    if not root.is_dir():
        raise SyncError("target_failed", f"The Gumloop operation path is not a directory: {root}")
    return root


def _operation_entries(
    root: Path,
    *,
    install_names: bool = False,
    prepared_names: bool = False,
) -> tuple[Path, ...]:
    entries = tuple(sorted(root.iterdir(), key=lambda path: path.name))
    for entry in entries:
        valid_name = (
            (install_names and is_safe_install_name(entry.name))
            or (prepared_names and entry.name.startswith("skill-"))
        )
        if not valid_name or entry.is_symlink() or not entry.is_dir():
            raise SyncError("target_failed", f"The Gumloop workspace contains an invalid operation entry: {entry}")
    return entries


def _remove_empty_workspace(skills_root: Path) -> None:
    try:
        workspace = _open_workspace(skills_root, create=False)
        if workspace is None:
            return
        for name in _WORKSPACE_OPERATION_DIRS:
            root = workspace / name
            if root.is_dir() and not root.is_symlink() and not any(root.iterdir()):
                root.rmdir()
        remaining = tuple(workspace.iterdir())
        if len(remaining) == 1 and remaining[0].name == _WORKSPACE_SENTINEL_FILENAME:
            remaining[0].unlink()
            workspace.rmdir()
    except (OSError, SyncError):
        pass


def _change_for(mutation: Mutation, target: PhysicalTarget) -> SyncChange:
    return SyncChange(
        skill_id=_skill_id(mutation),
        name=mutation.destination.name,
        action=mutation.action,
        targets=target.logical_targets,
        physical_path=mutation.destination,
        backup_path=mutation.backup_path,
    )


def _failed_change(
    mutation: Mutation,
    target: PhysicalTarget,
    error: Exception,
) -> SyncChange:
    return SyncChange(
        skill_id=_skill_id(mutation),
        name=mutation.destination.name,
        action="failed",
        targets=target.logical_targets,
        physical_path=mutation.destination,
        backup_path=mutation.backup_path,
        error=str(error),
    )


def _skill_id(mutation: Mutation) -> str:
    if mutation.skill is not None:
        return mutation.skill.skill_id
    return mutation.marker.skill_id if mutation.marker is not None else ""


def _replace_rolling_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.parent / f".{destination.name}.tmp"
    displaced = destination.parent / f".{destination.name}.old"
    _remove_path(temporary)
    _remove_path(displaced)
    _copy_path(source, temporary)
    try:
        if destination.exists() or destination.is_symlink():
            destination.replace(displaced)
        temporary.replace(destination)
    except OSError:
        if displaced.exists() or displaced.is_symlink():
            displaced.replace(destination)
        raise
    try:
        _remove_path(displaced)
    except OSError:
        pass
    finally:
        _remove_path(temporary)


def _atomic_replace(prepared: Path, destination: Path) -> None:
    workspace = _open_workspace(destination.parent, create=True)
    if workspace is None:
        raise RuntimeError("temporary workspace was not created")
    displaced_root = _operation_root(workspace, "displaced", create=True)
    if displaced_root is None:
        raise RuntimeError("displaced operation directory was not created")
    displaced = displaced_root / destination.name
    _remove_path(displaced)
    try:
        if destination.exists() or destination.is_symlink():
            destination.replace(displaced)
        prepared.replace(destination)
    except OSError:
        if displaced.exists() or displaced.is_symlink():
            displaced.replace(destination)
        raise
    try:
        _remove_path(displaced)
    except OSError:
        pass
    _remove_empty_workspace(destination.parent)


def _atomic_remove(destination: Path) -> None:
    workspace = _open_workspace(destination.parent, create=True)
    if workspace is None:
        raise RuntimeError("temporary workspace was not created")
    removed_root = _operation_root(workspace, "removed", create=True)
    if removed_root is None:
        raise RuntimeError("removed operation directory was not created")
    displaced = removed_root / destination.name
    _remove_path(displaced)
    destination.replace(displaced)
    try:
        _remove_path(displaced)
    except OSError:
        pass
    _remove_empty_workspace(destination.parent)


def _copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=False)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)
