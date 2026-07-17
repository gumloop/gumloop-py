from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable
from collections.abc import Mapping

from gumloop.sync.errors import SyncError
from gumloop.types import CliSyncBundleSkill

_FORMAT_PREFIX = b"\x01"


def normalize_relative_path(path: str) -> str:
    """Return the canonical v1 path used by the shared hash fixtures."""
    normalized = path.replace("\\", "/")
    is_windows_absolute = len(normalized) >= 3 and normalized[0].isalpha() and normalized[1:3] == ":/"
    if not normalized or "\x00" in normalized:
        raise SyncError("invalid_desired_state", "Skill content contains an invalid path.")
    if normalized.startswith("/") or is_windows_absolute:
        raise SyncError("invalid_desired_state", f"Skill content path is absolute: {path}")

    parts: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise SyncError("invalid_desired_state", f"Skill content path escapes its root: {path}")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise SyncError("invalid_desired_state", f"Skill content path is empty after normalization: {path}")
    return "/".join(parts)


def _frame(value: bytes) -> bytes:
    return struct.pack(">Q", len(value)) + value


def compute_content_hash(files: Mapping[str, bytes]) -> str:
    """Compute the canonical v1 hash for one complete Skill file map."""
    normalized: dict[bytes, bytes] = {}
    for path, content in files.items():
        encoded_path = normalize_relative_path(path).encode("utf-8")
        if encoded_path in normalized:
            raise SyncError("invalid_desired_state", "Skill content has duplicate normalized paths.")
        normalized[encoded_path] = content

    framing = bytearray(_FORMAT_PREFIX)
    for path in sorted(normalized):
        framing.extend(_frame(path))
        framing.extend(_frame(normalized[path]))
    return hashlib.sha256(framing).hexdigest()


def compute_manifest_hash(skills: Iterable[CliSyncBundleSkill]) -> str:
    """Compute the canonical v1 identity for a complete desired Skill set."""
    framing = bytearray(_FORMAT_PREFIX)
    for skill in sorted(skills, key=lambda item: item.skill_id):
        framing.extend(_frame(skill.skill_id.encode("utf-8")))
        framing.extend(_frame(skill.published_version_id.encode("utf-8")))
        framing.extend(_frame(skill.content_hash.encode("utf-8")))
    return hashlib.sha256(framing).hexdigest()
