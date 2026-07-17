from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.bundle_validation import ValidatedBundle
from gumloop.sync.bundle_validation import validate_sync_bundle
from gumloop.sync.errors import SyncError
from gumloop.sync.wire import MANIFEST_FILENAME
from gumloop.types import CliSyncBundleManifest
from gumloop.types import CliSyncLimits


@dataclass(frozen=True)
class StagedSyncBundle:
    root: Path
    manifest: CliSyncBundleManifest
    skill_roots: dict[str, Path]


def write_bytes(path: Path, content: bytes) -> None:
    """Write one staged file. This seam supports staging-failure tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def stage_sync_bundle(
    download: SyncBundleDownload,
    *,
    expected_organization_id: str,
    plan_limits: CliSyncLimits,
    staging_parent: Path,
) -> StagedSyncBundle:
    """Validate a complete bundle before materializing one isolated staging tree."""
    staging_root: Path | None = None
    try:
        validated = validate_sync_bundle(
            download,
            expected_organization_id=expected_organization_id,
            plan_limits=plan_limits,
        )
        staging_root = staging_parent / f".gumloop-sync-staging-{secrets.token_hex(8)}"
        staging_root.mkdir()
        _materialize(validated, staging_root)
    except SyncError:
        _cleanup(staging_root)
        raise
    except OSError as error:
        _cleanup(staging_root)
        raise SyncError("download_failed", "The sync bundle could not be staged.") from error

    return StagedSyncBundle(
        root=staging_root,
        manifest=validated.manifest,
        skill_roots={skill.install_name: staging_root / skill.install_name for skill in validated.manifest.skills},
    )


def _materialize(validated: ValidatedBundle, root: Path) -> None:
    write_bytes(root / MANIFEST_FILENAME, validated.manifest_bytes)
    for install_name, files in validated.files_by_install_name.items():
        for relative_path, content in files.items():
            write_bytes(root / install_name / relative_path, content)


def _cleanup(root: Path | None) -> None:
    if root is not None:
        shutil.rmtree(root, ignore_errors=True)
