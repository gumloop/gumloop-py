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

    assert isinstance(response.model_groups, list)


def test_teams_list_returns_teams_with_id_and_name(dev_client: Gumloop) -> None:
    response = dev_client.teams.list()

    assert isinstance(response.teams, list)
    for team in response.teams:
        assert team.id
        assert team.name


def test_agents_list_returns_paginated_envelope(dev_client: Gumloop) -> None:
    response = dev_client.agents.list(page_size=5)

    assert isinstance(response.agents, list)
    # ``next_cursor`` can be None when there's a single page; just check it
    # is the declared field rather than its truthiness.
    assert hasattr(response, "next_cursor")


def test_mcp_servers_list_returns_servers_envelope(dev_client: Gumloop) -> None:
    response = dev_client.mcp.list_servers()

    assert isinstance(response.servers, list)


def test_skills_list_returns_paginated_envelope(dev_client: Gumloop) -> None:
    response = dev_client.skills.list(page_size=5)

    assert isinstance(response.skills, list)


def test_dev_api_invalid_agent_id_raises_api_status_error(dev_client: Gumloop) -> None:
    with pytest.raises(APIStatusError) as exc:
        dev_client.agents.retrieve("agent_does_not_exist_" + "0" * 16)
    assert exc.value.status_code in (403, 404)


class TestAgentSkillAttachments:
    def test_create_agent_attaches_initial_skills(self, dev_client: Gumloop, make_skill, make_agent) -> None:
        skill = make_skill("live-skill-initial")

        agent = make_agent(skill_ids=[skill.id])

        assert agent.skill_ids == [skill.id]

    def test_attach_skills_adds_without_touching_existing(self, dev_client: Gumloop, make_skill, make_agent) -> None:
        existing, added = make_skill("live-skill-a"), make_skill("live-skill-b")
        agent = make_agent(skill_ids=[existing.id])

        response = dev_client.agents.attach_skills(agent.id, added.id)

        assert response.attached == [added.id]
        assert sorted(response.skill_ids) == sorted([existing.id, added.id])

    def test_attach_replay_is_reported_not_errored(self, dev_client: Gumloop, make_skill, make_agent) -> None:
        skill = make_skill()
        agent = make_agent(skill_ids=[skill.id])

        response = dev_client.agents.attach_skills(agent.id, skill.id)

        assert response.attached == []
        assert response.already_attached == [skill.id]

    def test_unknown_skill_id_rejects_whole_batch(self, dev_client: Gumloop, make_skill, make_agent) -> None:
        valid = make_skill()
        agent = make_agent()

        with pytest.raises(APIStatusError) as exc:
            dev_client.agents.attach_skills(agent.id, [valid.id, "sk_does_not_exist"])

        assert exc.value.code == "skill_not_found"
        assert exc.value.details.get("skill_ids") == ["sk_does_not_exist"]
        assert dev_client.agents.retrieve(agent.id).agent.skill_ids == []

    def test_detach_skills_removes_and_replay_reports(self, dev_client: Gumloop, make_skill, make_agent) -> None:
        keep, remove = make_skill("live-keep"), make_skill("live-remove")
        agent = make_agent(skill_ids=[keep.id, remove.id])

        response = dev_client.agents.detach_skills(agent.id, remove.id)

        assert response.detached == [remove.id]
        assert response.skill_ids == [keep.id]
        assert dev_client.agents.detach_skills(agent.id, remove.id).already_detached == [remove.id]

    def test_list_skills_returns_attached_set(self, dev_client: Gumloop, make_skill, make_agent) -> None:
        skill = make_skill()
        agent = make_agent(skill_ids=[skill.id])

        listed = dev_client.agents.list_skills(agent.id)

        assert [s.id for s in listed.skills] == [skill.id]


class TestAgentMcpServers:
    def test_attach_mcp_server_creates_catalog_entry(self, dev_client: Gumloop, make_agent) -> None:
        agent = make_agent()

        response = dev_client.agents.attach_mcp_server(agent.id, "gmail", approval_mode="off")

        assert response.created is True
        assert response.mcp_server.get("server_id") == "gmail"
        assert response.mcp_server.get("approval_mode") == "off"

    def test_attach_again_updates_config_in_place(self, dev_client: Gumloop, make_agent) -> None:
        agent = make_agent()
        dev_client.agents.attach_mcp_server(agent.id, "gmail", approval_mode="off")

        response = dev_client.agents.attach_mcp_server(agent.id, "gmail", approval_mode="always")

        assert response.created is False
        assert response.mcp_server.get("approval_mode") == "always"

    def test_identity_keys_cannot_be_spoofed_and_secrets_never_round_trip(
        self, dev_client: Gumloop, make_agent,
    ) -> None:
        agent = make_agent()

        response = dev_client.agents.attach_mcp_server(
            agent.id, "gmail",
            mcp_server_url="https://evil.example.com", secret_id="spoofed",
        )

        assert response.mcp_server.get("server_id") == "gmail"
        assert "secret_id" not in response.mcp_server
        assert response.mcp_server.get("mcp_server_url") is None

    def test_unknown_server_id_is_a_loud_404(self, dev_client: Gumloop, make_agent) -> None:
        agent = make_agent()

        with pytest.raises(APIStatusError) as exc:
            dev_client.agents.attach_mcp_server(agent.id, "not_a_real_server")

        assert exc.value.code == "mcp_server_not_found"
        assert exc.value.status_code == 404

    def test_detach_mcp_server_is_idempotent(self, dev_client: Gumloop, make_agent) -> None:
        agent = make_agent()
        dev_client.agents.attach_mcp_server(agent.id, "gmail")

        assert dev_client.agents.detach_mcp_server(agent.id, "gmail").detached is True
        assert dev_client.agents.detach_mcp_server(agent.id, "gmail").detached is False
