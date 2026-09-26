from __future__ import annotations

import hashlib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from gumloop.types import BrainFile

_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class LocalFile:
    name: str
    path: Path
    sha256: str


def scan_directory(directory: Path) -> list[LocalFile]:
    """Every regular file under ``directory``, named by its POSIX path relative to the root."""
    files = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        if any(part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
        files.append(LocalFile(name=path.relative_to(directory).as_posix(), path=path, sha256=digest.hexdigest()))
    return files


@dataclass(frozen=True)
class BrainSyncPlan:
    upload: list[LocalFile] = field(default_factory=list)
    replace: list[BrainFile] = field(default_factory=list)
    prune: list[BrainFile] = field(default_factory=list)
    unchanged: list[LocalFile] = field(default_factory=list)

    @classmethod
    def build(cls, local: list[LocalFile], remote: list[BrainFile]) -> BrainSyncPlan:
        """Diff by (name, sha256). A remote file without ``sha256`` predates hashing and is re-uploaded."""
        remote_by_name = {remote_file.file_name: remote_file for remote_file in remote}
        upload, replace, unchanged = [], [], []
        for local_file in local:
            remote_file = remote_by_name.pop(local_file.name, None)
            if remote_file is None:
                upload.append(local_file)
            elif remote_file.sha256 == local_file.sha256:
                unchanged.append(local_file)
            else:
                replace.append(remote_file)
                upload.append(local_file)
        return cls(upload=upload, replace=replace, prune=list(remote_by_name.values()), unchanged=unchanged)

    @property
    def is_noop(self) -> bool:
        return not (self.upload or self.replace or self.prune)
