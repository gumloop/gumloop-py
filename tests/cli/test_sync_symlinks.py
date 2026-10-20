"""Unmanaged skill links coexist with managed sync without granting mutation authority."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gumloop.cli.main import app
from tests.cli.sync_scenario_helpers import MARKER_FILENAME
from tests.cli.sync_scenario_helpers import NEWER_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NEWER_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import NORMAL_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NORMAL_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import NORMAL_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import SKILL_INSTALL_NAME
from tests.cli.sync_scenario_helpers import agents_skills_root
from tests.cli.sync_scenario_helpers import install_skill_from_bundle
from tests.cli.sync_scenario_helpers import invoke_sync
from tests.cli.sync_scenario_helpers import parse_json_envelope
from tests.cli.sync_scenario_helpers import register_download_response
from tests.cli.sync_scenario_helpers import register_plan_response
from tests.cli.sync_scenario_helpers import save_configured_credentials
from tests.cli.sync_scenario_helpers import write_sync_config
from tests.cli.sync_scenario_helpers import write_sync_state
from tests.cli.sync_test_fakes import SyncCliTestEnvironment


def _personal_link(home: Path, name: str = "personal-skill", kind: str = "directory") -> Path:
    root = agents_skills_root(home)
    root.mkdir(parents=True, exist_ok=True)
    link = root / name
    outside = home / "personal-source"
    if kind == "directory":
        outside.mkdir()
        (outside / "SKILL.md").write_text("personal content", encoding="utf-8")
        # Even content that cannot be safely hashed must not be inspected.
        (outside / "loop").symlink_to(outside, target_is_directory=True)
    elif kind == "file":
        outside.write_text("personal content", encoding="utf-8")
    elif kind == "loop":
        outside = link
    link.symlink_to(outside)
    return link


class TestUnmanagedSymlinks:
    @pytest.mark.parametrize("kind", ["directory", "file", "dangling", "loop"])
    def test_install_preserves_unrelated_link_and_reports_warning(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
        kind: str,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        link = _personal_link(sync_cli_environment.home, kind=kind)
        destination = link.readlink()
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["status"] == "ok"
        assert envelope["result"]["convergence"] == "full"
        assert envelope["result"]["counts"]["installed"] == 1
        assert envelope["result"]["counts"]["skipped"] == 1
        skipped = next(change for change in envelope["result"]["changes"] if change["action"] == "skipped")
        assert skipped["warning"] == f"Skipping unmanaged symlink; link and destination were preserved: {link}"
        assert skipped["error"] is None
        assert link.is_symlink()
        assert link.readlink() == destination
        assert (link.parent / SKILL_INSTALL_NAME / MARKER_FILENAME).is_file()
        if kind == "directory":
            assert (destination / "SKILL.md").read_text(encoding="utf-8") == "personal content"
            assert not (destination / MARKER_FILENAME).exists()

    def test_links_to_same_external_source_are_not_treated_as_managed_shared_links(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        link = _personal_link(sync_cli_environment.home)
        claude_root = sync_cli_environment.home / ".claude" / "skills"
        claude_root.mkdir(parents=True)
        alias = claude_root / link.name
        alias.symlink_to(link.readlink())
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["installed"] == 2
        assert envelope["result"]["counts"]["skipped"] == 2
        assert link.is_symlink()
        assert alias.is_symlink()
        assert not (link.readlink() / MARKER_FILENAME).exists()

    def test_updates_managed_skill_beside_personal_link(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        link = _personal_link(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/newer-than-plan.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["updated"] == 1
        marker = (installed / MARKER_FILENAME).read_text(encoding="utf-8")
        assert NEWER_PUBLISHED_VERSION_ID in marker
        assert NEWER_CONTENT_HASH in marker
        assert link.is_symlink()

    def test_matching_manifest_keeps_warning_without_downloading(
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
        link = _personal_link(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        download = register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["unchanged"] == 1
        assert envelope["result"]["counts"]["skipped"] == 1
        assert not download.called
        assert link.is_symlink()

    def test_warning_is_visible_without_verbose_output(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        link = _personal_link(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = cli_runner.invoke(app, ["sync", "--non-interactive"])

        assert result.exit_code == 0
        assert "warning: Skipping unmanaged symlink" in result.stderr
        assert "personal-skill" in result.stderr
        assert link.is_symlink()

    def test_managed_name_collision_fails_only_that_skill_and_removes_obsolete_skill(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        # This valid owned entry is no longer in the desired manifest.
        obsolete = installed.with_name("obsolete-skill")
        installed.rename(obsolete)
        marker = obsolete / MARKER_FILENAME
        marker.write_text(
            marker.read_text(encoding="utf-8").replace(SKILL_INSTALL_NAME, obsolete.name), encoding="utf-8"
        )
        link = _personal_link(sync_cli_environment.home, name=SKILL_INSTALL_NAME)
        destination = link.readlink()
        register_plan_response(sync_cli_environment.http, "responses/normal-plan.json")
        register_download_response(sync_cli_environment.http, "bundles/normal.zip")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 1
        assert envelope["status"] == "partial"
        assert envelope["result"]["counts"]["failed"] == 1
        assert envelope["result"]["counts"]["removed"] == 1
        assert envelope["result"]["physical_targets"][0]["error"]["code"] == "target_failed"
        assert not obsolete.exists()
        assert link.is_symlink()
        assert link.readlink() == destination
        assert (destination / "SKILL.md").read_text(encoding="utf-8") == "personal content"
        assert not (destination / MARKER_FILENAME).exists()

    def test_empty_plan_removes_owned_skill_but_preserves_personal_link(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        cli_runner: CliRunner,
    ) -> None:
        save_configured_credentials()
        write_sync_config(sync_cli_environment.home)
        installed = install_skill_from_bundle(
            sync_cli_environment.home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        link = _personal_link(sync_cli_environment.home)
        register_plan_response(sync_cli_environment.http, "responses/normal-empty-plan.json")

        result = invoke_sync(cli_runner)

        envelope = parse_json_envelope(result)
        assert result.exit_code == 0
        assert envelope["result"]["counts"]["removed"] == 1
        assert envelope["result"]["counts"]["skipped"] == 1
        assert not installed.exists()
        assert link.is_symlink()
