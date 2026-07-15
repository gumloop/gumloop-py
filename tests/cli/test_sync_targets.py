"""Behavioral tests for Skill Sync target discovery."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from gumloop.sync.targets import PhysicalTarget
from gumloop.sync.targets import detect_targets


def _detect_targets(
    *,
    home: Path,
    which: Callable[[str], str | None] | None = None,
    cursor_app_exists: Callable[[], bool] | None = None,
) -> tuple[PhysicalTarget, ...]:
    kwargs: dict[str, object] = {
        "home": home,
        "cursor_app_exists": cursor_app_exists if cursor_app_exists is not None else (lambda: False),
    }
    if which is not None:
        kwargs["which"] = which
    return detect_targets(**kwargs)  # type: ignore[arg-type]


def _write_executable(executable_path: Path, name: str) -> Path:
    executable = executable_path / name
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    return executable


class TestDetectTargetsEmpty:
    def test_detect_targets_returns_empty_when_no_signals_exist(self, temporary_home: Path) -> None:
        """Discovery reports no targets when no agent signals are present."""
        targets = _detect_targets(home=temporary_home)

        assert targets == ()

    def test_detect_targets_creates_no_directories(self, temporary_home: Path) -> None:
        """Target discovery performs read-only filesystem inspection."""
        before = sorted(temporary_home.iterdir())

        _detect_targets(
            home=temporary_home,
            which=lambda name: name,
            cursor_app_exists=lambda: True,
        )

        after = sorted(temporary_home.iterdir())

        assert after == before


class TestDetectTargetsBySignal:
    def test_detect_targets_finds_agent_skills_from_agents_directory(self, temporary_home: Path) -> None:
        """Agent Skills is detected when the home `.agents` directory exists."""
        (temporary_home / ".agents").mkdir()

        targets = _detect_targets(home=temporary_home)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("agent_skills",),
            ),
        )

    def test_detect_targets_finds_claude_code_from_executable(
        self,
        temporary_home: Path,
        fake_executable_path: Path,
    ) -> None:
        """Claude Code is detected when the `claude` executable is on PATH."""
        _write_executable(fake_executable_path, "claude")

        targets = _detect_targets(home=temporary_home, which=shutil.which)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".claude" / "skills").resolve(),
                logical_targets=("claude_code",),
            ),
        )

    def test_detect_targets_finds_claude_code_from_claude_directory(self, temporary_home: Path) -> None:
        """Claude Code is detected when the home `.claude` directory exists."""
        (temporary_home / ".claude").mkdir()

        targets = _detect_targets(home=temporary_home)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".claude" / "skills").resolve(),
                logical_targets=("claude_code",),
            ),
        )

    def test_detect_targets_finds_codex_from_executable(
        self,
        temporary_home: Path,
        fake_executable_path: Path,
    ) -> None:
        """Codex is detected when the `codex` executable is on PATH."""
        _write_executable(fake_executable_path, "codex")

        targets = _detect_targets(home=temporary_home, which=shutil.which)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("codex",),
            ),
        )

    def test_detect_targets_finds_codex_from_codex_directory(self, temporary_home: Path) -> None:
        """Codex is detected when the home `.codex` directory exists."""
        (temporary_home / ".codex").mkdir()

        targets = _detect_targets(home=temporary_home)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("codex",),
            ),
        )

    def test_detect_targets_finds_cursor_from_executable(
        self,
        temporary_home: Path,
        fake_executable_path: Path,
    ) -> None:
        """Cursor is detected when the `cursor-agent` executable is on PATH."""
        _write_executable(fake_executable_path, "cursor-agent")

        targets = _detect_targets(home=temporary_home, which=shutil.which)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("cursor",),
            ),
        )

    def test_detect_targets_finds_cursor_from_cursor_directory(self, temporary_home: Path) -> None:
        """Cursor is detected when the home `.cursor` directory exists."""
        (temporary_home / ".cursor").mkdir()

        targets = _detect_targets(home=temporary_home)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("cursor",),
            ),
        )

    def test_detect_targets_finds_cursor_from_cursor_app_injection(self, temporary_home: Path) -> None:
        """Cursor is detected when the injected Cursor.app presence check succeeds."""
        targets = detect_targets(home=temporary_home, which=lambda _name: None, cursor_app_exists=lambda: True)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("cursor",),
            ),
        )

    def test_detect_targets_resolves_skills_root_without_existing_directory(self, temporary_home: Path) -> None:
        """Discovery resolves install roots even when the skills directory is missing."""
        (temporary_home / ".agents").mkdir()

        targets = _detect_targets(home=temporary_home)

        skills_root = targets[0].skills_root
        assert skills_root == (temporary_home / ".agents" / "skills").resolve()
        assert not skills_root.exists()


class TestDetectTargetsComposition:
    def test_detect_targets_deduplicates_shared_agents_skills_root(self, temporary_home: Path) -> None:
        """Agent Skills, Codex, and Cursor share one physical target when detected together."""
        (temporary_home / ".agents").mkdir()
        (temporary_home / ".codex").mkdir()

        targets = _detect_targets(
            home=temporary_home,
            which=lambda name: "cursor-agent" if name == "cursor-agent" else None,
        )

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("agent_skills", "codex", "cursor"),
            ),
        )

    def test_detect_targets_sorts_physical_targets_by_skills_root(self, temporary_home: Path) -> None:
        """Multiple physical roots are returned in deterministic path order."""
        (temporary_home / ".agents").mkdir()
        (temporary_home / ".claude").mkdir()

        targets = _detect_targets(home=temporary_home)

        assert targets == (
            PhysicalTarget(
                skills_root=(temporary_home / ".agents" / "skills").resolve(),
                logical_targets=("agent_skills",),
            ),
            PhysicalTarget(
                skills_root=(temporary_home / ".claude" / "skills").resolve(),
                logical_targets=("claude_code",),
            ),
        )
