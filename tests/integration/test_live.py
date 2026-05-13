"""Live integration tests against the real Gumloop API. Each test skips
when its required env var is missing."""

from __future__ import annotations

import httpx
import pytest

from gumloop import APIStatusError
from gumloop import Gumloop
from gumloop import GumloopClient


def test_run_flow_completes_and_returns_outputs(live_client: GumloopClient, test_flow_id: str) -> None:
    outputs = live_client.run_flow(test_flow_id, inputs={}, timeout=60.0)

    assert isinstance(outputs, dict)


def test_invalid_run_id_surfaces_an_error(live_client: GumloopClient) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        live_client.get_run_status("does-not-exist-" + "0" * 16)


def test_models_list_returns_model_groups_envelope(dev_client: Gumloop) -> None:
    response = dev_client.models.list()

    assert "model_groups" in response
    assert isinstance(response["model_groups"], list)


def test_teams_list_returns_teams_with_id_and_name(dev_client: Gumloop) -> None:
    response = dev_client.teams.list()

    assert "teams" in response
    assert isinstance(response["teams"], list)
    for team in response["teams"]:
        assert "id" in team
        assert "name" in team


def test_agents_list_returns_paginated_envelope(dev_client: Gumloop) -> None:
    response = dev_client.agents.list(page_size=5)

    assert "agents" in response
    assert isinstance(response["agents"], list)
    assert "next_cursor" in response


def test_mcp_servers_list_returns_servers_envelope(dev_client: Gumloop) -> None:
    response = dev_client.mcp.list_servers()

    assert "servers" in response
    assert isinstance(response["servers"], list)


def test_skills_list_returns_paginated_envelope(dev_client: Gumloop) -> None:
    response = dev_client.skills.list(page_size=5)

    assert "skills" in response
    assert isinstance(response["skills"], list)


def test_dev_api_invalid_agent_id_raises_api_status_error(dev_client: Gumloop) -> None:
    with pytest.raises(APIStatusError) as exc:
        dev_client.agents.retrieve("agent_does_not_exist_" + "0" * 16)
    assert exc.value.status_code in (403, 404)
