from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

FACT = {
    "id": "fact_1",
    "kind": "rule",
    "text": "Never open with a greeting.",
    "origin": "user_stated",
    "pinned": True,
    "card": {"type": "tone"},
}


@respx.mock
def test_cards_list_json_and_next_cursor(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    body = {"data": [{"type": "person", "entity_key": "ann@acme.com", "name": "Ann"}], "next_cursor": "c2"}
    route = respx.get(f"{API_BASE}/memory/cards").mock(return_value=httpx.Response(200, json=body))

    result = cli_runner.invoke(app, ["memory", "cards", "list", "--type", "person", "--type", "agent", "--json"])
    assert result.exit_code == 0, result.output
    assert route.calls[0].request.url.params["type"] == "person,agent"
    assert json.loads(result.output)["data"][0]["entity_key"] == "ann@acme.com"

    result = cli_runner.invoke(app, ["memory", "cards", "list", "--limit", "1"])
    assert result.exit_code == 0, result.output
    assert result.output.split("\n")[1].split() == ["person", "ann@acme.com", "Ann", "active"]
    assert "Next cursor: c2" in result.output


@respx.mock
def test_facts_create_and_rules_human_output(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    create = respx.post(f"{API_BASE}/memory/facts").mock(return_value=httpx.Response(201, json=FACT))
    respx.get(f"{API_BASE}/memory/rules").mock(
        return_value=httpx.Response(
            200, json={"tone": {"guide": "Short and direct.", "guide_pinned": True, "rules": [FACT]}, "design": {}}
        )
    )

    result = cli_runner.invoke(
        app,
        ["memory", "facts", "create", "--type", "profile", "--kind", "pattern", "Bullets", "--always-in-prompt"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(create.calls[0].request.content) == {
        "type": "profile",
        "kind": "pattern",
        "text": "Bullets",
        "always_in_prompt": True,
    }
    assert "Remembered fact_1" in result.output

    result = cli_runner.invoke(app, ["memory", "rules", "list"])
    assert result.exit_code == 0, result.output
    assert "tone: (your own guide)" in result.output
    assert "Short and direct." in result.output
    assert "- Never open with a greeting. (fact_1)" in result.output


def test_update_requires_a_field_and_entity_key_requires_type(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    result = cli_runner.invoke(app, ["memory", "facts", "update", "fact_1"])
    assert result.exit_code != 0
    assert "Pass at least one of" in result.output
    result = cli_runner.invoke(app, ["memory", "query", "--entity-key", "launch"])
    assert result.exit_code != 0
    assert "Pass --type" in result.output


@respx.mock
def test_cards_get_handles_empty_singleton(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/memory/cards/note").mock(
        return_value=httpx.Response(200, json={"card": None, "facts": [], "rank": None})
    )
    result = cli_runner.invoke(app, ["memory", "cards", "get", "note"])
    assert result.exit_code == 0, result.output
    assert "Nothing remembered for note yet." in result.output


@respx.mock
def test_revisions_list_shows_undoable_and_sync_start_surfaces_credit_limit(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))
    respx.get(f"{API_BASE}/memory/revisions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "rev_1", "action": "update", "actor": "user", "fact_id": "fact_1", "undoable": True},
                    {"id": "rev_2", "action": "rename", "actor": "user", "undoable": False},
                ]
            },
        )
    )
    respx.post(f"{API_BASE}/memory/sync").mock(
        return_value=httpx.Response(
            402,
            json={"error": {"code": "credit_limit_exceeded", "message": "Credit limit exceeded.", "type": "payment"}},
        )
    )

    result = cli_runner.invoke(app, ["memory", "revisions", "list"])
    assert result.exit_code == 0, result.output
    assert result.output.split("\n")[1].split() == ["rev_1", "update", "user", "fact_1", "yes"]
    assert result.output.split("\n")[2].split() == ["rev_2", "rename", "user", "no"]

    result = cli_runner.invoke(app, ["memory", "sync", "start"])
    assert result.exit_code == 1
    assert "Error: Credit limit exceeded." in result.output
    result = cli_runner.invoke(app, ["memory", "sync", "start", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["code"] == "credit_limit_exceeded"
