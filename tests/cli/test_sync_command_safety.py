"""Command-level safety scenarios for one-shot Skill Sync."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from gumloop.sync.lock import sync_lock
from gumloop.sync.reconcile import prepare_target_reconciliation
from gumloop.sync.results import SyncProgress
from gumloop.sync.run import run_sync
from tests.cli.sync_scenario_helpers import MARKER_FILENAME
from tests.cli.sync_scenario_helpers import NORMAL_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NORMAL_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import NORMAL_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import SKILL_INSTALL_NAME
from tests.cli.sync_scenario_helpers import agents_skills_root
from tests.cli.sync_scenario_helpers import ensure_agents_signal
from tests.cli.sync_scenario_helpers import expected_skill_files
from tests.cli.sync_scenario_helpers import install_skill_from_bundle
from tests.cli.sync_scenario_helpers import invoke_sync
from tests.cli.sync_scenario_helpers import parse_json_envelope
from tests.cli.sync_scenario_helpers import register_download_response
from tests.cli.sync_scenario_helpers import register_plan_response
from tests.cli.sync_scenario_helpers import save_configured_credentials
from tests.cli.sync_scenario_helpers import skill_content_files
from tests.cli.sync_scenario_helpers import write_sync_config
from tests.cli.sync_scenario_helpers import write_sync_state
from tests.cli.sync_test_fakes import SyncCliTestEnvironment
from tests.sdk.helpers import API_BASE
from tests.skill_sync_fixtures import load_json


class TestAdoptionAndCollision:
    def test_matching_unmarked_content_is_adopted_without_backup(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Exact unmarked content receives only an ownership marker."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash="0" * 64)
        skill_dir = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        (skill_dir / MARKER_FILENAME).unlink()
        before = skill_content_files(skill_dir)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        after = skill_content_files(skill_dir)
        backups = sync_cli_environment.home / ".gumloop" / "sync" / "backups"
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["adopted"] == 1
        assert before == after
        assert list(backups.iterdir()) == []

    def test_stateless_collision_overwrites_without_retained_backup(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Stateless sync reports a collision but creates no persistent backup state."""
        skills_root = ensure_agents_signal(sync_cli_environment.home)
        collision = skills_root / SKILL_INSTALL_NAME
        collision.mkdir(parents=True)
        (collision / "SKILL.md").write_text("local collision", encoding="utf-8")
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner, stateless=True)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["overwritten_collision"] == 1
        assert envelope["result"]["changes"][0]["backup_path"] is None
        assert not (sync_cli_environment.home / ".gumloop" / "sync").exists()


