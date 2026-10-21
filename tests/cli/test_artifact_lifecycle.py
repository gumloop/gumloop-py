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
def test_artifact_cli_script_payload_and_consent(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    execute = respx.post(f"{API_BASE}/artifacts/file/execute").respond(200, json={"answer": 3})
    result = cli_runner.invoke(
        app, ["artifacts", "scripts", "execute", "file", "data", "--args", "-", "--json"], input='{"payload":[1,2]}'
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"answer": 3}
    assert json.loads(execute.calls[0].request.content)["payload"] == [1, 2]
    acknowledge = respx.post(f"{API_BASE}/artifacts/file/acknowledgements").respond(204)
    result = cli_runner.invoke(app, ["artifacts", "scripts", "acknowledge-integrations", "file", "version", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(acknowledge.calls[0].request.content)["version_id"] == "version"


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


@pytest.mark.parametrize("script", [False, True])
@respx.mock
def test_artifact_output_requires_explicit_replace(cli_runner, tmp_path, script):
    save_credentials(Credentials(api_key="key"))
    target = tmp_path / "existing.bin"
    target.write_bytes(b"original")
    route = (
        respx.post(f"{API_BASE}/artifacts/file/execute") if script else respx.get(f"{API_BASE}/artifacts/file/content")
    ).respond(200, content=b"replacement")
    command = ["artifacts", "scripts", "execute", "file", "data"] if script else ["artifacts", "content", "file"]
    result = cli_runner.invoke(app, [*command, "--output", str(target), "--json"])
    assert result.exit_code != 0
    assert target.read_bytes() == b"original"
    assert not route.called
    result = cli_runner.invoke(app, [*command, "--output", str(target), "--force", "--json"])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"replacement"


@pytest.mark.parametrize("script", [False, True])
@respx.mock
def test_failed_disk_write_keeps_existing_download(cli_runner, tmp_path, script):
    save_credentials(Credentials(api_key="key"))
    target = tmp_path / "existing.bin"
    target.write_bytes(b"original")
    (
        respx.post(f"{API_BASE}/artifacts/file/execute") if script else respx.get(f"{API_BASE}/artifacts/file/content")
    ).respond(200, content=b"replacement")
    command = ["artifacts", "scripts", "execute", "file", "data"] if script else ["artifacts", "content", "file"]
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


@respx.mock
def test_script_consent_uses_policy_version_independently_of_content(cli_runner):
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/artifacts/file").respond(
        200,
        json={
            "id": "file",
            "version_id": "vfsh1-content",
            "consent_version_id": "script-policy-v2",
            "scripts": {"data": {"tools": ["gmail__search"]}},
        },
    )
    listed = cli_runner.invoke(app, ["artifacts", "scripts", "list", "file", "--json"])
    assert listed.exit_code == 0, listed.output
    details = json.loads(listed.output)
    assert details["version_id"] == "vfsh1-content"
    assert details.get("consent_version_id") == "script-policy-v2"
    assert details["scripts"] == {"data": {"tools": ["gmail__search"]}}
    ack = respx.post(f"{API_BASE}/artifacts/file/acknowledgements").respond(204)
    acknowledged = cli_runner.invoke(
        app, ["artifacts", "scripts", "acknowledge-integrations", "file", details["consent_version_id"], "--json"]
    )
    assert acknowledged.exit_code == 0, acknowledged.output
    assert json.loads(ack.calls[0].request.content) == {"ack_type": "integrations", "version_id": "script-policy-v2"}
