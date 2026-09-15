from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

_ROUTE_RESPONSE = {
    "router": "gumloop-chew",
    "route": {
        "model": "gpt-5.6-luna",
        "lane": "light",
        "verdict_lane": "light",
        "adjustment": None,
        "reasoning_effort": "medium",
        "fallback_models": ["claude-opus-5"],
        "fail_closed": False,
    },
    "candidates": [
        {
            "requested_model": "gpt-5.6-luna",
            "model": "gpt-5.6-luna",
            "lanes": ["light"],
            "lane_basis": "catalog",
            "status": "eligible",
        },
    ],
}


@respx.mock
def test_models_route_forwards_models_and_prompt_file(cli_runner: CliRunner, tmp_path) -> None:
    route = respx.post(f"{API_BASE}/models/route").mock(return_value=httpx.Response(200, json=_ROUTE_RESPONSE))
    save_credentials(Credentials(api_key="key"))
    prompt_file = tmp_path / "agent.md"
    prompt_file.write_text("You summarize email.", encoding="utf-8")

    result = cli_runner.invoke(
        app,
        [
            "models",
            "route",
            "Summarize this email thread",
            "--model",
            "gpt-5.6-luna",
            "--model",
            "claude-opus-5",
            "--system-prompt-file",
            str(prompt_file),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "input": "Summarize this email thread",
        "models": ["gpt-5.6-luna", "claude-opus-5"],
        "agent": {"system_prompt": "You summarize email."},
    }
    assert json.loads(result.output)["route"]["model"] == "gpt-5.6-luna"


@respx.mock
def test_models_route_reads_stdin_and_prints_a_summary(cli_runner: CliRunner) -> None:
    respx.post(f"{API_BASE}/models/route").mock(return_value=httpx.Response(200, json=_ROUTE_RESPONSE))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["models", "route", "--input-stdin", "-"], input="Summarize this email thread")

    assert result.exit_code == 0, result.output
    assert "gpt-5.6-luna" in result.output
    assert "lane=light" in result.output
    assert "fallbacks: claude-opus-5" in result.output


def test_models_route_rejects_input_and_stdin_together(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["models", "route", "hi", "--input-stdin", "-"], input="hi")

    assert result.exit_code != 0
    assert "at most one of INPUT or --input-stdin" in result.output


@respx.mock
def test_models_list_prints_option_values(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "model_groups": [
                    {
                        "groupLabel": "OpenAI",
                        "options": [{"value": "gpt-5.6-luna", "label": "GPT-5.6 Luna", "status": "active"}],
                    }
                ]
            },
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0, result.output
    assert "gpt-5.6-luna" in result.output and "OpenAI" in result.output
