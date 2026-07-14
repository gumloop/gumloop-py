from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures/skill_sync/v1"
EXPECTED_CORPUS_SHA256 = "a06d90dd2eb67b52e2974b2a2b8f152e34f0ef3d1d9dfb357715027d9dc7b0ed"


def load_json(relative_path: str) -> Any:
    return json.loads((FIXTURE_ROOT / relative_path).read_text())


def load_catalog() -> dict[str, Any]:
    value = load_json("catalog.json")
    if not isinstance(value, dict):
        raise TypeError("catalog.json must contain an object")
    return value


def calculate_corpus_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(FIXTURE_ROOT.rglob("*")):
        if not path.is_file() or path.name == "corpus.sha256":
            continue
        relative_path = path.relative_to(FIXTURE_ROOT).as_posix().encode()
        digest.update(struct.pack(">Q", len(relative_path)))
        digest.update(relative_path)
        content = path.read_bytes()
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
    return digest.hexdigest()
