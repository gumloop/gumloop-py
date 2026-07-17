"""Behavioral tests for installed-state inspection and stale-work recovery."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from gumloop.resources.sync import SYNC_BUNDLE_CONTENT_TYPE
from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.bundle import StagedSyncBundle
from gumloop.sync.bundle import stage_sync_bundle
from gumloop.sync.errors import SyncError
from gumloop.sync.installed import target_matches_manifest
from gumloop.sync.markers import is_safe_install_name
from gumloop.sync.reconcile import prepare_target_reconciliation
from gumloop.sync.targets import PhysicalTarget
from gumloop.sync.wire import SYNC_WORKSPACE_DIRNAME
from gumloop.types import CliSyncLimits
from tests.cli.sync_scenario_helpers import NORMAL_CONTENT_HASH
from tests.cli.sync_scenario_helpers import NORMAL_MANIFEST_HASH
from tests.cli.sync_scenario_helpers import NORMAL_PUBLISHED_VERSION_ID
from tests.cli.sync_scenario_helpers import SKILL_INSTALL_NAME
from tests.cli.sync_scenario_helpers import agents_skills_root
from tests.cli.sync_scenario_helpers import claim_sync_workspace
from tests.cli.sync_scenario_helpers import install_skill_from_bundle
from tests.skill_sync_fixtures import FIXTURE_ROOT
from tests.skill_sync_fixtures import load_json

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _stage_normal_bundle(staging_parent: Path) -> StagedSyncBundle:
    staging_parent.mkdir(parents=True, exist_ok=True)
    content = (FIXTURE_ROOT / "bundles/normal.zip").read_bytes()
    return stage_sync_bundle(
        SyncBundleDownload(
            content=content,
            content_type=SYNC_BUNDLE_CONTENT_TYPE,
        ),
        expected_organization_id="org_fixture",
        plan_limits=CliSyncLimits.model_validate(load_json("responses/normal-plan.json")["limits"]),
        staging_parent=staging_parent,
    )


class TestInstallNameSafety:
    def test_sync_workspace_name_is_not_a_safe_install_name(self) -> None:
        """A downloaded Skill cannot claim the CLI's exact recovery workspace."""
        assert is_safe_install_name(SYNC_WORKSPACE_DIRNAME) is False


