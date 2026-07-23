"""Behavioral CLI scenarios for first-time Skill Sync enrollment."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import load_credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from gumloop.sync.errors import SyncError
from gumloop.sync.reconcile import prepare_target_reconciliation
from tests.cli.sync_scenario_helpers import MARKER_FILENAME
from tests.cli.sync_scenario_helpers import NORMAL_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NORMAL_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import NORMAL_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import ORGANIZATION_ID
from tests.cli.sync_scenario_helpers import PLAN_URL
from tests.cli.sync_scenario_helpers import SKILL_INSTALL_NAME
from tests.cli.sync_scenario_helpers import agents_skills_root
from tests.cli.sync_scenario_helpers import bundle_with_manifest_fixture
from tests.cli.sync_scenario_helpers import ensure_agents_signal
from tests.cli.sync_scenario_helpers import expected_skill_files
from tests.cli.sync_scenario_helpers import install_skill_from_bundle
from tests.cli.sync_scenario_helpers import invoke_sync
from tests.cli.sync_scenario_helpers import parse_json_envelope
from tests.cli.sync_scenario_helpers import register_download_response
from tests.cli.sync_scenario_helpers import register_plan_error_response
from tests.cli.sync_scenario_helpers import register_plan_response
from tests.cli.sync_scenario_helpers import save_configured_credentials
from tests.cli.sync_scenario_helpers import snapshot_skill_tree
from tests.cli.sync_scenario_helpers import write_sync_config
from tests.cli.sync_scenario_helpers import write_sync_state
from tests.cli.sync_test_fakes import SyncCliTestEnvironment
from tests.sdk.helpers import OAUTH_BASE
from tests.skill_sync_fixtures import load_json


def _gumloop_executable(environment: SyncCliTestEnvironment) -> Path:
    return environment.executable_path / "gumloop"


def _sync_root(home: Path) -> Path:
    return home / ".gumloop" / "sync"


def _assert_no_enrollment_side_effects(environment: SyncCliTestEnvironment) -> None:
    root = _sync_root(environment.home)
    assert not (root / "config.json").exists()
    assert not (root / "state.json").exists()
    assert environment.scheduler.installed_executable is None
    assert environment.scheduler.install_count == 0
    assert snapshot_skill_tree(agents_skills_root(environment.home)) == {}


class TestEnrollmentWithSavedCredentials:
    def test_plain_sync_enrolls_with_saved_api_key_and_installs_skill(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Missing config reuses a saved API key, writes config, installs scheduler and Skill."""
        secret = "gum_test_secret_123"
        save_credentials(Credentials(api_key=secret, user_id="user_fixture"))
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        skills_root = agents_skills_root(sync_cli_environment.home)
        expected_executable = _gumloop_executable(sync_cli_environment)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        sync_dir = _sync_root(sync_cli_environment.home)
        config_path = sync_dir / "config.json"
        state_path = sync_dir / "state.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        skill_dir = skills_root / SKILL_INSTALL_NAME
        marker = json.loads((skill_dir / MARKER_FILENAME).read_text(encoding="utf-8"))
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["background"] == {
            "enabled": True,
            "interval_seconds": 14400,
            "scheduler": "launch_agent",
        }
        assert config == {
            "organization_id": ORGANIZATION_ID,
            "scheduler_gumloop_path": str(expected_executable),
            "schema_version": 1,
        }
        assert Path(config["scheduler_gumloop_path"]).is_absolute()
        assert stat.S_IMODE(sync_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
        assert sync_cli_environment.scheduler.installed_executable == expected_executable
        assert sync_cli_environment.scheduler.install_count == 1
        assert state["status"] == "success"
        assert state["manifest_hash"] == NORMAL_MANIFEST_HASH
        assert secret not in config_path.read_text(encoding="utf-8")
        assert secret not in state_path.read_text(encoding="utf-8")
        assert expected_skill_files("bundles/normal.zip") == {
            path: (skill_dir / path).read_bytes() for path in expected_skill_files("bundles/normal.zip")
        }
        assert marker["published_version_id"] == NORMAL_PUBLISHED_VERSION_ID
        assert marker["content_hash"] == NORMAL_CONTENT_HASH

    def test_saved_oauth_access_credential_enrolls_without_login_flow(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A saved OAuth access token enrolls without browser or login prompts."""
        save_credentials(Credentials(access_token="oauth_access_token"))
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert (_sync_root(sync_cli_environment.home) / "config.json").is_file()
        assert sync_cli_environment.scheduler.install_count == 1
        assert "login" not in (result.stdout or "").lower()
        assert "browser" not in (result.stdout or "").lower()

    def test_expired_saved_oauth_refreshes_and_commits_after_validation(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A refreshed OAuth credential is persisted only when enrollment commits."""
        save_credentials(
            Credentials(
                access_token="stale_access",
                refresh_token="saved_refresh",
            )
        )
        ensure_agents_signal(sync_cli_environment.home)
        sync_cli_environment.http.post(PLAN_URL).mock(
            side_effect=[
                httpx.Response(
                    401,
                    json={
                        "error": {
                            "code": "invalid_token",
                            "message": "expired",
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json=load_json("responses/normal-plan.json"),
                    headers={"Content-Type": "application/json"},
                ),
            ]
        )
        sync_cli_environment.http.post(f"{OAUTH_BASE}/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "fresh_access",
                    "refresh_token": "fresh_refresh",
                },
            )
        )
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        persisted = load_credentials()
        assert result.exit_code == 0
        assert persisted.access_token == "fresh_access"
        assert persisted.refresh_token == "fresh_refresh"


class TestEnrollmentAuthGates:
    def test_missing_durable_auth_fails_auth_required_without_writes(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Enrollment without a saved credential fails auth_required and writes nothing."""
        ensure_agents_signal(sync_cli_environment.home)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "auth_required"
        assert "gumloop login" in envelope["error"]["message"]
        _assert_no_enrollment_side_effects(sync_cli_environment)

    @pytest.mark.parametrize(
        "environment_name",
        [
            "GUMLOOP_ACCESS_TOKEN",
            "GUMLOOP_API_KEY",
        ],
    )
    def test_temporary_auth_override_cannot_enroll(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        environment_name: str,
    ) -> None:
        """A process-only credential override cannot create persistent machine state."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setenv(environment_name, "temporary_secret")
        if environment_name == "GUMLOOP_API_KEY":
            monkeypatch.setenv("GUMLOOP_USER_ID", "temporary_user")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "auth_required"
        assert load_credentials().api_key == "key"
        _assert_no_enrollment_side_effects(sync_cli_environment)

    def test_temporary_base_url_override_cannot_enroll(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A base URL different from the saved login cannot become background configuration."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)

        result = cli_runner.invoke(
            app,
            [
                "--base-url",
                "https://temporary.example/api/v1",
                "sync",
                "--json",
            ],
        )

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "auth_required"
        _assert_no_enrollment_side_effects(sync_cli_environment)

    def test_missing_keychain_fails_before_enrollment_writes(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A machine without durable keychain support receives stateless recovery guidance."""
        ensure_agents_signal(sync_cli_environment.home)
        monkeypatch.setattr(
            "gumloop.cli.commands.sync.is_keyring_available",
            lambda: False,
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["error"]["code"] == "scheduler_unavailable"
        assert "gumloop sync --once --non-interactive" in envelope["error"]["message"]
        _assert_no_enrollment_side_effects(sync_cli_environment)

    def test_non_interactive_missing_config_fails_not_configured_without_enrolling(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """`--non-interactive` with missing config fails not_configured and does not enroll."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(app, ["sync", "--non-interactive", "--json"])

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "not_configured"
        _assert_no_enrollment_side_effects(sync_cli_environment)


class TestEnrollmentPreCommitFailures:
    def test_refreshed_oauth_rotation_persists_when_bundle_validation_fails(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Rotated OAuth tokens persist even when later enrollment validation fails."""
        save_credentials(
            Credentials(
                access_token="stale_access",
                refresh_token="saved_refresh",
            )
        )
        ensure_agents_signal(sync_cli_environment.home)
        sync_cli_environment.http.post(PLAN_URL).mock(
            side_effect=[
                httpx.Response(
                    401,
                    json={
                        "error": {
                            "code": "invalid_token",
                            "message": "expired",
                        }
                    },
                ),
                httpx.Response(
                    200,
                    json=load_json("responses/normal-plan.json"),
                    headers={"Content-Type": "application/json"},
                ),
            ]
        )
        sync_cli_environment.http.post(f"{OAUTH_BASE}/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "fresh_access",
                    "refresh_token": "fresh_refresh",
                },
            )
        )
        register_download_response(
            sync_cli_environment.http,
            "bundles/normal.zip",
            content=bundle_with_manifest_fixture(
                "bundles/normal.zip",
                "manifests/invalid-manifest-hash.json",
            ),
        )

        result = invoke_sync(cli_runner)

        persisted = load_credentials()
        assert result.exit_code == 1
        assert persisted.access_token == "fresh_access"
        assert persisted.refresh_token == "fresh_refresh"
        _assert_no_enrollment_side_effects(sync_cli_environment)

    def test_below_pro_plan_fails_before_enrollment_writes(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """A below-Pro plan rejection fails before config, state, scheduler, or target writes."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_error_response(
            sync_cli_environment.http,
            "responses/below-pro.json",
            status_code=403,
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "download_failed"
        _assert_no_enrollment_side_effects(sync_cli_environment)

    def test_invalid_bundle_fails_before_enrollment_writes(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """An invalid downloaded bundle fails before config, state, scheduler, or target writes."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
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
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "invalid_desired_state"
        _assert_no_enrollment_side_effects(sync_cli_environment)

    def test_scheduler_failure_before_commit_creates_no_enrollment_writes(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Scheduler install failure during enrollment commit leaves no durable side effects."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        sync_cli_environment.scheduler.install_error = SyncError(
            "scheduler_unavailable",
            "Background scheduling failed during install.",
        )

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "scheduler_unavailable"
        _assert_no_enrollment_side_effects(sync_cli_environment)


class TestEnrollmentPostCommitOutcomes:
    def test_first_target_failure_after_enrollment_keeps_config_and_writes_partial_state(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A first reconciliation target failure keeps config and scheduler and writes partial state."""
        save_configured_credentials()
        agents_root = ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        expected_executable = _gumloop_executable(sync_cli_environment)

        def fail_agents_target(**kwargs: Any):
            target = kwargs["target"]
            if target.skills_root == agents_root:
                raise PermissionError("injected target permissions failure")
            return prepare_target_reconciliation(**kwargs)

        monkeypatch.setattr("gumloop.sync.run.prepare_target_reconciliation", fail_agents_target)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        sync_dir = _sync_root(sync_cli_environment.home)
        config = json.loads((sync_dir / "config.json").read_text(encoding="utf-8"))
        state = json.loads((sync_dir / "state.json").read_text(encoding="utf-8"))
        assert result.exit_code == 1
        assert envelope["status"] == "partial"
        assert config["organization_id"] == ORGANIZATION_ID
        assert config["scheduler_gumloop_path"] == str(expected_executable)
        assert sync_cli_environment.scheduler.installed_executable == expected_executable
        assert state["status"] == "partial"
        assert not (agents_root / SKILL_INSTALL_NAME).exists()

    def test_no_detected_targets_still_completes_enrollment(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Enrollment with no detected targets writes config, scheduler, and state without Skills."""
        save_configured_credentials()
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        expected_executable = _gumloop_executable(sync_cli_environment)

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        sync_dir = _sync_root(sync_cli_environment.home)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert (sync_dir / "config.json").is_file()
        assert (sync_dir / "state.json").is_file()
        assert envelope["result"]["manifest_hash"] == NORMAL_MANIFEST_HASH
        assert sync_cli_environment.scheduler.installed_executable == expected_executable
        assert snapshot_skill_tree(agents_skills_root(sync_cli_environment.home)) == {}


class TestDepartureCleanup:
    def test_departure_stops_scheduler_and_requires_reenrollment(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Successful departure removes persistent enrollment but preserves login and cleanup state."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        write_sync_state(
            sync_cli_environment.home,
            manifest_hash=NORMAL_MANIFEST_HASH,
        )
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

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        sync_dir = _sync_root(sync_cli_environment.home)
        state = json.loads((sync_dir / "state.json").read_text(encoding="utf-8"))
        assert result.exit_code == 0
        assert envelope["result"]["departure_cleanup"] is True
        assert envelope["result"]["background"]["enabled"] is False
        assert not (sync_dir / "config.json").exists()
        assert state["status"] == "departure_cleanup"
        assert sync_cli_environment.scheduler.installed_executable is None
        assert sync_cli_environment.scheduler.remove_count == 1
        assert load_credentials().api_key == "key"


class TestEnrollmentIdempotencyAndRepair:
    def test_non_interactive_configured_sync_reports_missing_scheduler(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Automation reports the actual scheduler state without repairing it."""
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        register_plan_response(
            sync_cli_environment.http,
            "responses/normal-empty-plan.json",
        )

        result = cli_runner.invoke(app, ["sync", "--non-interactive", "--json"])

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["background"] == {
            "enabled": False,
            "interval_seconds": 14400,
            "scheduler": "launch_agent",
        }
        assert sync_cli_environment.scheduler.install_count == 0

    def test_scheduled_sync_after_manual_enrollment_reaches_equivalent_state(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Configured non-interactive sync uses the manual enrollment reconciliation state."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")
        first = invoke_sync(cli_runner)
        assert first.exit_code == 0
        before = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(app, ["sync", "--non-interactive", "--json"])

        envelope = parse_json_envelope(result)
        after = snapshot_skill_tree(agents_skills_root(sync_cli_environment.home))
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["background"]["enabled"] is True
        assert envelope["result"]["counts"]["unchanged"] == 1
        assert after == before

    def test_rerunning_repairs_missing_scheduler_after_enrollment(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Clearing fake scheduler state and re-running plain sync reinstalls the scheduler."""
        save_configured_credentials()
        expected_executable = _gumloop_executable(sync_cli_environment)
        sync_dir = _sync_root(sync_cli_environment.home)
        sync_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (sync_dir / "config.json").write_text(
            json.dumps(
                {
                    "organization_id": ORGANIZATION_ID,
                    "scheduler_gumloop_path": str(expected_executable),
                    "schema_version": 1,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_sync_state(sync_cli_environment.home, manifest_hash=NORMAL_MANIFEST_HASH)
        install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        sync_cli_environment.scheduler.installed_executable = None
        sync_cli_environment.scheduler.install_count = 0
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert sync_cli_environment.scheduler.installed_executable == expected_executable
        assert sync_cli_environment.scheduler.install_count == 1
        assert sync_cli_environment.scheduler.is_current(expected_executable)


class TestEnrollmentJsonContract:
    def test_human_enrollment_prints_organization_targets_and_background(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Foreground enrollment names the organization, resolved target, and scheduler state."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(app, ["sync"], terminal_width=1000)

        assert result.exit_code == 0
        assert "Enrolled in Fixture Organization" in result.stdout
        assert "Coding agents" in result.stdout
        assert "Skills path" in result.stdout
        assert "agent-skills" in result.stdout
        assert "Background sync enabled (every 4 hours)" in result.stdout

    def test_enrollment_json_is_one_progress_free_deterministic_object(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        """Enrollment JSON emits exactly one progress-free object with background status."""
        save_configured_credentials()
        ensure_agents_signal(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = json.loads(result.stdout)
        assert result.exit_code == 0
        assert result.stdout.count("\n") == 1
        assert "Resolving managed Skills" not in result.stdout
        assert envelope["command"] == "sync"
        assert envelope["schema_version"] == 1
        assert envelope["status"] == "ok"
        assert envelope["error"] is None
        assert envelope["result"]["background"] == {
            "enabled": True,
            "interval_seconds": 14400,
            "scheduler": "launch_agent",
        }
