"""Behavioral CLI scenario tests for one-shot Skill Sync."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from gumloop.cli.commands._sync_output import SyncOutput
from gumloop.cli.main import app
from gumloop.sync.reconcile import prepare_target_reconciliation
from gumloop.sync.results import SyncProgress
from tests.cli.sync_scenario_helpers import DOWNLOAD_URL
from tests.cli.sync_scenario_helpers import EMPTY_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import MARKER_FILENAME
from tests.cli.sync_scenario_helpers import NEWER_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NEWER_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import NEWER_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import NORMAL_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NORMAL_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import NORMAL_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import SKILL_INSTALL_NAME
from tests.cli.sync_scenario_helpers import agents_skills_root
from tests.cli.sync_scenario_helpers import bundle_with_manifest_fixture
from tests.cli.sync_scenario_helpers import change_for_action
from tests.cli.sync_scenario_helpers import configure_environment
from tests.cli.sync_scenario_helpers import ensure_agents_signal
from tests.cli.sync_scenario_helpers import expected_skill_files
from tests.cli.sync_scenario_helpers import install_skill_from_bundle
from tests.cli.sync_scenario_helpers import invoke_sync
from tests.cli.sync_scenario_helpers import parse_json_envelope
from tests.cli.sync_scenario_helpers import register_download_response
from tests.cli.sync_scenario_helpers import register_plan_error_response
from tests.cli.sync_scenario_helpers import register_plan_response
from tests.cli.sync_scenario_helpers import register_plan_transport_failure
from tests.cli.sync_scenario_helpers import save_configured_credentials
from tests.cli.sync_scenario_helpers import snapshot_skill_tree
from tests.cli.sync_scenario_helpers import write_sync_config
from tests.cli.sync_scenario_helpers import write_sync_state
from tests.cli.sync_test_fakes import SyncCliTestEnvironment


class TestStatelessSync:
    def test_stateless_initial_install_writes_skill_without_sync_state(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Stateless sync installs the shared normal bundle and leaves no sync directory."""
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        skills_root = agents_skills_root(sync_cli_environment.home)

        result = invoke_sync(cli_runner, stateless=True)

        envelope = parse_json_envelope(result)
        skill_dir = skills_root / SKILL_INSTALL_NAME
        marker = json.loads((skill_dir / MARKER_FILENAME).read_text(encoding="utf-8"))
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["error"] is None
        assert expected_skill_files("bundles/normal.zip") == {
            path: (skill_dir / path).read_bytes() for path in expected_skill_files("bundles/normal.zip")
        }
        assert marker["schema_version"] == 1
        assert marker["published_version_id"] == NORMAL_PUBLISHED_VERSION_ID
        assert marker["content_hash"] == NORMAL_CONTENT_HASH
        assert not (sync_cli_environment.home / ".gumloop" / "sync").exists()


