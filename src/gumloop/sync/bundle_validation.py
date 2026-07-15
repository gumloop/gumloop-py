from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.archive import read_bundle_archive
from gumloop.sync.errors import SyncError
from gumloop.sync.hashing import compute_content_hash
from gumloop.sync.hashing import compute_manifest_hash
from gumloop.sync.markers import is_safe_install_name
from gumloop.sync.wire import BUNDLE_CONTENT_TYPE
from gumloop.sync.wire import V1_LIMITS
from gumloop.types import CliSyncBundleManifest
from gumloop.types import CliSyncLimits


@dataclass(frozen=True)
class ValidatedBundle:
    manifest_bytes: bytes
    manifest: CliSyncBundleManifest
    files_by_install_name: dict[str, dict[str, bytes]]


def validate_sync_bundle(
    download: SyncBundleDownload,
    *,
    expected_organization_id: str,
    plan_limits: CliSyncLimits,
) -> ValidatedBundle:
    _validate_download(download, plan_limits)
    initial_limits = _effective_limits(plan_limits, V1_LIMITS)
    archive = read_bundle_archive(download.content, limits=initial_limits)
    manifest = _parse_manifest(archive.manifest_bytes)
    effective_limits = _effective_limits(plan_limits, manifest.limits)
    _validate_manifest(
        manifest,
        expected_organization_id=expected_organization_id,
    )
    _validate_skill_files(
        manifest,
        archive.files_by_install_name,
        limits=effective_limits,
    )
    return ValidatedBundle(
        manifest_bytes=archive.manifest_bytes,
        manifest=manifest,
        files_by_install_name=archive.files_by_install_name,
    )


def _validate_download(
    download: SyncBundleDownload,
    plan_limits: CliSyncLimits,
) -> None:
    if download.content_type != BUNDLE_CONTENT_TYPE:
        raise SyncError("download_failed", "The sync bundle returned an unexpected media type.")
    if len(download.content) > min(V1_LIMITS.bundle_transfer_bytes, plan_limits.bundle_transfer_bytes):
        raise SyncError("download_failed", "The sync bundle exceeded the transfer byte limit.")


def _parse_manifest(manifest_bytes: bytes) -> CliSyncBundleManifest:
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
        return CliSyncBundleManifest.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise SyncError("invalid_desired_state", "The sync bundle manifest is invalid.") from error


def _validate_manifest(
    manifest: CliSyncBundleManifest,
    *,
    expected_organization_id: str,
) -> None:
    if manifest.organization.organization_id != expected_organization_id:
        raise SyncError("invalid_desired_state", "The sync bundle returned a different organization.")
    if any(not is_safe_install_name(skill.install_name) for skill in manifest.skills):
        raise SyncError("invalid_desired_state", "The sync bundle contains an invalid install name.")
    computed_hash = compute_manifest_hash(manifest.skills)
    if computed_hash != manifest.manifest.hash:
        raise SyncError("invalid_desired_state", "The sync bundle manifest hash does not match its skills.")


def _validate_skill_files(
    manifest: CliSyncBundleManifest,
    files_by_install_name: dict[str, dict[str, bytes]],
    *,
    limits: CliSyncLimits,
) -> None:
    if set(files_by_install_name) != {skill.install_name for skill in manifest.skills}:
        raise SyncError("invalid_desired_state", "The sync bundle does not match its declared skill roots.")
    for skill in manifest.skills:
        files = files_by_install_name[skill.install_name]
        if not files:
            raise SyncError("invalid_desired_state", "The sync bundle is missing declared Skill files.")
        if len(files) > limits.files_per_skill:
            raise SyncError("invalid_desired_state", "A Skill exceeds the file count limit.")
        if compute_content_hash(files) != skill.content_hash:
            raise SyncError("invalid_desired_state", "A Skill content hash does not match the manifest.")


def _effective_limits(
    plan_limits: CliSyncLimits,
    embedded_limits: CliSyncLimits,
) -> CliSyncLimits:
    return CliSyncLimits(
        files_per_skill=min(V1_LIMITS.files_per_skill, plan_limits.files_per_skill, embedded_limits.files_per_skill),
        bytes_per_file=min(V1_LIMITS.bytes_per_file, plan_limits.bytes_per_file, embedded_limits.bytes_per_file),
        bundle_transfer_bytes=min(
            V1_LIMITS.bundle_transfer_bytes,
            plan_limits.bundle_transfer_bytes,
            embedded_limits.bundle_transfer_bytes,
        ),
        total_uncompressed_bytes=min(
            V1_LIMITS.total_uncompressed_bytes,
            plan_limits.total_uncompressed_bytes,
            embedded_limits.total_uncompressed_bytes,
        ),
    )
