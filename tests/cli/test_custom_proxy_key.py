from __future__ import annotations

import pytest
from pydantic import ValidationError

from gumloop.cli.custom_proxy_key import CustomProxyRegistration


def test_registration_accepts_an_unencrypted_gateway_on_this_computer():
    registration = CustomProxyRegistration(
        custom_proxy_id="dp-1", name="Ada's laptop", gateway_url="ws://localhost:8443/v1/cli/connect", public_key="key"
    )

    assert registration.gateway_url == "ws://localhost:8443/v1/cli/connect"


def test_registration_refuses_an_unencrypted_remote_gateway():
    with pytest.raises(ValidationError) as refused:
        CustomProxyRegistration(
            custom_proxy_id="dp-1",
            name="Ada's laptop",
            gateway_url="ws://linked-proxy-gateway.gumloop.com/v1/cli/connect",
            public_key="key",
        )

    assert [(error["loc"], error["type"], error["msg"]) for error in refused.value.errors()] == [
        (
            ("gateway_url",),
            "value_error",
            "Value error, the linked proxy gateway must use wss:// unless it runs on this computer",
        )
    ]
