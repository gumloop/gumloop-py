from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@respx.mock
def test_artifact_cli_binary_failure_preserves_output(cli_runner: CliRunner, tmp_path: Path) -> None:
    save_credentials(Credentials(api_key="key"))
    target = tmp_path / "file.bin"
    target.write_bytes(b"original")
    respx.get(f"{API_BASE}/artifacts/file/content").respond(200, content=b"big binary")
    result = cli_runner.invoke(
        app, ["artifacts", "content", "file", "--output", str(target), "--max-bytes", "1", "--force", "--json"]
    )
    assert result.exit_code != 0
    assert target.read_bytes() == b"original"


@respx.mock
def test_artifact_cli_rename_requires_choice_and_sends_null(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["artifacts", "rename", "file", "--json"])
    assert result.exit_code != 0
    route = respx.put(f"{API_BASE}/artifacts/file/name").respond(200, json={"name": None})
    result = cli_runner.invoke(app, ["artifacts", "rename", "file", "--reset", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"name": None}


@respx.mock
def test_artifact_output_requires_explicit_replace(cli_runner, tmp_path):
    save_credentials(Credentials(api_key="key"))
    target = tmp_path / "existing.bin"
    target.write_bytes(b"original")
    route = respx.get(f"{API_BASE}/artifacts/file/content").respond(200, content=b"replacement")
    command = ["artifacts", "content", "file"]
    result = cli_runner.invoke(app, [*command, "--output", str(target), "--json"])
    assert result.exit_code != 0
    assert target.read_bytes() == b"original"
    assert not route.called
    result = cli_runner.invoke(app, [*command, "--output", str(target), "--force", "--json"])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"replacement"


@respx.mock
def test_failed_disk_write_keeps_existing_download(cli_runner, tmp_path):
    save_credentials(Credentials(api_key="key"))
    target = tmp_path / "existing.bin"
    target.write_bytes(b"original")
    respx.get(f"{API_BASE}/artifacts/file/content").respond(200, content=b"replacement")
    command = ["artifacts", "content", "file"]
    open_file = Path.open

    def failing_open(*args, **kwargs):
        stream = open_file(*args, **kwargs)
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        if "w" in mode:
            write = stream.write

            def partial_write(data):
                write(data[:3])
                raise OSError("test disk full")

            stream.write = partial_write
        return stream

    with patch.object(Path, "open", autospec=True, side_effect=failing_open):
        result = cli_runner.invoke(app, [*command, "--output", str(target), "--force", "--json"])
    assert result.exit_code != 0
    assert target.read_bytes() == b"original"
    assert "test disk full" in result.output
    assert sorted(path.name for path in tmp_path.iterdir() if path.is_file()) == ["existing.bin"]


@pytest.mark.parametrize(
    "command,method,path,response",
    [
        (["get", "file"], "GET", "", {"id": "file"}),
        (["rename", "file", "--name", "Renamed"], "PUT", "/name", {"name": "Renamed"}),
        (["delete", "file"], "DELETE", "", {"deleted": True}),
        (["versions", "file"], "GET", "/versions", {"versions": []}),
    ],
)
@respx.mock
def test_new_artifact_commands_forward_explicit_workspace(cli_runner, command, method, path, response):
    save_credentials(Credentials(access_token="personal"))
    route = respx.route(method=method, url=f"{API_BASE}/artifacts/file{path}").respond(
        204 if response is None else 200, json=response
    )
    result = cli_runner.invoke(app, ["--team-id", "selected", "artifacts", *command, "--json"])
    assert result.exit_code == 0, result.output
    assert route.calls[0].request.url.params["team_id"] == "selected"


@respx.mock
def test_new_artifact_binary_commands_forward_explicit_workspace(cli_runner, tmp_path):
    save_credentials(Credentials(access_token="personal"))
    route = respx.get(f"{API_BASE}/artifacts/file/content").respond(200, content=b"download")
    command = ["content", "file"]
    destination = tmp_path / "download.bin"
    result = cli_runner.invoke(
        app, ["--team-id", "selected", "artifacts", *command, "--output", str(destination), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert destination.read_bytes() == b"download"
    assert route.calls[0].request.url.params["team_id"] == "selected"


@respx.mock
def test_existing_artifact_list_keeps_original_workspace_behavior(cli_runner):
    save_credentials(Credentials(access_token="personal"))
    route = respx.get(f"{API_BASE}/agents/agent_1/artifacts").respond(200, json={"artifacts": []})
    result = cli_runner.invoke(app, ["--team-id", "selected", "artifacts", "list", "agent_1", "--json"])
    assert result.exit_code == 0, result.output
    assert "team_id" not in route.calls[0].request.url.params
