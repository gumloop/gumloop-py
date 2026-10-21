from __future__ import annotations

import json
from pathlib import Path

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
        app, ["artifacts", "content", "file", "--output", str(target), "--max-bytes", "1", "--json"]
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
