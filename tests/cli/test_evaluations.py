from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from gumloop.cli.credentials import Credentials
from gumloop.cli.credentials import save_credentials
from gumloop.cli.main import app
from tests.sdk.helpers import API_BASE

EVALUATION = {
    "id": "eval_1",
    "scope": "organization",
    "organization_id": "org_1",
    "name": "Support tone",
    "enabled": False,
    "targets": [],
    "covered_agent_count": 0,
    "config": {"criteria": []},
    "run_summary": {"graded_count": 0, "success_rate": None},
}


def _mock_organizations() -> None:
    respx.get(f"{API_BASE}/organizations").mock(
        return_value=httpx.Response(200, json={"organizations": [{"id": "org_1", "name": "Acme"}]})
    )


@respx.mock
def test_evaluations_list_resolves_organization_when_omitted(cli_runner: CliRunner) -> None:
    _mock_organizations()
    route = respx.get(f"{API_BASE}/evaluations").mock(
        return_value=httpx.Response(200, json={"evaluations": [EVALUATION], "next_cursor": None})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "list"])

    assert result.exit_code == 0, result.output
    assert "eval_1" in result.output
    assert route.calls[0].request.url.params["organization_id"] == "org_1"


@respx.mock
def test_evaluations_list_uses_explicit_organization_without_lookup(cli_runner: CliRunner) -> None:
    lookup = respx.get(f"{API_BASE}/organizations").mock(return_value=httpx.Response(200, json={"organizations": []}))
    route = respx.get(f"{API_BASE}/evaluations").mock(
        return_value=httpx.Response(200, json={"evaluations": [], "next_cursor": None})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "list", "--organization", "org_2", "--json"])

    assert result.exit_code == 0, result.output
    assert not lookup.called
    assert route.calls[0].request.url.params["organization_id"] == "org_2"


@respx.mock
def test_evaluations_create_reads_config_file(cli_runner: CliRunner, tmp_path) -> None:
    _mock_organizations()
    route = respx.post(f"{API_BASE}/evaluations").mock(
        return_value=httpx.Response(201, json={"evaluation": EVALUATION})
    )
    save_credentials(Credentials(api_key="key"))
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps({"criteria": [{"name": "Greets", "prompt": "Did the agent greet?"}]}))

    result = cli_runner.invoke(
        app, ["evaluations", "create", "--name", "Support tone", "--config-file", str(rubric), "--json"]
    )

    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls[0].request.content)
    assert sent["organization_id"] == "org_1"
    assert sent["config"]["criteria"][0]["name"] == "Greets"


@respx.mock
def test_evaluations_create_rejects_both_config_sources(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app, ["evaluations", "create", "--name", "x", "--config-json", "{}", "--config-file", "rubric.json"]
    )

    assert result.exit_code != 0


@respx.mock
def test_evaluations_update_enable_flag_patches_enabled(cli_runner: CliRunner) -> None:
    route = respx.patch(f"{API_BASE}/evaluations/eval_1").mock(
        return_value=httpx.Response(200, json={"evaluation": {**EVALUATION, "enabled": True}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "update", "eval_1", "--enable"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"enabled": True}


def test_evaluations_update_requires_a_change(cli_runner: CliRunner) -> None:
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "update", "eval_1"])

    assert result.exit_code != 0


@respx.mock
def test_evaluations_targets_builds_typed_target_list(cli_runner: CliRunner) -> None:
    route = respx.put(f"{API_BASE}/evaluations/eval_1/targets").mock(
        return_value=httpx.Response(
            200,
            json={"targets": [{"type": "team", "id": "team_1"}], "covered_agent_count": 5, "enabled": False},
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app, ["evaluations", "targets", "eval_1", "--team", "team_1", "--team", "team_2", "--agent", "agent_9"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "targets": [
            {"type": "team", "id": "team_1"},
            {"type": "team", "id": "team_2"},
            {"type": "agent", "id": "agent_9"},
        ]
    }
    assert "covered agents: 5" in result.output


@respx.mock
def test_evaluations_run_posts_session_ids_with_dry_run(cli_runner: CliRunner) -> None:
    route = respx.post(f"{API_BASE}/evaluations/eval_1/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "dry_run": True,
                "credit_cost": 1,
                "results": [{"id": None, "session_id": "session_1", "status": "planned"}],
                "skipped": [{"session_id": "session_2", "reason": "in_flight", "result_id": "res_9"}],
            },
        )
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "run", "eval_1", "session_1", "session_2", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {"session_ids": ["session_1", "session_2"], "dry_run": True}
    assert "Would queue 1 session(s)" in result.output
    assert "skipped: in_flight" in result.output


@respx.mock
def test_evaluations_results_forwards_filters(cli_runner: CliRunner) -> None:
    route = respx.get(f"{API_BASE}/evaluations/eval_1/results").mock(
        return_value=httpx.Response(200, json={"results": [], "next_cursor": None})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(
        app,
        ["evaluations", "results", "eval_1", "--grade", "pass", "--since", "2026-09-01T00:00:00Z", "--limit", "5"],
    )

    assert result.exit_code == 0, result.output
    params = route.calls[0].request.url.params
    assert params["grade"] == "pass"
    assert params["created_after"] == "2026-09-01T00:00:00Z"
    assert params["page_size"] == "5"


@respx.mock
def test_evaluations_delete_hits_delete_endpoint(cli_runner: CliRunner) -> None:
    route = respx.delete(f"{API_BASE}/evaluations/eval_1").mock(return_value=httpx.Response(204))
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "delete", "eval_1"])

    assert result.exit_code == 0, result.output
    assert route.called


@respx.mock
def test_evaluations_options_prints_json(cli_runner: CliRunner) -> None:
    respx.get(f"{API_BASE}/evaluation-options").mock(
        return_value=httpx.Response(200, json={"grades": ["pass"], "limits": {"run_session_ids": 200}})
    )
    save_credentials(Credentials(api_key="key"))

    result = cli_runner.invoke(app, ["evaluations", "options"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["limits"]["run_session_ids"] == 200
