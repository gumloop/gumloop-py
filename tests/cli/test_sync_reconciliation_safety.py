"""Failure-injection tests for local Skill replacement safety."""

from __future__ import annotations

import shutil
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.bundle import StagedSyncBundle
from gumloop.sync.bundle import stage_sync_bundle
from gumloop.sync.markers import build_marker
from gumloop.sync.markers import write_marker_atomic
from gumloop.sync.reconcile import prepare_target_reconciliation
from gumloop.sync.target_files import Mutation
from gumloop.sync.target_files import PreparedTargetReconciliation
from gumloop.sync.targets import PhysicalTarget
from gumloop.types import CliSyncLimits
from tests.cli.sync_test_fakes import SyncCliTestEnvironment
from tests.skill_sync_fixtures import FIXTURE_ROOT
from tests.skill_sync_fixtures import load_json

pytestmark = pytest.mark.implementation

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CONTENT_TYPE = "application/zip"


def _fail_new_directory_swap(original_replace: object):
    def fail(source: Path, target: Path) -> Path:
        if source.parent.name == "prepared" and source.name.startswith("skill-"):
            raise OSError("injected replacement interruption")
        return original_replace(source, target)  # type: ignore[operator]

    return fail


def _interrupt_replacement(_prepared: Path, _destination: Path) -> None:
    raise OSError("injected first replacement failure")


def _stage(relative_bundle: str, staging_parent: Path) -> StagedSyncBundle:
    staging_parent.mkdir(parents=True, exist_ok=True)
    download = SyncBundleDownload(
        content=(FIXTURE_ROOT / relative_bundle).read_bytes(),
        content_type=CONTENT_TYPE,
    )
    return stage_sync_bundle(
        download,
        expected_organization_id="org_fixture",
        plan_limits=CliSyncLimits.model_validate(load_json("responses/normal-plan.json")["limits"]),
        staging_parent=staging_parent,
    )


def _arrange_local_edit_update(
    environment: SyncCliTestEnvironment,
    staging_parent: Path,
) -> tuple[PreparedTargetReconciliation, Path, Path]:
    normal = _stage("bundles/normal.zip", staging_parent)
    newer = _stage("bundles/newer-than-plan.zip", staging_parent)
    skills_root = environment.create_target("agent-skills")
    destination = skills_root / "acme-api-conventions"
    shutil.copytree(normal.skill_roots["acme-api-conventions"], destination)
    normal_skill = normal.manifest.skills[0]
    write_marker_atomic(
        destination,
        build_marker(
            organization_id="org_fixture",
            skill_id=normal_skill.skill_id,
            name=normal_skill.install_name,
            published_version_id=normal_skill.published_version_id,
            content_hash=normal_skill.content_hash,
            installed_at=NOW,
        ),
    )
    (destination / "SKILL.md").write_text("local edit", encoding="utf-8")
    backup_base = environment.home / ".gumloop" / "sync" / "backups"
    prepared = prepare_target_reconciliation(
        target=PhysicalTarget(
            skills_root=skills_root,
            logical_targets=("agent_skills",),
        ),
        organization_id="org_fixture",
        bundle=newer,
        backup_base=backup_base,
        installed_at=NOW,
    )
    return prepared, destination, backup_base


class TestReplacementRollback:
    def test_backup_failure_preserves_complete_previous_target(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failed backup copy changes neither the installed Skill nor its previous backup."""
        prepared, destination, _backup_base = _arrange_local_edit_update(
            sync_cli_environment,
            tmp_path / "staging",
        )
        original_skill = (destination / "SKILL.md").read_bytes()

        def fail_copy(_source: Path, _destination: Path) -> None:
            raise OSError("injected backup failure")

        monkeypatch.setattr("gumloop.sync.target_files._copy_path", fail_copy)
        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()

        assert outcome.error is not None
        assert "Could not back up" in outcome.error
        assert (destination / "SKILL.md").read_bytes() == original_skill

    def test_interrupted_atomic_swap_restores_complete_previous_skill(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A replacement failure after displacement restores the complete old directory."""
        prepared, destination, _backup_base = _arrange_local_edit_update(
            sync_cli_environment,
            tmp_path / "staging",
        )
        original_replace = Path.replace
        monkeypatch.setattr(Path, "replace", _fail_new_directory_swap(original_replace))
        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()

        assert outcome.error == "injected replacement interruption"
        assert (destination / "SKILL.md").read_text(encoding="utf-8") == "local edit"
        assert load_json("manifests/normal-bundle.json")["skills"][0]["published_version_id"] in (
            destination / ".gumloop.json"
        ).read_text(encoding="utf-8")

    def test_failed_earlier_mutation_does_not_roll_later_skill_backup(
        self,
        sync_cli_environment: SyncCliTestEnvironment,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A skill not reached by apply keeps its previous rolling backup."""
        skills_root = sync_cli_environment.create_target("agent-skills")
        first = skills_root / "first"
        second = skills_root / "second"
        first.mkdir()
        second.mkdir()
        (first / "SKILL.md").write_text("first old", encoding="utf-8")
        (second / "SKILL.md").write_text("second old", encoding="utf-8")
        first_prepared = skills_root / ".gumloop-tmp-first"
        second_prepared = skills_root / ".gumloop-tmp-second"
        first_prepared.mkdir()
        second_prepared.mkdir()
        (first_prepared / "SKILL.md").write_text("first new", encoding="utf-8")
        (second_prepared / "SKILL.md").write_text("second new", encoding="utf-8")
        backup_root = sync_cli_environment.home / ".gumloop" / "sync" / "backups"
        first_backup = backup_root / "target" / "first"
        second_backup = backup_root / "target" / "second"
        second_backup.mkdir(parents=True)
        (second_backup / "SKILL.md").write_text("previous second backup", encoding="utf-8")
        prepared = PreparedTargetReconciliation(
            target=PhysicalTarget(skills_root, ("agent_skills",)),
            mutations=[
                Mutation(
                    kind="replace",
                    destination=first,
                    skill=None,
                    marker=None,
                    action="updated",
                    prepared_path=first_prepared,
                    backup_path=first_backup,
                    backup_required=True,
                ),
                Mutation(
                    kind="replace",
                    destination=second,
                    skill=None,
                    marker=None,
                    action="updated",
                    prepared_path=second_prepared,
                    backup_path=second_backup,
                    backup_required=True,
                ),
            ],
            unchanged=[],
        )
        monkeypatch.setattr("gumloop.sync.target_files._atomic_replace", _interrupt_replacement)

        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()

        assert outcome.error == "injected first replacement failure"
        assert (first_backup / "SKILL.md").read_text(encoding="utf-8") == "first old"
        assert (second_backup / "SKILL.md").read_text(encoding="utf-8") == "previous second backup"
        assert (second / "SKILL.md").read_text(encoding="utf-8") == "second old"
