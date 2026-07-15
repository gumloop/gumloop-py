"""Shared builders for CLI sync scenario tests."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import httpx
import respx
from click.testing import Result

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from gumloop.resources.sync import SYNC_BUNDLE_CONTENT_TYPE
from gumloop.resources.sync import SyncBundleDownload
from gumloop.sync.bundle import stage_sync_bundle
from gumloop.sync.reconcile import prepare_target_reconciliation
from gumloop.sync.targets import PhysicalTarget
from gumloop.sync.wire import SYNC_WORKSPACE_DIRNAME
from gumloop.types import CliSyncLimits
from tests.sdk.helpers import API_BASE
from tests.skill_sync_fixtures import FIXTURE_ROOT
from tests.skill_sync_fixtures import load_json

PLAN_URL = f"{API_BASE}/skills/sync/plan"
DOWNLOAD_URL = f"{API_BASE}/skills/sync/download"

ORGANIZATION_ID = "org_fixture"
SKILL_INSTALL_NAME = "acme-api-conventions"
NORMAL_PUBLISHED_VERSION_ID = "version_fixture_1"
NEWER_PUBLISHED_VERSION_ID = "version_fixture_2"
NORMAL_CONTENT_HASH = "78ebce909b2a71a5bd38f75f0389e83346f7f6fc3aec125ad1029e34afdfb204"
NEWER_CONTENT_HASH = "e2a424776a2fde99b4ca96a1c639d47014dffb3c9a2d706fbb0b27d9fb6bba3e"
NORMAL_MANIFEST_HASH = "9e13c221a12284faed9dd0010ee3ae36840c4599ed88726dbe964bbe32cd67e6"
NEWER_MANIFEST_HASH = "28fd26b3be2adeca75dee82be1e13c3cb282fab8fb277c11172408ae57952b1f"
EMPTY_MANIFEST_HASH = "4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a"
FIXTURE_INSTALLED_AT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
MARKER_FILENAME = ".gumloop.json"


@dataclass(frozen=True)
class SkillSnapshot:
    paths: dict[str, bytes]
    marker: dict[str, Any] | None


def agents_skills_root(home: Path) -> Path:
    return home / ".agents" / "skills"


def ensure_agents_signal(home: Path) -> Path:
    (home / ".agents").mkdir(parents=True, exist_ok=True)
    return agents_skills_root(home)


def claim_sync_workspace(skills_root: Path) -> Path:
    """Arrange a claimed on-disk sync workspace for crash-recovery scenarios.

    Mirrors the sentinel contract production writes under SYNC_WORKSPACE_DIRNAME.
    """
    workspace = skills_root / SYNC_WORKSPACE_DIRNAME
    workspace.mkdir(parents=True, mode=0o700)
    sentinel = workspace / "workspace.json"
    sentinel.write_text(
        json.dumps(
            {
                "owner": "gumloop-skill-sync",
                "schema_version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    sentinel.chmod(0o600)
    for name in ("displaced", "prepared", "removed"):
        (workspace / name).mkdir(exist_ok=True)
    return workspace


def save_configured_credentials() -> None:
    save_credentials(Credentials(api_key="key", user_id="user_fixture"))


def write_sync_config(home: Path) -> Path:
    destination = home / ".gumloop" / "sync" / "config.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "organization_id": ORGANIZATION_ID,
        "schema_version": 1,
        "scheduler_gumloop_path": "/tmp/gumloop-test",
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def write_sync_state(
    home: Path,
    *,
    manifest_hash: str | None,
    status: str = "success",
    last_result: dict[str, Any] | None = None,
) -> Path:
    destination = home / ".gumloop" / "sync" / "state.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_attempt_at": FIXTURE_INSTALLED_AT.isoformat(),
        "last_result": last_result or {},
        "last_success_at": FIXTURE_INSTALLED_AT.isoformat(),
        "manifest_hash": manifest_hash,
        "schema_version": 1,
        "status": status,
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def fixture_bytes(relative_path: str) -> bytes:
    return (FIXTURE_ROOT / relative_path).read_bytes()


def manifest_hash_from_archive(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        manifest = json.loads(archive.read("gumloop-sync-manifest.json"))
    return manifest["manifest"]["hash"]


def bundle_with_manifest_fixture(
    bundle_path: str,
    manifest_path: str,
) -> bytes:
    """Replace a bundle's embedded manifest with another shared fixture."""
    destination = io.BytesIO()
    with (
        zipfile.ZipFile(FIXTURE_ROOT / bundle_path) as source,
        zipfile.ZipFile(destination, "w") as archive,
    ):
        for info in source.infolist():
            content = source.read(info)
            if info.filename == "gumloop-sync-manifest.json":
                content = (json.dumps(load_json(manifest_path), indent=2, sort_keys=True) + "\n").encode()
            archive.writestr(info, content)
    return destination.getvalue()


def _plan_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
    }


def _download_headers() -> dict[str, str]:
    return {
        "Content-Type": SYNC_BUNDLE_CONTENT_TYPE,
    }


