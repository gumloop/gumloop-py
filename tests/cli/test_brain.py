from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

_RESULT = {
    "document_id": "notion:doc_1",
    "source": "notion",
    "title": "Onboarding",
    "content": "How we onboard new teammates.",
    "url": "https://notion.so/doc_1",
    "score": 0.87,
}


@respx.mock
def test_brain_search_forwards_query_limit_and_sources(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": []}))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["brain", "search", "onboarding", "--limit", "5", "--source", "notion", "--source", "slack", "--json"],
    )

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls[0].request.content)
    assert body == {"query": "onboarding", "limit": 5, "source_type": ["notion", "slack"]}


@respx.mock
def test_brain_search_renders_result_table(cli_runner: CliRunner) -> None:
    respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": [_RESULT]}))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["brain", "search", "onboarding"])

    assert result.exit_code == 0, result.output
    assert "Onboarding" in result.output
    assert "notion" in result.output
    assert "0.870" in result.output


@respx.mock
def test_brain_search_prints_empty_state(cli_runner: CliRunner) -> None:
    respx.post(f"{API_BASE}/brain/search").mock(return_value=httpx.Response(200, json={"results": []}))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["brain", "search", "nothing"])

    assert result.exit_code == 0, result.output
    assert "No results found." in result.output


@respx.mock
def test_brain_search_surfaces_api_errors(cli_runner: CliRunner) -> None:
    respx.post(f"{API_BASE}/brain/search").mock(
        return_value=httpx.Response(
            402,
            json={
                "error": {
                    "code": "credit_limit_exceeded",
                    "message": "Credit limit exceeded.",
                    "type": "payment_required_error",
                }
            },
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["brain", "search", "q", "--json"])

    assert result.exit_code != 0
