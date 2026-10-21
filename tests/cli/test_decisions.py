from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

REQUEST = {
    "model": "typesafe/jev-1.13",
    "state": {"message": "The screen is blank"},
    "questions": {"is_bug": {"type": "noul", "instructions": "Is this a software defect?"}},
}
RESPONSE = {
    "id": "decision-1",
    "model": "typesafe/jev-1.13",
    "answers": {"is_bug": {"type": "noul", "noul": 0.95}},
    "usage": {"input_tokens": 20, "output_tokens": 0, "cost": 0.0001},
}


@pytest.mark.parametrize("scope_source", ["flag", "environment", "flag_overrides_environment"])
@respx.mock
def test_decision_team_scope(cli_runner: CliRunner, monkeypatch, scope_source: str) -> None:
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{API_BASE}/decisions").respond(200, json=RESPONSE)
    if scope_source != "flag":
        monkeypatch.setenv("GUMLOOP_TEAM_ID", "environment_team")
    else:
        monkeypatch.delenv("GUMLOOP_TEAM_ID", raising=False)
    options = ["--team-id", "flag_team"] if scope_source != "environment" else []
    result = cli_runner.invoke(app, [*options, "decisions", "create", "--args-json", json.dumps(REQUEST), "--json"])
    assert result.exit_code == 0, result.output
    assert route.calls[0].request.url.params["team_id"] == (
        "environment_team" if scope_source == "environment" else "flag_team"
    )


@respx.mock
def test_decision_file_requires_utf8(cli_runner: CliRunner, tmp_path) -> None:
    save_credentials(Credentials(api_key="key"))
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff")
    result = cli_runner.invoke(app, ["decisions", "create", "--args-file", str(path), "--json"])
    assert result.exit_code == 1
    assert "UTF-8" in json.loads(result.output)["error"]["message"]
    assert "Traceback" not in result.output
    assert not respx.calls


@pytest.mark.parametrize("source", ["inline", "file", "stdin"])
@respx.mock
def test_decision_request_sources(cli_runner: CliRunner, tmp_path, source: str) -> None:
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{API_BASE}/decisions").mock(return_value=httpx.Response(200, json=RESPONSE))
    raw = json.dumps(REQUEST)
    request_file = tmp_path / "decision.json"
    request_file.write_text(raw)
    options = {"inline": ["--args-json", raw], "file": ["--args-file", str(request_file)], "stdin": ["--args", "-"]}

    result = cli_runner.invoke(app, ["decisions", "create", *options[source], "--json"], input=raw)

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == REQUEST
    assert json.loads(result.output)["answers"]["is_bug"]["noul"] == 0.95
    assert json.loads(result.output)["usage"]["input_tokens"] == 20


@respx.mock
def test_decision_human_output(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.post(f"{API_BASE}/decisions").mock(return_value=httpx.Response(200, json=RESPONSE))
    result = cli_runner.invoke(app, ["decisions", "create", "--args-json", json.dumps(REQUEST)])
    assert result.exit_code == 0, result.output
    assert "is_bug" in result.output
    assert "0.95" in result.output


@pytest.mark.parametrize("raw", ["[]", "{", '{"state":"missing model and questions"}'])
def test_decision_invalid_request(cli_runner: CliRunner, raw: str) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["decisions", "create", "--args-json", raw, "--json"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


@respx.mock
def test_decision_api_error(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.post(f"{API_BASE}/decisions").mock(
        return_value=httpx.Response(403, json={"error": {"message": "Model access denied", "code": "forbidden"}})
    )
    result = cli_runner.invoke(app, ["decisions", "create", "--args-json", json.dumps(REQUEST), "--json"])
    assert result.exit_code != 0
    assert "Model access denied" in result.output
