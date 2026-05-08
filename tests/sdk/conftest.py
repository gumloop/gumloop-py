from __future__ import annotations

import pytest

from gumloop import AsyncGumloop
from gumloop import Gumloop


@pytest.fixture
def client() -> Gumloop:
    return Gumloop(access_token="token")


@pytest.fixture
def async_client() -> AsyncGumloop:
    return AsyncGumloop(access_token="token")