def register_plan_response(
    http: respx.MockRouter,
    response_path: str,
    *,
    status_code: int = 200,
) -> respx.Route:
    return http.post(PLAN_URL).mock(
        return_value=httpx.Response(
            status_code,
            json=load_json(response_path),
            headers=_plan_headers(),
        )
    )


def register_plan_error_response(
    http: respx.MockRouter,
    response_path: str,
    *,
    status_code: int,
) -> respx.Route:
    return http.post(PLAN_URL).mock(return_value=httpx.Response(status_code, json=load_json(response_path)))


def register_plan_transport_failure(
    http: respx.MockRouter,
    error: Exception,
) -> respx.Route:
    return http.post(PLAN_URL).mock(side_effect=error)


def register_download_response(
    http: respx.MockRouter,
    bundle_path: str,
    *,
    content: bytes | None = None,
) -> respx.Route:
    archive_bytes = content if content is not None else fixture_bytes(bundle_path)
    return http.post(DOWNLOAD_URL).mock(
        return_value=httpx.Response(
            200,
            content=archive_bytes,
            headers=_download_headers(),
        )
    )


def invoke_sync(
    cli_runner: Any,
    *,
    stateless: bool = False,
    extra_args: list[str] | None = None,
) -> Result:
    args = ["sync"]
    if stateless:
        args.extend(["--once", "--non-interactive"])
    args.append("--json")
    if extra_args:
        args.extend(extra_args)
    return cli_runner.invoke(app, args)


def parse_json_envelope(result: Result) -> dict[str, Any]:
    for stream in (result.stdout, result.stderr):
        text = (stream or "").strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("sync JSON envelope must be an object")
        return payload
    raise ValueError("sync command did not emit JSON output")


def change_for_action(envelope: dict[str, Any], action: str) -> dict[str, Any]:
    return next(change for change in envelope["result"]["changes"] if change.get("action") == action)


def skill_content_files(skill_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_bytes()
        for path in skill_dir.rglob("*")
        if path.is_file() and path.name != MARKER_FILENAME
    }


def configure_environment(
    monkeypatch: Any,
    values: dict[str, str | None],
) -> None:
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def install_skill_from_bundle(
    home: Path,
    bundle_path: str,
    *,
    published_version_id: str,
    content_hash: str,
    installed_at: datetime = FIXTURE_INSTALLED_AT,
) -> Path:
    skills_root = ensure_agents_signal(home)
    content = fixture_bytes(bundle_path)
    with tempfile.TemporaryDirectory(dir=home) as staging_parent:
        staged = stage_sync_bundle(
            SyncBundleDownload(
                content=content,
                content_type=SYNC_BUNDLE_CONTENT_TYPE,
            ),
            expected_organization_id=ORGANIZATION_ID,
            plan_limits=CliSyncLimits.model_validate(load_json("responses/normal-plan.json")["limits"]),
            staging_parent=Path(staging_parent),
        )
        skill = staged.manifest.skills[0]
        if skill.published_version_id != published_version_id or skill.content_hash != content_hash:
            raise ValueError("fixture identity does not match the requested installed state")
        prepared = prepare_target_reconciliation(
            target=PhysicalTarget(
                skills_root=skills_root,
                logical_targets=("agent_skills",),
            ),
            organization_id=ORGANIZATION_ID,
            bundle=staged,
            backup_base=None,
            installed_at=installed_at,
        )
        try:
            outcome = prepared.apply()
        finally:
            prepared.cleanup()
        if outcome.error is not None:
            raise RuntimeError(outcome.error)
    return skills_root / SKILL_INSTALL_NAME


def snapshot_skill_tree(skills_root: Path) -> dict[str, SkillSnapshot]:
    if not skills_root.exists():
        return {}
    snapshots: dict[str, SkillSnapshot] = {}
    for entry in sorted(skills_root.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        paths: dict[str, bytes] = {}
        for file_path in sorted(entry.rglob("*")):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(entry).as_posix()
            paths[relative] = file_path.read_bytes()
        marker_path = entry / MARKER_FILENAME
        marker: dict[str, Any] | None = None
        if marker_path.is_file():
            raw_marker = marker_path.read_text(encoding="utf-8")
            try:
                parsed = json.loads(raw_marker)
                marker = parsed if isinstance(parsed, dict) else {"_raw": raw_marker}
            except json.JSONDecodeError:
                marker = {"_raw": raw_marker}
        snapshots[entry.name] = SkillSnapshot(paths=paths, marker=marker)
    return snapshots


def expected_skill_files(bundle_path: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    prefix = f"{SKILL_INSTALL_NAME}/"
    with zipfile.ZipFile(FIXTURE_ROOT / bundle_path) as archive:
        for name in archive.namelist():
            if not name.startswith(prefix):
                continue
            relative_path = name.removeprefix(prefix)
            if relative_path:
                files[relative_path] = archive.read(name)
    return files
