"""Fixtures for live integration tests. Each fixture reads one env var
and fails loudly if missing — silent skips hide configuration drift."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from gumloop import Gumloop
from gumloop import GumloopClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(
            f"required env var {name} is not set — populate gumloop-py/.env "
            f"or export it before running live tests",
            pytrace=False,
        )
    return value


@pytest.fixture(scope="session")
def api_key() -> str:
    return _required("GUMLOOP_API_KEY")


@pytest.fixture(scope="session")
def user_id() -> str:
    return _required("GUMLOOP_USER_ID")


@pytest.fixture(scope="session")
def test_flow_id() -> str:
    return _required("GUMLOOP_TEST_FLOW_ID")


@pytest.fixture
def live_client(api_key: str, user_id: str) -> GumloopClient:
    return GumloopClient(api_key=api_key, user_id=user_id)


@pytest.fixture
def dev_client(api_key: str, user_id: str) -> Gumloop:
    # GUMLOOP_BASE_URL gates the dev-API tests: the dev API isn't on
    # prod yet, so blindly hitting the default URL would be all 404s.
    base_url = _required("GUMLOOP_BASE_URL")
    return Gumloop(api_key=api_key, user_id=user_id, base_url=base_url)


_SKILL_MD = "---\nname: live-test-skill\ndescription: live test skill\n---\n\n# Live\nDo nothing."


@pytest.fixture
def make_skill(dev_client: Gumloop):
    """Factory for live skills; deletes everything it created on teardown."""
    created: list[str] = []

    def _make(name: str = "live-skill"):
        skill = dev_client.skills.create({"SKILL.md": _SKILL_MD}, name=name).skill
        created.append(skill.id)
        return skill

    yield _make
    for skill_id in created:
        dev_client.skills.delete(skill_id)


@pytest.fixture
def make_agent(dev_client: Gumloop):
    """Factory for live agents; deactivates everything it created on teardown."""
    created: list[str] = []

    def _make(**kwargs):
        kwargs.setdefault("name", "Live Verb Agent")
        kwargs.setdefault("model_name", "auto")
        agent = dev_client.agents.create(**kwargs).agent
        created.append(agent.id)
        return agent

    yield _make
    for agent_id in created:
        dev_client.agents.update(agent_id, is_active=False)
