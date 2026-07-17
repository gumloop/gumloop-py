from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_LOGICAL_TARGET_AGENT_SKILLS = "agent_skills"
_LOGICAL_TARGET_CLAUDE_CODE = "claude_code"
_LOGICAL_TARGET_CODEX = "codex"
_LOGICAL_TARGET_CURSOR = "cursor"

_CURSOR_APP_PATH = Path("/Applications/Cursor.app")


@dataclass(frozen=True)
class PhysicalTarget:
    skills_root: Path
    logical_targets: tuple[str, ...]


def detect_targets(
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    cursor_app_exists: Callable[[], bool] | None = None,
) -> tuple[PhysicalTarget, ...]:
    """Return detected skill install locations without creating directories."""
    home_path = home if home is not None else Path.home()
    cursor_app_present = cursor_app_exists if cursor_app_exists is not None else _default_cursor_app_exists

    logical_to_root: dict[str, Path] = {}

    if (home_path / ".agents").exists():
        logical_to_root[_LOGICAL_TARGET_AGENT_SKILLS] = home_path / ".agents" / "skills"

    if which("claude") is not None or (home_path / ".claude").exists():
        logical_to_root[_LOGICAL_TARGET_CLAUDE_CODE] = home_path / ".claude" / "skills"

    if which("codex") is not None or (home_path / ".codex").exists():
        logical_to_root[_LOGICAL_TARGET_CODEX] = home_path / ".agents" / "skills"

    if which("cursor-agent") is not None or (home_path / ".cursor").exists() or cursor_app_present():
        logical_to_root[_LOGICAL_TARGET_CURSOR] = home_path / ".agents" / "skills"

    grouped: dict[Path, list[str]] = {}
    for logical_target, skills_root in logical_to_root.items():
        resolved_root = skills_root.resolve()
        grouped.setdefault(resolved_root, []).append(logical_target)

    physical_targets = [
        PhysicalTarget(
            skills_root=skills_root,
            logical_targets=tuple(sorted(logical_names)),
        )
        for skills_root, logical_names in grouped.items()
    ]
    physical_targets.sort(key=lambda target: target.skills_root)
    return tuple(physical_targets)


def _default_cursor_app_exists() -> bool:
    return _CURSOR_APP_PATH.exists()
