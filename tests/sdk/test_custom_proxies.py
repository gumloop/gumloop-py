from __future__ import annotations

import asyncio
import json

import pytest
import respx

from gumloop import AsyncGumloop
from gumloop import Gumloop
from tests.sdk.helpers import API_BASE

REGISTRATION = {
    "custom_proxy": {"id": "dp-1", "name": "Ada's laptop", "kind": "cli", "is_default": True},
    "gateway_url": "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect",
}
REGISTER_ARGS = {
    "name": "Ada's laptop",
    "public_key": "MCowBQYDK2VwAyEA",
    "machine_name": "Ada's MacBook Pro",
    "cli_version": "0.6.0",
}
OPERATIONS = [
    ("register_cli", (), REGISTER_ARGS, "POST", "custom-proxies", 201, REGISTRATION),
    (
        "create_gateway_token",
        ("dp-1",),
        {},
        "POST",
        "custom-proxies/dp-1/gateway-token",
        200,
        {"gateway_token": "t"},
    ),
    ("delete", ("dp-1",), {}, "DELETE", "custom-proxies/dp-1", 204, None),
]


@pytest.mark.parametrize(("operation", "args", "kwargs", "method", "path", "status", "payload"), OPERATIONS)
@pytest.mark.parametrize("asynchronous", [False, True])
@respx.mock
def test_custom_proxy_operations(operation, args, kwargs, method, path, status, payload, asynchronous):
    route = respx.request(method, f"{API_BASE}/{path}").respond(status, json=payload)

    async def run():
        async with AsyncGumloop(api_key="key", user_id="actor") as client:
            return await getattr(client.custom_proxies, operation)(*args, **kwargs)

    if asynchronous:
        response = asyncio.run(run())
    else:
        with Gumloop(api_key="key", user_id="actor") as client:
            response = getattr(client.custom_proxies, operation)(*args, **kwargs)

    assert (response.model_dump() if response is not None else None) == payload
    request = route.calls[0].request
    sent = {"kind": "cli", **kwargs} if operation == "register_cli" else kwargs
    assert (json.loads(request.content) if request.content else None) == (sent or None)
