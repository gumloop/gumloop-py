"""Unit tests for GumloopClient.

Each test exercises a specific branch or transformation in client.py.
Tests that would pass purely by re-asserting hardcoded values from the
mock have been deliberately omitted.
"""

from __future__ import annotations

import json
import types
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx

from gumloop import GumloopClient
from gumloop import _client as client_module

API_BASE = "https://api.gumloop.com/api/v1"
START_URL = f"{API_BASE}/start_pipeline"
STATUS_URL = f"{API_BASE}/get_pl_run"

pytestmark = pytest.mark.filterwarnings("ignore:GumloopClient is the legacy flows client:DeprecationWarning")


def _start_response(run_id: str = "run-123") -> dict[str, Any]:
    return {"run_id": run_id, "url": f"https://app.gumloop.com/runs/{run_id}"}


def _status(state: str, **extra: Any) -> dict[str, Any]:
    return {"state": state, **extra}


def _fake_time(ticks: list[float]) -> types.SimpleNamespace:
    # Patched into gumloop.client's namespace, not the real time module,
    # so third-party libraries keep using the real clock.
    it = iter(ticks)
    return types.SimpleNamespace(time=lambda: next(it), sleep=lambda _s: None)


@pytest.fixture
def client() -> GumloopClient:
    return GumloopClient(api_key="k", user_id="u")


@pytest.fixture
def project_client() -> GumloopClient:
    return GumloopClient(api_key="k", user_id="u", project_id="p")


@pytest.fixture(autouse=True)
def _no_sleep() -> Iterator[None]:
    fake = types.SimpleNamespace(time=client_module.time.time, sleep=lambda _s: None)
    with patch.object(client_module, "time", fake):
        yield


# ---------------------------------------------------------------------------
# Input transformation
# ---------------------------------------------------------------------------


@respx.mock
def test_pipeline_inputs_preserves_diverse_value_types(client: GumloopClient) -> None:
    """Catches accidental str()/json.dumps()/etc. coercion in the
    inputs -> pipeline_inputs transformation."""
    start = respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    respx.get(STATUS_URL).mock(return_value=httpx.Response(200, json=_status("DONE", outputs={})))

    inputs = {"n": 42, "f": 3.14, "b": True, "lst": [1, 2], "obj": {"k": "v"}}
    client.run_flow("flow", inputs=inputs)

    sent = json.loads(start.calls[0].request.content)
    reconstructed = {p["input_name"]: p["value"] for p in sent["pipeline_inputs"]}
    assert reconstructed == inputs
    assert len(sent["pipeline_inputs"]) == len(inputs)


# ---------------------------------------------------------------------------
# project_id branching
# ---------------------------------------------------------------------------


@respx.mock
def test_run_flow_project_id_in_body_iff_set(client: GumloopClient, project_client: GumloopClient) -> None:
    start = respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    respx.get(STATUS_URL).mock(return_value=httpx.Response(200, json=_status("DONE", outputs={})))

    client.run_flow("flow", inputs={})
    project_client.run_flow("flow", inputs={})

    body_unset = json.loads(start.calls[0].request.content)
    body_set = json.loads(start.calls[1].request.content)
    assert "project_id" not in body_unset
    assert body_set["project_id"] == project_client.project_id


@respx.mock
def test_get_run_status_project_id_in_query_iff_set(client: GumloopClient, project_client: GumloopClient) -> None:
    """project_id placement differs from run_flow — query string vs body."""
    route = respx.get(STATUS_URL).mock(return_value=httpx.Response(200, json=_status("DONE", outputs={})))

    client.get_run_status("r")
    project_client.get_run_status("r")

    params_unset = route.calls[0].request.url.params
    params_set = route.calls[1].request.url.params
    assert "project_id" not in params_unset
    assert params_set["project_id"] == project_client.project_id


# ---------------------------------------------------------------------------
# Polling state machine
# ---------------------------------------------------------------------------


@respx.mock
def test_polling_loop_iterates_until_terminal_state(client: GumloopClient) -> None:
    """Catches early-return bugs and verifies run_flow returns the
    `outputs` field, not the whole status object."""
    start = respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    poll = respx.get(STATUS_URL).mock(
        side_effect=[
            httpx.Response(200, json=_status("RUNNING")),
            httpx.Response(200, json=_status("RUNNING")),
            httpx.Response(200, json=_status("DONE", outputs={"answer": 42}, log=["x"])),
        ]
    )

    result = client.run_flow("flow", inputs={})

    assert result == {"answer": 42}
    assert start.call_count == 1
    assert poll.call_count == 3


@pytest.mark.parametrize(
    "state, match",
    [
        ("FAILED", "failed"),
        ("TERMINATING", "terminated"),
        ("TERMINATED", "terminated"),
    ],
)
@respx.mock
def test_terminal_failure_states_raise_distinct_messages(client: GumloopClient, state: str, match: str) -> None:
    respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    respx.get(STATUS_URL).mock(return_value=httpx.Response(200, json=_status(state)))

    with pytest.raises(RuntimeError, match=match):
        client.run_flow("flow", inputs={})


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@respx.mock
def test_timeout_raises_when_budget_exceeded(client: GumloopClient) -> None:
    respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    respx.get(STATUS_URL).mock(return_value=httpx.Response(200, json=_status("RUNNING")))

    with patch.object(client_module, "time", _fake_time([0.0, 0.0, 999.0])):
        with pytest.raises(TimeoutError):
            client.run_flow("flow", inputs={}, timeout=1.0)


@respx.mock
def test_none_timeout_disables_deadline_check(client: GumloopClient) -> None:
    """timeout=None must short-circuit the `if timeout and ...` check."""
    respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    respx.get(STATUS_URL).mock(
        side_effect=[
            httpx.Response(200, json=_status("RUNNING")),
            httpx.Response(200, json=_status("DONE", outputs={})),
        ]
    )

    with patch.object(client_module, "time", _fake_time([0.0, 10**9, 10**9])):
        client.run_flow("flow", inputs={}, timeout=None)


@respx.mock
def test_poll_interval_forwarded_to_sleep(client: GumloopClient) -> None:
    respx.post(START_URL).mock(return_value=httpx.Response(200, json=_start_response()))
    respx.get(STATUS_URL).mock(
        side_effect=[
            httpx.Response(200, json=_status("RUNNING")),
            httpx.Response(200, json=_status("DONE", outputs={})),
        ]
    )

    sleeps: list[float] = []
    fake = types.SimpleNamespace(time=client_module.time.time, sleep=lambda s: sleeps.append(s))
    with patch.object(client_module, "time", fake):
        client.run_flow("flow", inputs={}, poll_interval=2.5)

    assert sleeps == [2.5]
