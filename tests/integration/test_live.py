"""Live integration tests — hit the real Gumloop API.

Tests declare the resources they need via fixtures (``live_client``,
``test_flow_id``, etc.). Each fixture reads one env var and skips the
test if it's missing, so partial ``.env`` setups still run whatever is
exercisable.
"""

from __future__ import annotations

import httpx
import pytest

from gumloop import GumloopClient


def test_run_flow_completes_and_returns_outputs(live_client: GumloopClient, test_flow_id: str) -> None:
    """A successful run yields a dict — confirms the SDK's contract with
    the API on the ``outputs`` field name and shape."""
    outputs = live_client.run_flow(test_flow_id, inputs={}, timeout=60.0)

    assert isinstance(outputs, dict)


def test_invalid_run_id_surfaces_an_error(live_client: GumloopClient) -> None:
    """Asking for a run that doesn't exist must raise — exercises the
    SDK's ``raise_for_status`` path against a real 4xx response."""
    with pytest.raises(httpx.HTTPStatusError):
        live_client.get_run_status("does-not-exist-" + "0" * 16)
