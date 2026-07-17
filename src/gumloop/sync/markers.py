from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError
from pydantic import model_validator

from gumloop.sync.errors import SyncError
from gumloop.sync.hashing import compute_content_hash
from gumloop.sync.wire import MANIFEST_FILENAME
from gumloop.sync.wire import MARKER_FILENAME
from gumloop.sync.wire import SYNC_WORKSPACE_DIRNAME


class OwnershipMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    organization_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    published_version_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    installed_at: datetime

    @model_validator(mode="after")
    def validate_installed_at(self) -> OwnershipMarker:
        if self.installed_at.tzinfo is None or self.installed_at.utcoffset() is None:
            raise ValueError("installed_at must be timezone-aware")
        return self


@dataclass(frozen=True)
class MarkerRead:
    status: Literal["valid", "unmarked", "invalid", "unsupported"]
    marker: OwnershipMarker | None = None
    reason: str | None = None


def is_safe_install_name(name: str) -> bool:
    return bool(
        name
        and name not in (".", "..")
        and name != MARKER_FILENAME
        and name != MANIFEST_FILENAME
        and name != SYNC_WORKSPACE_DIRNAME
        and "/" not in name
        and "\\" not in name
        and "\x00" not in name
        and not any(ord(character) < 32 for character in name)
    )


def read_marker(skill_path: Path, organization_id: str) -> MarkerRead:
    marker_path = skill_path / MARKER_FILENAME
    if not marker_path.exists():
        return MarkerRead("unmarked")
    if marker_path.is_symlink() or not marker_path.is_file():
        return MarkerRead("invalid", reason="ownership marker is not a regular file")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return MarkerRead("invalid", reason=str(error))
    if isinstance(payload, dict) and isinstance(payload.get("schema_version"), int):
        if payload["schema_version"] > 1:
            return MarkerRead("unsupported", reason=f"unsupported marker schema {payload['schema_version']}")
    try:
        marker = OwnershipMarker.model_validate(payload)
    except ValidationError as error:
        return MarkerRead("invalid", reason=str(error))
    if not is_safe_install_name(marker.name):
        return MarkerRead("invalid", reason="marker name is not a safe install name")
    if marker.name != skill_path.name:
        return MarkerRead("invalid", reason="marker name does not match its parent directory")
    if marker.organization_id != organization_id:
        return MarkerRead("invalid", reason="marker belongs to another organization")
    return MarkerRead("valid", marker=marker)


def directory_content_hash(skill_path: Path) -> str:
    files: dict[str, bytes] = {}
    try:
        entries = sorted(skill_path.rglob("*"))
    except OSError as error:
        raise SyncError("target_failed", f"Could not inspect installed Skill: {skill_path}") from error
    for entry in entries:
        relative_path = entry.relative_to(skill_path).as_posix()
        if relative_path == MARKER_FILENAME:
            continue
        if entry.is_symlink():
            raise SyncError("target_failed", f"Refusing to follow symlinked Skill content: {entry}")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise SyncError("target_failed", f"Skill content is not a regular file: {entry}")
        try:
            files[relative_path] = entry.read_bytes()
        except OSError as error:
            raise SyncError("target_failed", f"Could not read installed Skill content: {entry}") from error
    return compute_content_hash(files)


def build_marker(
    *,
    organization_id: str,
    skill_id: str,
    name: str,
    published_version_id: str,
    content_hash: str,
    installed_at: datetime,
) -> OwnershipMarker:
    return OwnershipMarker(
        schema_version=1,
        organization_id=organization_id,
        skill_id=skill_id,
        name=name,
        published_version_id=published_version_id,
        content_hash=content_hash,
        installed_at=installed_at,
    )


def write_marker_atomic(skill_path: Path, marker: OwnershipMarker) -> None:
    marker_path = skill_path / MARKER_FILENAME
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=skill_path,
            prefix=f".{MARKER_FILENAME}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                marker.model_dump(mode="json"),
                temporary,
                sort_keys=True,
                separators=(",", ":"),
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(marker_path)
        temporary_path = None
    except OSError as error:
        raise SyncError("target_failed", f"Could not write ownership marker: {marker_path}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
