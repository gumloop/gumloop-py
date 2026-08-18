from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gumloop.cli.main import app


@pytest.fixture(autouse=True)
def _no_cursor_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from the host machine's Cursor.app install."""
    monkeypatch.setattr("gumloop.sync.targets._default_cursor_app_exists", lambda: False)


def test_plugin_install_copies_skill_into_detected_targets(cli_runner: CliRunner, temporary_home: Path) -> None:
    (temporary_home / ".claude").mkdir()

    result = cli_runner.invoke(app, ["plugin", "install", "gumloop", "--json"])

    assert result.exit_code == 0, result.output
    installed = temporary_home / ".claude" / "skills" / "gumloop-cli"
    assert (installed / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (installed / "references" / "commands.md").exists()
    summary = json.loads(result.output)
    assert str(installed) in summary["installed"]


def test_plugin_install_writes_no_sync_ownership_marker(cli_runner: CliRunner, temporary_home: Path) -> None:
    (temporary_home / ".claude").mkdir()

    result = cli_runner.invoke(app, ["plugin", "install", "gumloop"])

    assert result.exit_code == 0, result.output
    # `gumloop sync` reconciliation must never claim these skills, so no
    # .gumloop.json marker may be present.
    assert not (temporary_home / ".claude" / "skills" / "gumloop-cli" / ".gumloop.json").exists()


def test_plugin_install_skips_existing_without_force(cli_runner: CliRunner, temporary_home: Path) -> None:
    existing = temporary_home / ".claude" / "skills" / "gumloop-cli"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("user edited", encoding="utf-8")

    result = cli_runner.invoke(app, ["plugin", "install", "gumloop", "--json"])

    assert result.exit_code == 0, result.output
    assert (existing / "SKILL.md").read_text(encoding="utf-8") == "user edited"
    summary = json.loads(result.output)
    assert str(existing) in summary["skipped"]
    assert summary["installed"] == []


def test_plugin_install_force_replaces_existing(cli_runner: CliRunner, temporary_home: Path) -> None:
    existing = temporary_home / ".claude" / "skills" / "gumloop-cli"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("user edited", encoding="utf-8")
    (existing / "stale-file.md").write_text("stale", encoding="utf-8")

    result = cli_runner.invoke(app, ["plugin", "install", "gumloop", "--force"])

    assert result.exit_code == 0, result.output
    assert (existing / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert not (existing / "stale-file.md").exists()


def test_plugin_install_dir_writes_full_plugin_package(cli_runner: CliRunner, tmp_path: Path) -> None:
    destination = tmp_path / "plugins"

    result = cli_runner.invoke(app, ["plugin", "install", "gumloop", "--dir", str(destination)])

    assert result.exit_code == 0, result.output
    package = destination / "gumloop"
    manifest = json.loads((package / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "gumloop"
    assert (package / "skills" / "gumloop-cli" / "SKILL.md").exists()


def test_plugin_install_unknown_name_lists_available_plugins(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["plugin", "install", "does-not-exist"])

    combined = result.output + (result.stderr or "")
    assert result.exit_code == 1
    assert "Unknown plugin: does-not-exist" in combined
    assert "gumloop" in combined


def test_plugin_install_errors_when_no_agents_detected(cli_runner: CliRunner, temporary_home: Path) -> None:
    result = cli_runner.invoke(app, ["plugin", "install", "gumloop"])

    combined = result.output + (result.stderr or "")
    assert result.exit_code == 1
    assert "No supported coding agent was detected" in combined