class TestLockAndTargetGates:
    def test_stateless_nonempty_plan_without_targets_returns_no_targets(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A stateless non-empty plan fails before download when no agent is detected."""
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        monkeypatch.setattr("gumloop.sync.targets._default_cursor_app_exists", lambda: False)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")

        result = invoke_sync(cli_runner, stateless=True)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "no_targets"
        assert not agents_skills_root(sync_cli_environment.home).exists()

    def test_held_sync_lock_rejects_second_command_before_http(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Configured and stateless runs contend on the same per-home lock."""
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")

        with sync_lock(home=sync_cli_environment.home):
            result = invoke_sync(cli_runner, stateless=True)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "sync_in_progress"
        assert not (sync_cli_environment.home / ".gumloop" / "sync").exists()


class TestEmptyPlanAndMarkerSchema:
    def test_empty_plan_removes_real_install_and_shared_symlink(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Empty convergence removes both an owned directory and its safe shared link."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        linked_root = sync_cli_environment.home / ".claude" / "skills"
        linked_root.mkdir(parents=True)
        linked = linked_root / SKILL_INSTALL_NAME
        linked.symlink_to(installed, target_is_directory=True)
        register_plan_response(sync_cli_environment.http, "responses/normal-empty-plan.json")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["removed"] == 2
        assert not installed.exists()
        assert not linked.is_symlink()

    def test_newer_marker_schema_fails_target_without_mutation(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A newer marker schema grants no authority to an older CLI."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        marker_path = installed / MARKER_FILENAME
        marker_path.write_text(
            '{"schema_version":2,"organization_id":"org_fixture"}\n',
            encoding="utf-8",
        )
        before = skill_content_files(installed)
        register_plan_response(sync_cli_environment.http, "responses/normal-empty-plan.json")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "partial"
        assert envelope["result"]["physical_targets"][0]["error"]["code"] == "unsupported_version"
        assert skill_content_files(installed) == before
        assert '"schema_version":2' in marker_path.read_text(encoding="utf-8")

    def test_matching_manifest_does_not_skip_newer_marker_schema(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """The matching-manifest fast path still rejects a newer marker schema."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        before = skill_content_files(installed)
        future_skill = agents_skills_root(sync_cli_environment.home) / "future-skill"
        future_skill.mkdir()
        future_marker = future_skill / MARKER_FILENAME
        future_marker.write_text(
            '{"schema_version":2,"organization_id":"org_fixture"}\n',
            encoding="utf-8",
        )
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "partial"
        assert envelope["result"]["physical_targets"][0]["error"]["code"] == "unsupported_version"
        assert skill_content_files(installed) == before
        assert future_marker.read_text(encoding="utf-8").startswith('{"schema_version":2')


class TestMultiTargetIsolation:
    def test_target_filesystem_error_does_not_stop_other_targets(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A raw filesystem error at one target still allows later targets to converge."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash="0" * 64)
        agents_root = ensure_agents_signal(sync_cli_environment.home)
        claude_root = sync_cli_environment.home / ".claude" / "skills"
        claude_root.parent.mkdir()
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        def fail_agents_target(**kwargs: Any):
            target = kwargs["target"]
            if target.skills_root == agents_root:
                raise PermissionError("injected target permissions failure")
            return prepare_target_reconciliation(**kwargs)

        monkeypatch.setattr("gumloop.sync.run.prepare_target_reconciliation", fail_agents_target)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        physical_targets = envelope["result"]["physical_targets"]
        assert result.exit_code == 1
        assert envelope["status"] == "partial"
        assert physical_targets[0]["error"]["code"] == "target_failed"
        assert physical_targets[1]["error"] is None
        assert not (agents_root / SKILL_INSTALL_NAME).exists()
        assert (claude_root / SKILL_INSTALL_NAME).is_dir()


class TestDepartureAndInvalidPlan:
    def test_successful_departure_clears_rolling_backups(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Final departure cleanup removes the configured organization's backup tree."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        backups = sync_cli_environment.home / ".gumloop" / "sync" / "backups"
        (backups / "old-target" / SKILL_INSTALL_NAME).mkdir(parents=True)
        (backups / "old-target" / SKILL_INSTALL_NAME / "SKILL.md").write_text("old backup", encoding="utf-8")
        sync_cli_environment.http.post(f"{API_BASE}/skills/sync/plan").mock(
            return_value=httpx.Response(
                403,
                json=load_json("responses/lost-membership.json"),
            )
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["departure_cleanup"] is True
        assert not backups.exists()

    def test_invalid_empty_manifest_hash_preserves_installed_skill(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """An empty plan with the wrong identity cannot authorize removals."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        before = skill_content_files(installed)
        payload = load_json("responses/normal-empty-plan.json")
        payload["manifest"]["hash"] = "0" * 64
        sync_cli_environment.http.post(f"{API_BASE}/skills/sync/plan").mock(
            return_value=httpx.Response(
                200,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "invalid_desired_state"
        assert skill_content_files(installed) == before


class TestProgressObserverIsolation:
    def test_progress_callback_exception_does_not_prevent_install(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A progress observer exception after target mutation must not undo a successful install."""
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        skills_root = agents_skills_root(sync_cli_environment.home)
        seen_stages: list[str] = []

        def exploding_progress(progress: SyncProgress) -> None:
            seen_stages.append(progress.stage)
            raise RuntimeError(f"progress renderer failed during {progress.stage}")

        def run_sync_with_exploding_progress(**kwargs: Any):
            return run_sync(**{**kwargs, "on_progress": exploding_progress})

        monkeypatch.setattr("gumloop.cli.commands.sync.run_sync", run_sync_with_exploding_progress)

        result = invoke_sync(cli_runner, stateless=True)

        envelope = parse_json_envelope(result)
        skill_dir = skills_root / SKILL_INSTALL_NAME
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["installed"] == 1
        assert "target_complete" in seen_stages
        assert expected_skill_files("bundles/normal.zip") == {
            path: (skill_dir / path).read_bytes() for path in expected_skill_files("bundles/normal.zip")
        }
