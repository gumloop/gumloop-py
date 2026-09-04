from __future__ import annotations

import asyncio

import httpx
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from gumloop.types import EvaluationTarget
from tests.sdk.helpers import API_BASE
from tests.sdk.helpers import auth_header
from tests.sdk.helpers import request_json

EVALUATION = {
    "id": "eval_1",
    "scope": "organization",
    "agent_id": None,
    "organization_id": "org_1",
    "name": "Support tone",
    "description": None,
    "enabled": False,
    "targets": [{"type": "team", "id": "team_1"}],
    "covered_agent_count": 3,
    "config": {"model_name": "auto", "frequency": "debounced", "language": "auto", "include_auto_tags": True},
    "run_summary": {"graded_count": 4, "success_rate": 0.75},
    "creator": {"id": "user_1"},
    "created_at": "2026-09-01T00:00:00+00:00",
    "updated_at": "2026-09-01T00:00:00+00:00",
}


@respx.mock
def test_evaluations_list_scopes_to_organization(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/evaluations").mock(
        return_value=httpx.Response(200, json={"evaluations": [EVALUATION], "next_cursor": None})
    )

    result = client.evaluations.list("org_1", page_size=10)

    assert result.evaluations[0].targets[0].id == "team_1"
    assert result.evaluations[0].run_summary["success_rate"] == 0.75
    params = route.calls[0].request.url.params
    assert params["organization_id"] == "org_1"
    assert params["page_size"] == "10"
    assert auth_header(route.calls[0].request) == "Bearer token"


@respx.mock
def test_evaluations_create_sends_config_and_omits_unset_fields(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/evaluations").mock(
        return_value=httpx.Response(201, json={"evaluation": EVALUATION})
    )

    result = client.evaluations.create(
        organization_id="org_1",
        name="Support tone",
        config={"criteria": [{"name": "Greets", "prompt": "Did the agent greet?"}]},
    )

    assert result.evaluation.id == "eval_1"
    sent = request_json(route.calls[0].request)
    assert sent == {
        "organization_id": "org_1",
        "name": "Support tone",
        "config": {"criteria": [{"name": "Greets", "prompt": "Did the agent greet?"}]},
    }


@respx.mock
def test_evaluations_update_patches_only_provided_fields(client: Gumloop) -> None:
    route = respx.patch(f"{API_BASE}/evaluations/eval_1").mock(
        return_value=httpx.Response(200, json={"evaluation": {**EVALUATION, "enabled": True}})
    )

    result = client.evaluations.update("eval_1", enabled=True)

    assert result.evaluation.enabled is True
    assert request_json(route.calls[0].request) == {"enabled": True}


@respx.mock
def test_evaluations_delete_hits_delete_endpoint(client: Gumloop) -> None:
    route = respx.delete(f"{API_BASE}/evaluations/eval_1").mock(return_value=httpx.Response(204))

    assert client.evaluations.delete("eval_1") is None
    assert route.called


@respx.mock
def test_evaluations_set_targets_accepts_models_and_dicts(client: Gumloop) -> None:
    route = respx.put(f"{API_BASE}/evaluations/eval_1/targets").mock(
        return_value=httpx.Response(
            200,
            json={"targets": [{"type": "organization", "id": "org_1"}], "covered_agent_count": 12, "enabled": True},
        )
    )

    result = client.evaluations.set_targets(
        "eval_1", [EvaluationTarget(type="organization"), {"type": "agent", "id": "agent_9"}]
    )

    assert result.covered_agent_count == 12
    assert request_json(route.calls[0].request) == {
        "targets": [{"type": "organization"}, {"type": "agent", "id": "agent_9"}]
    }


@respx.mock
def test_evaluations_run_accepts_single_session_id_and_dry_run(client: Gumloop) -> None:
    route = respx.post(f"{API_BASE}/evaluations/eval_1/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "dry_run": True,
                "credit_cost": 1,
                "results": [{"id": None, "session_id": "session_1", "status": "planned"}],
                "skipped": [{"session_id": "session_2", "reason": "ineligible", "result_id": None}],
            },
        )
    )

    result = client.evaluations.run("eval_1", "session_1", dry_run=True)

    assert result.results[0].status == "planned"
    assert result.skipped[0].reason == "ineligible"
    assert request_json(route.calls[0].request) == {"session_ids": ["session_1"], "dry_run": True}


@respx.mock
def test_evaluations_list_results_forwards_filters(client: Gumloop) -> None:
    route = respx.get(f"{API_BASE}/evaluations/eval_1/results").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "res_1",
                        "evaluation_id": "eval_1",
                        "session_id": "session_1",
                        "agent_id": "agent_9",
                        "status": "completed",
                        "grade": "pass",
                    }
                ],
                "next_cursor": "cursor_2",
            },
        )
    )

    result = client.evaluations.list_results("eval_1", grade="pass", created_after="2026-09-01T00:00:00Z")

    assert result.results[0].session_id == "session_1"
    assert result.next_cursor == "cursor_2"
    params = route.calls[0].request.url.params
    assert params["grade"] == "pass"
    assert params["created_after"] == "2026-09-01T00:00:00Z"
    assert "status" not in params


@respx.mock
def test_evaluations_get_result_and_metrics(client: Gumloop) -> None:
    respx.get(f"{API_BASE}/evaluations/eval_1/results/res_1").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"id": "res_1", "session_id": "session_1", "agent_id": "agent_9", "status": "queued"}},
        )
    )
    metrics_route = respx.get(f"{API_BASE}/evaluations/eval_1/metrics").mock(
        return_value=httpx.Response(200, json={"days": 7, "grades": {"pass": 3}})
    )

    assert client.evaluations.get_result("eval_1", "res_1").result.status == "queued"
    metrics = client.evaluations.metrics("eval_1", days=7)

    assert metrics.grades == {"pass": 3}
    assert metrics_route.calls[0].request.url.params["days"] == "7"


@respx.mock
def test_async_evaluations_create_and_run() -> None:
    respx.post(f"{API_BASE}/evaluations").mock(return_value=httpx.Response(201, json={"evaluation": EVALUATION}))
    respx.post(f"{API_BASE}/evaluations/eval_1/run").mock(
        return_value=httpx.Response(202, json={"dry_run": False, "credit_cost": 2, "results": [], "skipped": []})
    )

    async def run() -> None:
        async with AsyncGumloop(access_token="token") as client:
            created = await client.evaluations.create(organization_id="org_1", name="Support tone")
            queued = await client.evaluations.run(created.evaluation.id, ["session_1", "session_2"])
            assert queued.credit_cost == 2

    asyncio.run(run())
