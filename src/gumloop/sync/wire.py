from __future__ import annotations

from gumloop.types import CliSyncLimits

CLI_VERSION_HEADER = "X-Gumloop-CLI-Version"
BUNDLE_CONTENT_TYPE = "application/zip"
MANIFEST_FILENAME = "gumloop-sync-manifest.json"
MARKER_FILENAME = ".gumloop.json"
SYNC_WORKSPACE_DIRNAME = ".gumloop-sync-work"
V1_LIMITS = CliSyncLimits(
    files_per_skill=1_000,
    bytes_per_file=26_214_400,
    bundle_transfer_bytes=104_857_600,
    total_uncompressed_bytes=209_715_200,
)