class TestManifestMatching:
    def test_matching_cross_target_symlink_is_treated_as_one_physical_install(
        self,
        temporary_home: Path,
    ) -> None:
        """A same-name symlink into another detected root is safely deduplicated."""
        installed = install_skill_from_bundle(
            temporary_home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        linked_root = temporary_home / ".claude" / "skills"
        linked_root.mkdir(parents=True)
        (linked_root / SKILL_INSTALL_NAME).symlink_to(installed, target_is_directory=True)
        actual_root = agents_skills_root(temporary_home)

        matches = target_matches_manifest(
            target=PhysicalTarget(linked_root, ("claude_code",)),
            organization_id="org_fixture",
            manifest_hash=NORMAL_MANIFEST_HASH,
            skill_count=1,
            other_target_roots=(actual_root,),
        )

        assert matches is True

    def test_manifest_match_does_not_inspect_unmarked_unrelated_content(
        self,
        temporary_home: Path,
    ) -> None:
        """Manifest inspection hashes owned Skills without reading unrelated unmarked directories."""
        install_skill_from_bundle(
            temporary_home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        skills_root = agents_skills_root(temporary_home)
        unrelated = skills_root / "personal-skill"
        unrelated.mkdir()
        outside = temporary_home / "outside"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("safe", encoding="utf-8")
        (unrelated / "linked-content").symlink_to(outside, target_is_directory=True)

        matches = target_matches_manifest(
            target=PhysicalTarget(skills_root, ("agent_skills",)),
            organization_id="org_fixture",
            manifest_hash=NORMAL_MANIFEST_HASH,
            skill_count=1,
        )

        assert matches is True
        assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "safe"

    def test_unrelated_skill_symlink_fails_without_following_it(
        self,
        temporary_home: Path,
    ) -> None:
        """A symlink outside another detected target fails without changing its target."""
        skills_root = temporary_home / ".agents" / "skills"
        skills_root.mkdir(parents=True)
        outside = temporary_home / "outside"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("safe", encoding="utf-8")
        (skills_root / "unsafe").symlink_to(outside, target_is_directory=True)

        with pytest.raises(SyncError, match="symlinked Skill entry"):
            target_matches_manifest(
                target=PhysicalTarget(skills_root, ("agent_skills",)),
                organization_id="org_fixture",
                manifest_hash=NORMAL_MANIFEST_HASH,
                skill_count=1,
            )

        assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "safe"


class TestStaleWorkRecovery:
    def test_next_reconciliation_restores_displaced_old_directory(
        self,
        temporary_home: Path,
        tmp_path: Path,
    ) -> None:
        """A crash after displacement is recovered before reconciliation continues."""
        installed = install_skill_from_bundle(
            temporary_home,
            "bundles/normal.zip",
            published_version_id=NORMAL_PUBLISHED_VERSION_ID,
            content_hash=NORMAL_CONTENT_HASH,
        )
        workspace = claim_sync_workspace(installed.parent)
        stale = workspace / "displaced" / installed.name
        installed.replace(stale)
        staged = _stage_normal_bundle(tmp_path / "staging")

        prepared = prepare_target_reconciliation(
            target=PhysicalTarget(installed.parent, ("agent_skills",)),
            organization_id="org_fixture",
            bundle=staged,
            backup_base=None,
            installed_at=NOW,
        )
        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()

        assert outcome.error is None
        assert outcome.changes[0].action == "unchanged"
        assert installed.is_dir()
        assert not stale.exists()
        assert not workspace.exists()

    def test_next_reconciliation_removes_abandoned_preparation(
        self,
        temporary_home: Path,
        tmp_path: Path,
    ) -> None:
        """An unfinished preparation directory is removed before a new plan is applied."""
        skills_root = temporary_home / ".agents" / "skills"
        skills_root.mkdir(parents=True)
        workspace = claim_sync_workspace(skills_root)
        stale = workspace / "prepared" / "skill-abandoned"
        stale.mkdir(parents=True)
        (stale / "partial.txt").write_text("partial", encoding="utf-8")
        staged = _stage_normal_bundle(tmp_path / "staging")

        prepared = prepare_target_reconciliation(
            target=PhysicalTarget(skills_root, ("agent_skills",)),
            organization_id="org_fixture",
            bundle=staged,
            backup_base=None,
            installed_at=NOW,
        )
        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()

        assert outcome.error is None
        assert not stale.exists()
        assert not workspace.exists()

    def test_legacy_temporary_prefix_directory_is_preserved(
        self,
        temporary_home: Path,
        tmp_path: Path,
    ) -> None:
        """A similarly named unmarked directory is not treated as Gumloop recovery work."""
        skills_root = temporary_home / ".agents" / "skills"
        user_skill = skills_root / ".gumloop-tmp-user-skill"
        user_skill.mkdir(parents=True)
        user_file = user_skill / "SKILL.md"
        user_file.write_text("user-owned content", encoding="utf-8")
        staged = _stage_normal_bundle(tmp_path / "staging")

        prepared = prepare_target_reconciliation(
            target=PhysicalTarget(skills_root, ("agent_skills",)),
            organization_id="org_fixture",
            bundle=staged,
            backup_base=None,
            installed_at=NOW,
        )
        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()

        assert outcome.error is None
        assert user_file.read_text(encoding="utf-8") == "user-owned content"

    def test_unclaimed_sync_workspace_is_preserved_and_fails_target(
        self,
        temporary_home: Path,
        tmp_path: Path,
    ) -> None:
        """An existing reserved directory without Gumloop's sentinel grants no cleanup authority."""
        skills_root = temporary_home / ".agents" / "skills"
        workspace = skills_root / SYNC_WORKSPACE_DIRNAME
        workspace.mkdir(parents=True)
        user_file = workspace / "notes.txt"
        user_file.write_text("not Gumloop work", encoding="utf-8")
        staged = _stage_normal_bundle(tmp_path / "staging")

        with pytest.raises(SyncError, match="Refusing to claim"):
            prepare_target_reconciliation(
                target=PhysicalTarget(skills_root, ("agent_skills",)),
                organization_id="org_fixture",
                bundle=staged,
                backup_base=None,
                installed_at=NOW,
            )

        assert user_file.read_text(encoding="utf-8") == "not Gumloop work"
