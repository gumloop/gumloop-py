"""Behavioral tests for Skill Sync bundle validation and staging."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.bundle import stage_sync_bundle
from gumloop.sync.bundle import write_bytes
from gumloop.sync.errors import SyncError
from gumloop.types import CliSyncBundleManifest
from gumloop.types import CliSyncLimits
from tests.skill_sync_fixtures import FIXTURE_ROOT
from tests.skill_sync_fixtures import load_catalog
from tests.skill_sync_fixtures import load_json

_BUNDLE_CONTENT_TYPE = "application/zip"

_NORMAL_PLAN = load_json("responses/normal-plan.json")
_EXPECTED_ORGANIZATION_ID = _NORMAL_PLAN["organization"]["organization_id"]
_PLAN_LIMITS = CliSyncLimits.model_validate(_NORMAL_PLAN["limits"])

_BUNDLE_CASES = (
    pytest.param(
        "bundles/normal.zip",
        "manifests/normal-bundle.json",
        "9e13c221a12284faed9dd0010ee3ae36840c4599ed88726dbe964bbe32cd67e6",
        id="normal",
    ),
    pytest.param(
        "bundles/newer-than-plan.zip",
        "manifests/newer-than-plan.json",
        "28fd26b3be2adeca75dee82be1e13c3cb282fab8fb277c11172408ae57952b1f",
        id="newer-than-plan",
    ),
)
_ADVERSARIAL_ARCHIVE_CASES = tuple(
    pytest.param(entry["path"], id=entry.get("case", Path(entry["path"]).stem))
    for entry in load_catalog()["archives"]
    if entry.get("expected") == "invalid_sync_bundle" and entry.get("kind") == "zip"
)
_INVALID_MANIFEST_CASES = tuple(
    pytest.param(entry["path"], id=Path(entry["path"]).stem)
    for entry in load_catalog()["manifests"]
    if entry.get("expected") == "invalid_sync_bundle"
)


def _fixture_bytes(relative_path: str) -> bytes:
    return (FIXTURE_ROOT / relative_path).read_bytes()


def _bundle_download(
    relative_path: str,
    *,
    content: bytes | None = None,
) -> SyncBundleDownload:
    archive_bytes = content if content is not None else _fixture_bytes(relative_path)
    return SyncBundleDownload(
        content=archive_bytes,
        content_type=_BUNDLE_CONTENT_TYPE,
    )


def _build_bundle_zip(manifest: dict[str, object]) -> bytes:
    with zipfile.ZipFile(FIXTURE_ROOT / "bundles/normal.zip") as source:
        skill_entries = {name: source.read(name) for name in source.namelist() if name != "gumloop-sync-manifest.json"}
    destination = io.BytesIO()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "gumloop-sync-manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
        for path in sorted(skill_entries):
            archive.writestr(path, skill_entries[path])
    return destination.getvalue()


def _assert_no_staging_children(staging_parent: Path) -> None:
    assert list(staging_parent.iterdir()) == []


def _failing_writer(original_write: object):
    calls = {"count": 0}

    def write(path: Path, content: bytes) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected staging write failure")
        original_write(path, content)  # type: ignore[operator]

    return write


class TestStageValidBundle:
    @pytest.mark.parametrize(
        ("bundle_path", "manifest_path", "expected_manifest_hash"),
        _BUNDLE_CASES,
    )
    def test_stage_sync_bundle_stages_valid_shared_bundles(
        self,
        tmp_path: Path,
        bundle_path: str,
        manifest_path: str,
        expected_manifest_hash: str,
    ) -> None:
        """Valid shared bundles stage their manifest and declared skill files."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = _bundle_download(bundle_path)
        expected_manifest = load_json(manifest_path)
        with zipfile.ZipFile(FIXTURE_ROOT / bundle_path) as archive:
            expected_manifest_bytes = archive.read("gumloop-sync-manifest.json")

        staged = stage_sync_bundle(
            download,
            expected_organization_id=_EXPECTED_ORGANIZATION_ID,
            plan_limits=_PLAN_LIMITS,
            staging_parent=staging_parent,
        )

        assert staged.manifest == CliSyncBundleManifest.model_validate(expected_manifest)
        assert staged.manifest.manifest.hash == expected_manifest_hash
        assert (staged.root / "gumloop-sync-manifest.json").read_bytes() == expected_manifest_bytes
        assert (staged.skill_roots["acme-api-conventions"] / "SKILL.md").is_file()
        assert (staged.skill_roots["acme-api-conventions"] / "examples.md").is_file()
        assert list(staging_parent.iterdir()) == [staged.root]

    def test_stage_sync_bundle_accepts_bundle_newer_than_plan_manifest(
        self,
        tmp_path: Path,
    ) -> None:
        """A bundle whose manifest hash differs from the preceding plan still stages successfully."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = _bundle_download("bundles/newer-than-plan.zip")

        staged = stage_sync_bundle(
            download,
            expected_organization_id=_EXPECTED_ORGANIZATION_ID,
            plan_limits=_PLAN_LIMITS,
            staging_parent=staging_parent,
        )

        assert staged.manifest.manifest.hash != _NORMAL_PLAN["manifest"]["hash"]
        assert staged.manifest.skills[0].published_version_id == "version_fixture_2"


class TestStageRejectsInvalidBundle:
    @pytest.mark.parametrize("archive_path", _ADVERSARIAL_ARCHIVE_CASES)
    def test_stage_sync_bundle_rejects_adversarial_archive_catalog(
        self,
        tmp_path: Path,
        archive_path: str,
    ) -> None:
        """Each shared adversarial archive is rejected without leaving a staging child."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = _bundle_download(archive_path)

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "invalid_desired_state"
        _assert_no_staging_children(staging_parent)

    @pytest.mark.parametrize("manifest_path", _INVALID_MANIFEST_CASES)
    def test_stage_sync_bundle_rejects_invalid_manifest_catalog(
        self,
        tmp_path: Path,
        manifest_path: str,
    ) -> None:
        """Each shared invalid manifest fixture is rejected when embedded in a bundle."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        manifest = load_json(manifest_path)
        archive_bytes = _build_bundle_zip(manifest)
        download = _bundle_download(
            "bundles/normal.zip",
            content=archive_bytes,
        )

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "invalid_desired_state"
        _assert_no_staging_children(staging_parent)

    def test_stage_sync_bundle_rejects_organization_mismatch(self, tmp_path: Path) -> None:
        """A bundle for a different organization is rejected."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = _bundle_download("bundles/normal.zip")

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id="org_other",
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "invalid_desired_state"
        _assert_no_staging_children(staging_parent)

    def test_stage_sync_bundle_rejects_corrupt_zip(self, tmp_path: Path) -> None:
        """Corrupt transfer bytes are rejected as a failed download."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = SyncBundleDownload(
            content=b"not-a-valid-zip",
            content_type=_BUNDLE_CONTENT_TYPE,
        )

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "download_failed"
        _assert_no_staging_children(staging_parent)

    def test_stage_sync_bundle_rejects_missing_declared_skill_root(self, tmp_path: Path) -> None:
        """A bundle that omits files for a declared install name is rejected."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        manifest = load_json("manifests/normal-bundle.json")
        destination = io.BytesIO()
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "gumloop-sync-manifest.json",
                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
            )
        download = _bundle_download(
            "bundles/normal.zip",
            content=destination.getvalue(),
        )

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "invalid_desired_state"
        _assert_no_staging_children(staging_parent)

    def test_stage_sync_bundle_rejects_extra_undeclared_skill_root(self, tmp_path: Path) -> None:
        """A bundle with files under an undeclared install name is rejected."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        archive_bytes = _build_bundle_zip(load_json("manifests/normal-bundle.json"))
        destination = io.BytesIO(archive_bytes)
        with zipfile.ZipFile(destination, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("extra-skill/notes.md", b"unexpected")
        download = _bundle_download(
            "bundles/normal.zip",
            content=destination.getvalue(),
        )

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "invalid_desired_state"
        _assert_no_staging_children(staging_parent)


class TestStageSafetyInvariants:
    @pytest.mark.implementation
    def test_stage_sync_bundle_rejects_oversized_member_before_expansion(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Declared member sizes are bounded before zipfile expands their content."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = _bundle_download("bundles/normal.zip")
        oversized_path = "acme-api-conventions/SKILL.md"
        original_infolist = zipfile.ZipFile.infolist
        original_read = zipfile.ZipFile.read

        def oversized_infolist(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
            entries = original_infolist(archive)
            for entry in entries:
                if entry.filename == oversized_path:
                    entry.file_size = _PLAN_LIMITS.bytes_per_file + 1
            return entries

        def fail_if_oversized_member_is_read(
            archive: zipfile.ZipFile,
            name: str | zipfile.ZipInfo,
            pwd: bytes | None = None,
        ) -> bytes:
            if isinstance(name, zipfile.ZipInfo) and name.filename == oversized_path:
                raise AssertionError("oversized member was expanded")
            return original_read(archive, name, pwd)

        monkeypatch.setattr(zipfile.ZipFile, "infolist", oversized_infolist)
        monkeypatch.setattr(zipfile.ZipFile, "read", fail_if_oversized_member_is_read)

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "invalid_desired_state"
        _assert_no_staging_children(staging_parent)

    @pytest.mark.implementation
    def test_stage_sync_bundle_cleans_up_after_injected_write_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A staged write failure removes only the newly created staging child."""
        staging_parent = tmp_path / "staging"
        staging_parent.mkdir()
        download = _bundle_download("bundles/normal.zip")
        monkeypatch.setattr("gumloop.sync.bundle.write_bytes", _failing_writer(write_bytes))

        with pytest.raises(SyncError) as raised:
            stage_sync_bundle(
                download,
                expected_organization_id=_EXPECTED_ORGANIZATION_ID,
                plan_limits=_PLAN_LIMITS,
                staging_parent=staging_parent,
            )

        assert raised.value.code == "download_failed"
        _assert_no_staging_children(staging_parent)
