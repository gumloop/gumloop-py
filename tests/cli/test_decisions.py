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
