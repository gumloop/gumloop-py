from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError
from pydantic import model_validator

from gumloop.sync.errors import SyncError


class SyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    organization_id: str = Field(min_length=1)
    scheduler_gumloop_path: str

    @model_validator(mode="after")
    def validate_scheduler_path(self) -> SyncConfig:
        if not Path(self.scheduler_gumloop_path).is_absolute():
            raise ValueError("scheduler_gumloop_path must be absolute")
        return self


class SyncState(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal[1]
    status: Literal["success", "partial", "blocked", "error", "departure_cleanup"]
    manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    last_success_at: str | None = None
    last_result: dict[str, Any]


def sync_root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".gumloop" / "sync"


def load_config(home: Path | None = None) -> SyncConfig:
    path = sync_root(home) / "config.json"
    if not path.exists():
        raise SyncError(
            "not_configured",
            "Skill sync is not configured. Run `gumloop sync` to enroll this machine.",
            details={"path": str(path)},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SyncConfig.model_validate(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise SyncError(
            "invalid_config",
            f"Skill sync configuration is invalid: {path}",
            details={"path": str(path), "reason": str(error)},
        ) from error


def load_state(home: Path | None = None) -> SyncState | None:
    path = sync_root(home) / "state.json"
    if not path.exists():
        return None
    try:
        return SyncState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError):
        return None


def write_config(config: SyncConfig, home: Path | None = None) -> Path:
    root = _ensure_sync_root(home)
    destination = root / "config.json"
    _atomic_json_write(
        destination,
        config.model_dump(mode="json"),
        description="sync configuration",
    )
    return destination


def remove_config(home: Path | None = None) -> None:
    destination = sync_root(home) / "config.json"
    try:
        destination.unlink(missing_ok=True)
    except OSError as error:
        raise SyncError(
            "target_failed",
            f"Could not remove sync configuration: {destination}",
            details={"path": str(destination), "reason": str(error)},
        ) from error


def write_state(payload: dict[str, Any], home: Path | None = None) -> Path:
    root = _ensure_sync_root(home)
    destination = root / "state.json"
    _atomic_json_write(destination, payload, description="local sync state")
    return destination


def _ensure_sync_root(home: Path | None = None) -> Path:
    root = sync_root(home)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def backup_root(home: Path | None = None) -> Path:
    root = sync_root(home) / "backups"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def _atomic_json_write(
    destination: Path,
    payload: dict[str, Any],
    *,
    description: str,
) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary_path.chmod(0o600)
            json.dump(payload, temporary, sort_keys=True, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
        temporary_path = None
        try:
            destination.chmod(0o600)
        except OSError:
            pass
    except OSError as error:
        raise SyncError(
            "target_failed",
            f"Could not write {description}: {destination}",
            details={"path": str(destination), "reason": str(error)},
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