class TestHumanReadableSyncOutput:
    def test_default_output_streams_progress_and_ends_with_a_summary(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(
            app,
            ["sync", "--once", "--non-interactive"],
        )

        summary = " ".join(result.stdout.split())
        assert result.exit_code == 0
        assert "✓ Found 1 Skill for 1 agent" in result.stdout
        assert "✓ Downloaded and verified Skill bundle" in result.stdout
        assert "✓ agent-skills — 1 installed" in result.stdout
        assert "Sync complete: 1 installed, 0 failed across 1 agent." in summary
        assert "Changes:" not in result.stdout
        assert "~/.agents/skills" not in result.stdout

    def test_verbose_output_lists_each_changed_skill(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(
            app,
            ["sync", "--once", "--non-interactive", "--verbose"],
        )

        assert result.exit_code == 0
        assert "Changes:" in result.stdout
        assert "installed: acme-api-conventions" in result.stdout

    def test_adoption_appears_in_target_and_summary_output(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
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
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(app, ["sync", "--non-interactive"])

        summary = " ".join(result.stdout.split())
        assert result.exit_code == 0
        assert "1 adopted" in result.stdout
        assert "no changes" not in result.stdout
        assert "Sync complete: 1 adopted, 0 failed across 1 agent." in summary

    def test_default_output_lists_critical_changes_and_backup_paths(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        skills_root = ensure_agents_signal(sync_cli_environment.home)
        skill_dir = skills_root / SKILL_INSTALL_NAME
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("legacy unmarked collision content\n", encoding="utf-8")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(app, ["sync", "--non-interactive"])

        assert result.exit_code == 0
        assert "Changes:" in result.stdout
        assert "replaced: acme-api-conventions" in result.stdout
        assert "backup:" in result.stdout
        assert "installed: acme-api-conventions" not in result.stdout

    def test_blocked_output_prints_reason_and_preservation(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        register_plan_error_response(
            sync_cli_environment.http,
            "responses/below-pro.json",
            status_code=403,
        )

        result = cli_runner.invoke(app, ["sync", "--non-interactive"])

        assert result.exit_code == 1
        assert "Sync blocked: organization_sync_requires_pro." in result.stdout
        assert "Installed Skills were preserved." in result.stdout

    def test_departure_cleanup_streams_target_progress(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Departure reconciliation still advances and completes the human progress spinner."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        register_plan_error_response(
            sync_cli_environment.http,
            "responses/lost-membership.json",
            status_code=403,
        )

        result = cli_runner.invoke(app, ["sync", "--non-interactive"])

        summary = " ".join(result.stdout.split())
        assert result.exit_code == 0
        assert "✓ agent-skills — 1 removed" in result.stdout
        assert "Sync complete: 1 removed, 0 failed across 1 agent." in summary

    def test_partial_target_preparation_failure_summary_reports_failed(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Human partial summary counts a target preparation failure even without failed SyncChanges."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash="0" * 64)
        agents_root = ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        def fail_agents_target(**kwargs: Any):
            target = kwargs["target"]
            if target.skills_root == agents_root:
                raise PermissionError("injected target permissions failure")
            return prepare_target_reconciliation(**kwargs)

        monkeypatch.setattr("gumloop.sync.run.prepare_target_reconciliation", fail_agents_target)

        result = cli_runner.invoke(app, ["sync", "--non-interactive"])

        summary = " ".join(result.stdout.split())
        assert result.exit_code == 1
        assert "✗ agent-skills — injected target permissions failure" in result.stderr
        assert "Sync partial:" in summary
        assert "1 failed" in summary
        assert "0 failed" not in summary

    def test_json_output_remains_one_progress_free_object(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(
            app,
            ["sync", "--once", "--non-interactive", "--json"],
        )

        envelope = json.loads(result.stdout)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert result.stdout.count("\n") == 1
        assert "Resolving managed Skills" not in result.stdout

    @pytest.mark.implementation
    def test_retry_progress_uses_max_attempts(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Retry progress messages include attempt/max when resolving the plan."""
        messages: list[str] = []
        output = SyncOutput()
        monkeypatch.setattr(output, "_start", messages.append)

        output(SyncProgress(stage="resolving_plan", attempt=1, max_attempts=5))
        output(SyncProgress(stage="resolving_plan", attempt=2, max_attempts=5))
        output(SyncProgress(stage="resolving_plan", attempt=3, max_attempts=5))

        assert messages == [
            "Resolving managed Skills…",
            "Desired state changed; retrying (2/5)…",
            "Desired state changed; retrying (3/5)…",
        ]


class TestConfiguredSync:
    def test_configured_idempotent_matching_manifest_skips_download(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Configured sync with matching local state calls plan only and leaves content unchanged."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        before = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        after = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["unchanged"] == 1
        assert after == before

    def test_bundle_newer_than_plan_installs_authoritative_version(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A download bundle newer than the preceding plan replaces the installed Skill hash."""
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv("GUMLOOP_API_KEY", "key")
        monkeypatch.setenv("GUMLOOP_USER_ID", "user_fixture")
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/newer-than-plan.zip")
        skills_root = agents_skills_root(sync_cli_environment.home)

        result = invoke_sync(cli_runner, stateless=True)

        envelope = parse_json_envelope(result)
        marker = json.loads((skills_root / SKILL_INSTALL_NAME / MARKER_FILENAME).read_text(encoding="utf-8"))
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["manifest_hash"] == NEWER_MANIFEST_HASH
        assert marker["published_version_id"] == NEWER_PUBLISHED_VERSION_ID
        assert marker["content_hash"] == NEWER_CONTENT_HASH

    def test_configured_update_replaces_normal_install_with_newer_bundle(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Configured sync updates a valid normal install when a newer bundle arrives."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash="0" * 64)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/newer-than-plan.zip")
        skills_root = agents_skills_root(sync_cli_environment.home)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        marker = json.loads((skills_root / SKILL_INSTALL_NAME / MARKER_FILENAME).read_text(encoding="utf-8"))
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["updated"] == 1
        assert marker["published_version_id"] == NEWER_PUBLISHED_VERSION_ID
        assert marker["content_hash"] == NEWER_CONTENT_HASH

    def test_configured_empty_plan_removes_managed_skill_without_download(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """An empty replacement plan removes a valid managed Skill without calling download."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        register_plan_response(sync_cli_environment.http, "responses/normal-empty-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        skills_root = agents_skills_root(sync_cli_environment.home)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["removed"] == 1
        assert envelope["result"]["manifest_hash"] == EMPTY_MANIFEST_HASH
        assert not (skills_root / SKILL_INSTALL_NAME).exists()


class TestConfiguredMembershipAndPlanLimits:
    def test_configured_departure_removes_managed_skill_and_succeeds(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Lost membership departure removes only the valid managed Skill and exits cleanly."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        register_plan_error_response(
            sync_cli_environment.http,
            "responses/lost-membership.json",
            status_code=403,
        )
        skills_root = agents_skills_root(sync_cli_environment.home)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["departure_cleanup"] is True
        assert envelope["result"]["counts"]["removed"] == 1
        assert not (skills_root / SKILL_INSTALL_NAME).exists()

    def test_configured_below_pro_preserves_installed_skill_and_blocks(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Below-Pro plan rejection preserves installed Skills and exits blocked."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        before = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        register_plan_error_response(
            sync_cli_environment.http,
            "responses/below-pro.json",
            status_code=403,
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        after = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        state = json.loads((sync_cli_environment.home / ".gumloop" / "sync" / "state.json").read_text(encoding="utf-8"))
        assert result.exit_code == 1
        assert envelope["status"] == "blocked"
        assert envelope["result"]["blocked_reason"] == "organization_sync_requires_pro"
        assert after == before
        assert state["status"] == "blocked"


class TestConfiguredLocalConflicts:
    def test_configured_invalid_marker_is_preserved_on_empty_plan(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """An invalid marker Skill is preserved when the desired plan is empty."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        skills_root = ensure_agents_signal(sync_cli_environment.home)
        skill_dir = skills_root / SKILL_INSTALL_NAME
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("invalid marker fixture\n", encoding="utf-8")
        (skill_dir / MARKER_FILENAME).write_text("{not-json", encoding="utf-8")
        before = snapshot_skill_tree(skills_root)
        register_plan_response(sync_cli_environment.http, "responses/normal-empty-plan.json")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        after = snapshot_skill_tree(skills_root)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["removed"] == 0
        assert after == before

    def test_configured_unmarked_collision_is_backed_up_and_overwritten(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """An unmarked same-name collision is backed up before the managed Skill is installed."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        skills_root = ensure_agents_signal(sync_cli_environment.home)
        skill_dir = skills_root / SKILL_INSTALL_NAME
        skill_dir.mkdir(parents=True)
        old_content = b"legacy unmarked collision content\n"
        (skill_dir / "SKILL.md").write_bytes(old_content)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        collision_change = change_for_action(envelope, "overwritten_collision")
        expected_backup = Path(collision_change["backup_path"])
        backup_skill = expected_backup / "SKILL.md"
        installed_skill = skill_dir / "SKILL.md"
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["overwritten_collision"] == 1
        assert backup_skill.read_bytes() == old_content
        assert installed_skill.read_bytes() == expected_skill_files("bundles/normal.zip")["SKILL.md"]
        assert collision_change["backup_path"] == str(expected_backup)

    def test_configured_local_edit_is_backed_up_and_overwritten(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A locally edited managed Skill is backed up before the authoritative bundle overwrites it."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        skills_root = agents_skills_root(sync_cli_environment.home)
        edited_path = skills_root / SKILL_INSTALL_NAME / "examples.md"
        edited_bytes = b"local edit that must be recoverable\n"
        edited_path.write_bytes(edited_bytes)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/newer-than-plan.zip")
        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        local_edit_change = change_for_action(envelope, "overwritten_local_edit")
        expected_backup = Path(local_edit_change["backup_path"])
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["counts"]["overwritten_local_edit"] == 1
        assert (expected_backup / "examples.md").read_bytes() == edited_bytes


class TestConfiguredSyncFailures:
    def test_configured_corrupt_bundle_preserves_existing_target(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A mismatched shared bundle fails with a stable error and leaves the target unchanged."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash="0" * 64)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        before = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(
            sync_cli_environment.http,
            "bundles/normal.zip",
            content=bundle_with_manifest_fixture(
                "bundles/normal.zip",
                "manifests/invalid-manifest-hash.json",
            ),
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        after = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "invalid_desired_state"
        assert after == before
        assert (sync_cli_environment.home / ".gumloop" / "sync" / "state.json").is_file()

    def test_repeated_context_change_preserves_existing_target(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Repeated pre-download context changes exhaust safely without target writes."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash="0" * 64)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        skills_root = agents_skills_root(sync_cli_environment.home)
        before = snapshot_skill_tree(skills_root)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        sync_cli_environment.http.post(DOWNLOAD_URL).mock(
            return_value=httpx.Response(
                409,
                json={
                    "error": {
                        "code": "sync_context_changed",
                        "message": "Authorization context changed.",
                    }
                },
            )
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "download_failed"
        assert snapshot_skill_tree(skills_root) == before

    @pytest.mark.parametrize(
        ("register_failure", "expected_code"),
        [
            pytest.param(
                lambda http: http.post("https://api.gumloop.com/api/v1/skills/sync/plan").mock(
                    return_value=httpx.Response(
                        401,
                        json={
                            "error": {
                                "code": "authentication_error",
                                "message": "Invalid API key.",
                                "type": "auth_error",
                            }
                        },
                    )
                ),
                "auth_required",
                id="authentication",
            ),
            pytest.param(
                lambda http: register_plan_transport_failure(http, httpx.ConnectError("connection refused")),
                "download_failed",
                id="transport",
            ),
            pytest.param(
                lambda http: http.post("https://api.gumloop.com/api/v1/skills/sync/plan").mock(
                    return_value=httpx.Response(
                        500,
                        json={"error": {"code": "internal_error", "message": "server exploded", "type": "api_error"}},
                    )
                ),
                "download_failed",
                id="plan-5xx",
            ),
        ],
    )
    def test_configured_plan_failures_preserve_existing_target(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        register_failure: object,
        expected_code: str,
    ) -> None:
        """Plan authentication, transport, and server failures preserve arranged target content."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        before = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        register_failure(sync_cli_environment.http)  # type: ignore[operator]

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        after = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == expected_code
        assert after == before
        assert (sync_cli_environment.home / ".gumloop" / "sync" / "state.json").is_file()


class TestStatelessValidation:
    @pytest.mark.parametrize(
        ("extra_args", "environment", "expected_code"),
        [
            pytest.param(
                ["--once", "--non-interactive", "--json"],
                {"GUMLOOP_API_KEY": "key", "GUMLOOP_USER_ID": None},
                "auth_required",
                id="missing-env-auth",
            ),
        ],
    )
    def test_stateless_validation_fails_without_writing_targets(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        extra_args: list[str],
        environment: dict[str, str | None],
        expected_code: str,
    ) -> None:
        """Stateless validation errors use stable codes and create no Skill writes."""
        ensure_agents_signal(sync_cli_environment.home)
        configure_environment(monkeypatch, environment)
        skills_root = agents_skills_root(sync_cli_environment.home)

        result = cli_runner.invoke(app, ["sync", *extra_args])

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == expected_code
        assert snapshot_skill_tree(skills_root) == {}
