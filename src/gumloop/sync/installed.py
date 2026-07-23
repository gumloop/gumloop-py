from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gumloop.sync.errors import SyncError
from gumloop.sync.hashing import compute_manifest_hash
from gumloop.sync.markers import MarkerRead
from gumloop.sync.markers import directory_content_hash
from gumloop.sync.markers import read_marker
from gumloop.sync.results import SyncChange
from gumloop.sync.target_files import has_temporary_workspace
from gumloop.sync.targets import PhysicalTarget
from gumloop.sync.wire import SYNC_WORKSPACE_DIRNAME
from gumloop.types import CliSyncBundleSkill


@dataclass(frozen=True)
class InstalledEntry:
    marker_read: MarkerRead
    content_hash: str | None
    shared_symlink: bool = False


def scan_target(
    skills_root: Path,
    organization_id: str,
    *,
    other_target_roots: tuple[Path, ...] = (),
    hash_unmanaged_names: frozenset[str] = frozenset(),
) -> dict[str, InstalledEntry]:
    if not skills_root.exists():
        return {}
    if skills_root.is_symlink():
        raise SyncError("target_failed", f"Target root must resolve before reconciliation: {skills_root}")
    if not skills_root.is_dir():
        raise SyncError("target_failed", f"Target root is not a directory: {skills_root}")

    installed: dict[str, InstalledEntry] = {}
    try:
        entries = sorted(skills_root.iterdir(), key=lambda path: path.name)
    except OSError as error:
        raise SyncError("target_failed", f"Could not inspect target root: {skills_root}") from error
    for entry in entries:
        if entry.name == SYNC_WORKSPACE_DIRNAME:
            continue
        if entry.is_symlink():
            resolved = entry.resolve()
            shared_destinations = {(other_root / entry.name).resolve() for other_root in other_target_roots}
            if resolved not in shared_destinations:
                raise SyncError("target_failed", f"Refusing to reconcile a symlinked Skill entry: {entry}")
            marker_read = read_marker(resolved, organization_id)
            installed[entry.name] = InstalledEntry(
                marker_read=marker_read,
                content_hash=(
                    directory_content_hash(resolved)
                    if resolved.is_dir() and (marker_read.status == "valid" or entry.name in hash_unmanaged_names)
                    else None
                ),
                shared_symlink=True,
            )
            continue

        marker_read = read_marker(entry, organization_id) if entry.is_dir() else MarkerRead("unmarked")
        installed[entry.name] = InstalledEntry(
            marker_read=marker_read,
            content_hash=(
                directory_content_hash(entry)
                if entry.is_dir() and (marker_read.status == "valid" or entry.name in hash_unmanaged_names)
                else None
            ),
        )
    return installed


def matching_manifest_changes(
    *,
    target: PhysicalTarget,
    organization_id: str,
    manifest_hash: str,
    skill_count: int,
    other_target_roots: tuple[Path, ...] = (),
) -> tuple[SyncChange, ...] | None:
    if has_temporary_workspace(target.skills_root):
        return None
    valid: list[CliSyncBundleSkill] = []
    changes: list[SyncChange] = []
    for name, existing in scan_target(
        target.skills_root,
        organization_id,
        other_target_roots=other_target_roots,
    ).items():
        marker_read = existing.marker_read
        if marker_read.status == "unsupported":
            return None
        if marker_read.status != "valid" or marker_read.marker is None:
            continue
        marker = marker_read.marker
        if existing.content_hash != marker.content_hash:
            return None
        valid.append(
            CliSyncBundleSkill(
                skill_id=marker.skill_id,
                install_name=marker.name,
                published_version_id=marker.published_version_id,
                content_hash=marker.content_hash,
            )
        )
        changes.append(
            SyncChange(
                skill_id=marker.skill_id,
                name=name,
                action="unchanged",
                targets=target.logical_targets,
                physical_path=target.skills_root / name,
            )
        )
    if len(valid) != skill_count or compute_manifest_hash(valid) != manifest_hash:
        return None
    return tuple(changes)


def target_matches_manifest(
    *,
    target: PhysicalTarget,
    organization_id: str,
    manifest_hash: str,
    skill_count: int,
    other_target_roots: tuple[Path, ...] = (),
) -> bool:
    return (
        matching_manifest_changes(
            target=target,
            organization_id=organization_id,
            manifest_hash=manifest_hash,
            skill_count=skill_count,
            other_target_roots=other_target_roots,
        )
        is not None
    )
