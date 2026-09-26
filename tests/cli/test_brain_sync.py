from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from gumloop.brain_sync import BrainSyncPlan
from gumloop.brain_sync import LocalFile
from gumloop.brain_sync import scan_directory
from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from gumloop.types import BrainFile
from tests.sdk.helpers import API_BASE


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _remote(name: str, content: bytes, file_id: str = "f") -> BrainFile:
    return BrainFile(id=file_id, file_name=name, status="indexed", sha256=_sha(content))


def test_scan_directory_names_files_by_relative_posix_path_and_skips_dotfiles(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "a.txt").write_bytes(b"a")
    (docs / "sub" / "b.md").write_bytes(b"b")
    (docs / ".hidden").write_bytes(b"h")

    files = scan_directory(docs)

    assert [(f.name, f.sha256) for f in files] == [("a.txt", _sha(b"a")), ("sub/b.md", _sha(b"b"))]


def test_plan_splits_new_changed_unchanged_and_pruned() -> None:
    local = [
        LocalFile("same.txt", Path("same.txt"), _sha(b"same")),
        LocalFile("changed.txt", Path("changed.txt"), _sha(b"new")),
        LocalFile("added.txt", Path("added.txt"), _sha(b"added")),
    ]
    remote = [
        _remote("same.txt", b"same", "1"),
        _remote("changed.txt", b"old", "2"),
        _remote("gone.txt", b"gone", "3"),
        BrainFile(id="4", file_name="legacy.txt", status="indexed", sha256=None),
    ]

    plan = BrainSyncPlan.build(local + [LocalFile("legacy.txt", Path("legacy.txt"), _sha(b"legacy"))], remote)

    assert [f.name for f in plan.upload] == ["changed.txt", "added.txt", "legacy.txt"]
    assert [f.id for f in plan.replace] == ["2", "4"]
    assert [f.id for f in plan.prune] == ["3"]
    assert [f.name for f in plan.unchanged] == ["same.txt"]
    assert not plan.is_noop


@respx.mock
def test_brain_sync_replaces_changed_prunes_missing_and_reports_rejections(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "same.txt").write_bytes(b"same")
    (docs / "changed.txt").write_bytes(b"new")
    (docs / "bad.exe").write_bytes(b"nope")
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/brain/sources/src_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": {
                    "id": "src_1",
                    "name": "Docs",
                    "source_type": "direct_file_uploads",
                    "status": "active",
                    "scope": "personal",
                }
            },
        )
    )
    respx.get(f"{API_BASE}/brain/sources/src_1/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    _remote("same.txt", b"same", "1").model_dump(),
                    _remote("changed.txt", b"old", "2").model_dump(),
                    _remote("gone.txt", b"gone", "3").model_dump(),
                ],
                "next_cursor": None,
            },
        )
    )
    deletes = respx.delete(url__regex=rf"{API_BASE}/brain/sources/src_1/files/.*").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    upload = respx.post(f"{API_BASE}/brain/sources/src_1/files").mock(
        return_value=httpx.Response(
            201,
            json={
                "files": [_remote("changed.txt", b"new", "5").model_dump()],
                "rejected": [{"file_name": "bad.exe", "error": 'unsupported file type ".exe"'}],
                "sync_run_id": "run_1",
            },
        )
    )

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--prune", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["uploaded"] == []
    assert payload["replaced"] == ["changed.txt"]
    assert payload["pruned"] == ["gone.txt"]
    assert payload["unchanged"] == 1
    assert payload["rejected"] == [{"file_name": "bad.exe", "error": 'unsupported file type ".exe"'}]
    assert sorted(call.request.url.path.rsplit("/", 1)[1] for call in deletes.calls) == ["2", "3"]
    assert upload.calls[0].request.content.count(b'name="files"') == 2


@respx.mock
def test_brain_sync_treats_all_rejected_batch_as_skips(cli_runner: CliRunner, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "bad.exe").write_bytes(b"nope")
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/brain/sources/src_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": {
                    "id": "src_1",
                    "name": "Docs",
                    "source_type": "direct_file_uploads",
                    "status": "active",
                    "scope": "personal",
                }
            },
        )
    )
    respx.get(f"{API_BASE}/brain/sources/src_1/files").mock(
        return_value=httpx.Response(200, json={"files": [], "next_cursor": None})
    )
    respx.post(f"{API_BASE}/brain/sources/src_1/files").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": "no_files_accepted",
                    "message": "Every file was rejected.",
                    "type": "invalid_request_error",
                    "param": "files",
                    "details": {"rejected": [{"file_name": "bad.exe", "error": 'unsupported file type ".exe"'}]},
                }
            },
        )
    )

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1"])

    assert result.exit_code == 0, result.output
    assert "Skipped bad.exe" in result.output
    assert "0 uploaded" in result.output


@respx.mock
def test_brain_sync_create_requires_exactly_one_target(cli_runner: CliRunner, tmp_path: Path) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["brain", "sync", str(tmp_path)])

    assert result.exit_code != 0
    assert "exactly one of --source or --create" in result.output
