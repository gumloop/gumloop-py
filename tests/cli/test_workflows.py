from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize("bulk", [False, True])
@respx.mock
def test_cli_workflow_explicit_upload_failure_exits_nonzero(cli_runner: CliRunner, tmp_path: Path, bulk: bool) -> None:
    save_credentials(Credentials(api_key="key"))
    paths = [tmp_path / "one.txt", *([tmp_path / "two.txt"] if bulk else [])]
    for path in paths:
        path.write_text("test")
    payload = {"success": False} if bulk else {"success": False, "file_name": "one.txt"}
    respx.post(f"{API_BASE}/{'upload_files' if bulk else 'upload_file'}").respond(200, json=payload)
    result = cli_runner.invoke(app, ["workflows", "upload", *map(str, paths), "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False


@respx.mock
def test_cli_workflow_run_input_stdin_and_wait(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    start = respx.post(f"{API_BASE}/start_pipeline").respond(200, json={"run_id": "run", "saved_item_id": "tab"})
    respx.get(f"{API_BASE}/get_pl_run").respond(200, json={"run_id": "run", "state": "DONE", "outputs": {"Output": 1}})
    result = cli_runner.invoke(
        app,
        ["workflows", "run", "tab", "--args", "-", "--wait", "--project-id", "project", "--json"],
        input='{"Input":1}',
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["outputs"] == {"Output": 1}
    assert json.loads(start.calls[0].request.content)["pipeline_inputs"] == [{"input_name": "Input", "value": 1}]


@respx.mock
def test_cli_workflow_timeout_keeps_run_id(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.post(f"{API_BASE}/start_pipeline").respond(200, json={"run_id": "active-run", "saved_item_id": "tab"})
    result = cli_runner.invoke(app, ["workflows", "run", "tab", "--wait", "--timeout", "0", "--json"])
    assert result.exit_code != 0
    assert "active-run" in result.output
    assert "timed out" in result.output


@respx.mock
def test_cli_workflow_binary_transfer_and_download_error(cli_runner: CliRunner, tmp_path: Path) -> None:
    save_credentials(Credentials(api_key="key"))
    source = tmp_path / "source.bin"
    source.write_bytes(b"hello\x00\xff")
    respx.post(f"{API_BASE}/upload_file").respond(200, json={"success": True, "file_name": "stored"})
    uploaded = cli_runner.invoke(app, ["workflows", "upload", str(source), "--json"])
    assert uploaded.exit_code == 0, uploaded.output
    destination = tmp_path / "output.bin"
    respx.post(f"{API_BASE}/download_file").respond(200, content=b"hello\x00\xff")
    downloaded = cli_runner.invoke(app, ["workflows", "download", "stored", "--output", str(destination), "--json"])
    assert downloaded.exit_code == 0, downloaded.output
    assert destination.read_bytes() == source.read_bytes()
    limited = cli_runner.invoke(
        app, ["workflows", "download", "stored", "--output", str(destination), "--max-bytes", "1", "--json"]
    )
    assert limited.exit_code != 0
    assert destination.read_bytes() == source.read_bytes()


@respx.mock
def test_cli_workflow_bulk_partial_upload_exits_nonzero(cli_runner: CliRunner, tmp_path: Path) -> None:
    save_credentials(Credentials(api_key="key"))
    paths = [tmp_path / name for name in ("one.txt", "two.txt")]
    for path in paths:
        path.write_text("test")
    respx.post(f"{API_BASE}/upload_files").respond(
        207, json={"partial_success": True, "uploaded_files": ["one.txt"], "failed_files": ["two.txt"]}
    )
    result = cli_runner.invoke(app, ["workflows", "upload", *map(str, paths), "--json"])
    assert result.exit_code != 0
    assert json.loads(result.output)["failed_files"] == ["two.txt"]
