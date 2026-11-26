from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
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

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--prune", "--yes", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["uploaded"] == []
    assert payload["replaced"] == ["changed.txt"]
    assert payload["pruned"] == ["gone.txt"]
    assert payload["unchanged"] == 1
    assert payload["rejected"] == [{"file_name": "bad.exe", "error": 'unsupported file type ".exe"'}]
    assert sorted(call.request.url.path.rsplit("/", 1)[1] for call in deletes.calls) == ["2", "3"]
    assert upload.calls[0].request.content.count(b'name="files"') == 2


SOURCE = {"id": "src_1", "name": "Docs", "source_type": "direct_file_uploads", "status": "active", "scope": "personal"}


def _source_with_one_file_gone_locally(tmp_path: Path) -> Path:
    """An empty local directory, and a signed-in CLI whose source src_1 still holds gone.txt."""
    docs = tmp_path / "docs"
    docs.mkdir()
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/brain/sources/src_1").respond(200, json={"source": SOURCE})
    respx.get(f"{API_BASE}/brain/sources/src_1/files").respond(
        200, json={"files": [_remote("gone.txt", b"gone", "3").model_dump()], "next_cursor": None}
    )
    respx.delete(f"{API_BASE}/brain/sources/src_1/files/3").respond(200, json={"deleted": True})
    return docs


@respx.mock
def test_brain_sync_prune_is_refused_without_a_terminal_unless_yes_is_passed(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    docs = _source_with_one_file_gone_locally(tmp_path)

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--prune"])

    assert result.exit_code == 1
    refusal = " ".join(result.stderr.split())
    assert "--prune deletes every file in Brain source src_1 that is not in" in refusal
    assert "You cannot undo it; --dry-run shows which files. Nothing was sent. Pass --yes to confirm." in refusal
    assert not respx.calls


@respx.mock
def test_brain_sync_prune_declined_in_a_terminal_sends_nothing(
    cli_runner: CliRunner, tmp_path: Path, answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]]
) -> None:
    docs = _source_with_one_file_gone_locally(tmp_path)
    asked = answer_in_terminal(False)

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--prune"])

    assert result.exit_code == 1
    assert asked == [("Sync and prune Brain source src_1?", False)]
    assert not respx.calls


@respx.mock
def test_brain_sync_prune_confirmed_in_a_terminal_deletes_the_missing_file(
    cli_runner: CliRunner, tmp_path: Path, answer_in_terminal: Callable[[bool | None], list[tuple[str, bool]]]
) -> None:
    docs = _source_with_one_file_gone_locally(tmp_path)
    answer_in_terminal(True)

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--prune"])

    assert result.exit_code == 0, result.output
    assert [call.request.method for call in respx.calls] == ["GET", "GET", "DELETE"]


@respx.mock
def test_brain_sync_prune_dry_run_shows_the_plan_without_asking(cli_runner: CliRunner, tmp_path: Path) -> None:
    docs = _source_with_one_file_gone_locally(tmp_path)

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--prune", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["pruned"] == ["gone.txt"]
    assert [call.request.method for call in respx.calls] == ["GET", "GET"]


@respx.mock
def test_brain_sync_without_prune_keeps_remote_files_and_does_not_ask(cli_runner: CliRunner, tmp_path: Path) -> None:
    docs = _source_with_one_file_gone_locally(tmp_path)

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--source", "src_1", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["pruned"] == []
    assert [call.request.method for call in respx.calls] == ["GET", "GET"]


@respx.mock
def test_brain_sync_prune_into_a_new_source_does_not_ask(cli_runner: CliRunner, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    save_credentials(Credentials(api_key="key"))
    create = respx.post(f"{API_BASE}/brain/sources").respond(201, json={"source": SOURCE})

    result = cli_runner.invoke(app, ["brain", "sync", str(docs), "--create", "Docs", "--prune", "--json"])

    assert result.exit_code == 0, result.output
    assert create.called


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

    result = cli_runner.invoke(app, ["brain", "sync", str(tmp_path)], env={"COLUMNS": "200"})

    assert result.exit_code == 2
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "exactly one of --source or --create" in plain
