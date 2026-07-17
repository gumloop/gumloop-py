from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from gumloop.sync.bundle import StagedSyncBundle
from gumloop.sync.errors import SyncError
from gumloop.sync.installed import scan_target
from gumloop.sync.markers import build_marker
from gumloop.sync.results import SyncChange
from gumloop.sync.target_files import Mutation
from gumloop.sync.target_files import PreparedTargetReconciliation
from gumloop.sync.target_files import backup_path
from gumloop.sync.target_files import prepare_replacement
from gumloop.sync.target_files import recover_stale_temporary_entries
from gumloop.sync.targets import PhysicalTarget


def prepare_target_reconciliation(
    *,
    target: PhysicalTarget,
    organization_id: str,
    bundle: StagedSyncBundle | None,
    backup_base: Path | None,
    installed_at: datetime,
    other_target_roots: tuple[Path, ...] = (),
) -> PreparedTargetReconciliation:
    desired_skills = bundle.manifest.skills if bundle is not None else []
    desired_by_name = {skill.install_name: skill for skill in desired_skills}
    recover_stale_temporary_entries(target.skills_root)
    installed = scan_target(
        target.skills_root,
        organization_id,
        other_target_roots=other_target_roots,
        hash_unmanaged_names=frozenset(desired_by_name),
    )
    unsupported = next(
        ((name, entry.marker_read) for name, entry in installed.items() if entry.marker_read.status == "unsupported"),
        None,
    )
    if unsupported is not None:
        name, marker_read = unsupported
        raise SyncError(
            "unsupported_version",
            f"Installed Skill {name} uses an unsupported Gumloop marker version.",
            details={"path": str(target.skills_root / name), "reason": marker_read.reason},
        )
    mutations: list[Mutation] = []
    unchanged: list[SyncChange] = []

    try:
        for name, skill in desired_by_name.items():
            destination = target.skills_root / name
            marker = build_marker(
                organization_id=organization_id,
                skill_id=skill.skill_id,
                name=name,
                published_version_id=skill.published_version_id,
                content_hash=skill.content_hash,
                installed_at=installed_at,
            )
            existing = installed.get(name)
            if existing is None:
                prepared = prepare_replacement(
                    skills_root=target.skills_root,
                    bundle=bundle,
                    skill=skill,
                    marker=marker,
                )
                mutations.append(
                    Mutation(
                        kind="replace",
                        destination=destination,
                        skill=skill,
                        marker=marker,
                        action="installed",
                        prepared_path=prepared,
                    )
                )
                continue

            marker_read = existing.marker_read
            local_hash = existing.content_hash
            if existing.shared_symlink:
                shared_marker = marker_read.marker
                if (
                    marker_read.status != "valid"
                    or shared_marker is None
                    or shared_marker.skill_id != skill.skill_id
                    or local_hash != shared_marker.content_hash
                ):
                    raise SyncError(
                        "target_failed",
                        f"Shared Skill link does not resolve to the desired version: {destination}",
                    )
                unchanged.append(
                    SyncChange(
                        skill_id=skill.skill_id,
                        name=name,
                        action="unchanged",
                        targets=target.logical_targets,
                        physical_path=destination,
                    )
                )
                continue
            if marker_read.status == "valid" and marker_read.marker is not None:
                existing_marker = marker_read.marker
                marker_matches = (
                    existing_marker.skill_id == skill.skill_id
                    and existing_marker.published_version_id == skill.published_version_id
                    and existing_marker.content_hash == skill.content_hash
                )
                content_matches_marker = local_hash == existing_marker.content_hash
                if marker_matches and content_matches_marker:
                    unchanged.append(
                        SyncChange(
                            skill_id=skill.skill_id,
                            name=name,
                            action="unchanged",
                            targets=target.logical_targets,
                            physical_path=destination,
                        )
                    )
                    continue
                action = "overwritten_local_edit" if not content_matches_marker else "updated"
                backup_required = not content_matches_marker
            else:
                desired_content_matches = local_hash == skill.content_hash
                if desired_content_matches and destination.is_dir():
                    mutations.append(
                        Mutation(
                            kind="adopt",
                            destination=destination,
                            skill=skill,
                            marker=marker,
                            action="adopted",
                        )
                    )
                    continue
                action = "overwritten_collision"
                backup_required = True

            prepared = prepare_replacement(
                skills_root=target.skills_root,
                bundle=bundle,
                skill=skill,
                marker=marker,
            )
            mutations.append(
                Mutation(
                    kind="replace",
                    destination=destination,
                    skill=skill,
                    marker=marker,
                    action=action,
                    prepared_path=prepared,
                    backup_required=backup_required and backup_base is not None,
                    backup_path=(
                        backup_path(backup_base, target.skills_root, name)
                        if backup_required and backup_base is not None
                        else None
                    ),
                )
            )

        for name, existing in installed.items():
            marker_read = existing.marker_read
            local_hash = existing.content_hash
            if existing.shared_symlink and name not in desired_by_name:
                mutations.append(
                    Mutation(
                        kind="remove",
                        destination=target.skills_root / name,
                        skill=None,
                        marker=marker_read.marker,
                        action="removed",
                    )
                )
                continue
            if marker_read.status != "valid" or marker_read.marker is None:
                if marker_read.status == "invalid":
                    unchanged.append(
                        SyncChange(
                            skill_id="",
                            name=name,
                            action="unchanged",
                            targets=target.logical_targets,
                            physical_path=target.skills_root / name,
                            error=f"Invalid Gumloop ownership marker: {marker_read.reason}",
                        )
                    )
                continue
            marker = marker_read.marker
            if name in desired_by_name:
                continue
            local_edit = local_hash != marker.content_hash
            mutations.append(
                Mutation(
                    kind="remove",
                    destination=target.skills_root / name,
                    skill=None,
                    marker=marker,
                    action="removed",
                    backup_required=local_edit and backup_base is not None,
                    backup_path=(
                        backup_path(backup_base, target.skills_root, name)
                        if local_edit and backup_base is not None
                        else None
                    ),
                )
            )
    except Exception:
        for mutation in mutations:
            if mutation.prepared_path is not None:
                shutil.rmtree(mutation.prepared_path, ignore_errors=True)
        raise

    return PreparedTargetReconciliation(target=target, mutations=mutations, unchanged=unchanged)
