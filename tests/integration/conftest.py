"""Fixtures for live integration tests.

Each fixture reads one env var and skips the test if missing. Adding a
new resource is a 4-line fixture below.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from gumloop import GumloopClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"set {name} in .env or the shell to run this test")
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
