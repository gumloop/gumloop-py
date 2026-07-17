from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from gumloop.sync.errors import SyncError
from gumloop.sync.hashing import normalize_relative_path
from gumloop.sync.wire import MANIFEST_FILENAME
from gumloop.sync.wire import MARKER_FILENAME
from gumloop.types import CliSyncLimits


@dataclass(frozen=True)
class ArchiveContents:
    manifest_bytes: bytes
    files_by_install_name: dict[str, dict[str, bytes]]


def read_bundle_archive(
    content: bytes,
    *,
    limits: CliSyncLimits,
) -> ArchiveContents:
    seen_paths: set[str] = set()
    manifest_bytes: bytes | None = None
    files_by_install_name: dict[str, dict[str, bytes]] = {}
    total_uncompressed_bytes = 0

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for info in archive.infolist():
                path = _validated_member_path(info)
                if path in seen_paths:
                    raise SyncError("invalid_desired_state", "The sync bundle archive contains duplicate paths.")
                seen_paths.add(path)

                file_type = stat.S_IFMT(info.external_attr >> 16)
                if info.is_dir():
                    if file_type not in (0, stat.S_IFDIR):
                        raise SyncError(
                            "invalid_desired_state",
                            "The sync bundle archive contains an unsupported entry type.",
                        )
                    continue
                if file_type not in (0, stat.S_IFREG):
                    raise SyncError(
                        "invalid_desired_state",
                        "The sync bundle archive contains an unsupported entry type.",
                    )

                # Check ZipInfo.file_size before read, then again on the bytes, so a
                # lying header cannot bypass limits after decompression.
                _validate_file_limits(
                    size=info.file_size,
                    total=total_uncompressed_bytes + info.file_size,
                    limits=limits,
                )
                file_bytes = archive.read(info)
                total_uncompressed_bytes += len(file_bytes)
                _validate_file_limits(
                    size=len(file_bytes),
                    total=total_uncompressed_bytes,
                    limits=limits,
                )
                if path == MANIFEST_FILENAME:
                    manifest_bytes = file_bytes
                    continue

                install_name, relative_path = _split_skill_path(path)
                if Path(relative_path).name == MARKER_FILENAME:
                    raise SyncError(
                        "invalid_desired_state",
                        "The sync bundle archive contains a reserved marker file.",
                    )
                files_by_install_name.setdefault(install_name, {})[relative_path] = file_bytes
    except zipfile.BadZipFile as error:
        raise SyncError("download_failed", "The sync bundle download is corrupt.") from error

    if manifest_bytes is None:
        raise SyncError(
            "invalid_desired_state",
            "The sync bundle archive must contain exactly one manifest file.",
        )
    return ArchiveContents(
        manifest_bytes=manifest_bytes,
        files_by_install_name=files_by_install_name,
    )


def _validated_member_path(info: zipfile.ZipInfo) -> str:
    raw_name = info.filename
    if "\x00" in raw_name:
        raise SyncError("invalid_desired_state", "The sync bundle archive contains an invalid path.")
    canonical = raw_name.replace("\\", "/").rstrip("/")
    if not canonical:
        raise SyncError("invalid_desired_state", "The sync bundle archive contains an empty path.")
    normalized = normalize_relative_path(canonical)
    if normalized != canonical:
        raise SyncError("invalid_desired_state", "The sync bundle archive contains a non-canonical path.")
    return normalized


def _split_skill_path(path: str) -> tuple[str, str]:
    install_name, separator, relative_path = path.partition("/")
    if not separator or not relative_path:
        raise SyncError(
            "invalid_desired_state",
            "The sync bundle archive contains a root-level file outside the manifest.",
        )
    return install_name, relative_path


def _validate_file_limits(
    *,
    size: int,
    total: int,
    limits: CliSyncLimits,
) -> None:
    if size > limits.bytes_per_file:
        raise SyncError(
            "invalid_desired_state",
            "The sync bundle contains a file that exceeds the per-file byte limit.",
        )
    if total > limits.total_uncompressed_bytes:
        raise SyncError(
            "invalid_desired_state",
            "The sync bundle exceeds the total uncompressed byte limit.",
        )
