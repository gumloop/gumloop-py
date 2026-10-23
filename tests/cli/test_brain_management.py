from __future__ import annotations

import json

import pytest
import respx

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE


@pytest.mark.parametrize(
    ("command", "method", "suffix", "payload"),
    [
        ("sync", "POST", "sync", {"source_id": "source", "status": "queued", "sync_run_id": "run"}),
        ("history", "GET", "sync-runs", {"items": [], "next_cursor": "next"}),
        ("issues", "GET", "issues", {"items": [], "next_cursor": "next"}),
        ("children", "GET", "children", {"connector_id": "source", "items": []}),
    ],
)
@respx.mock
def test_existing_source_inspection_and_sync(cli_runner, command, method, suffix, payload):
    save_credentials(Credentials(api_key="key"))
    route = respx.request(method, f"{API_BASE}/brain/sources/source/{suffix}").respond(200, json=payload)
    result = cli_runner.invoke(app, ["brain", "sources", command, "source", "--json"])
    assert result.exit_code == 0, result.output
    actual = json.loads(result.output)
    assert all(actual[key] == value for key, value in payload.items())
    assert not route.calls[0].request.content


@respx.mock
def test_sync_reports_not_ready_without_setup_retry(cli_runner):
    save_credentials(Credentials(api_key="key"))
    route = respx.post(f"{API_BASE}/brain/sources/source/sync").respond(
        409, json={"error": {"code": "knowledge_source_not_ready", "message": "Source must be ready and active."}}
    )
    result = cli_runner.invoke(app, ["brain", "sources", "sync", "source", "--json"])
    assert result.exit_code == 1
    assert "ready and active" in result.output
    assert route.call_count == 1


@pytest.mark.parametrize("command", ["connect", "configuration", "configure", "browse", "pause", "resume"])
@respx.mock
def test_deferred_source_commands_are_unavailable(cli_runner, command):
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["brain", "sources", command, "source", "--json"])
    assert result.exit_code != 0
    assert not respx.calls
