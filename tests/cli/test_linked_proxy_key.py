from __future__ import annotations

import pytest
from pydantic import ValidationError

from gumloop.cli.linked_proxy_key import LinkedProxyRegistration
from gumloop.cli.linked_proxy_key import load_or_create_key
from gumloop.cli.linked_proxy_key import load_registration
from gumloop.cli.linked_proxy_key import save_registration
from gumloop.linked_proxy.sign_in import public_key_text


def test_key_and_registration_persist(temporary_home):
    host = "api.gumloop.com"
    first = public_key_text(load_or_create_key(host))
    registration = LinkedProxyRegistration(
        linked_proxy_id="dp-1",
        name="Ada's laptop",
        gateway_url="wss://linked-proxy-gateway.gumloop.com/v1/cli/connect",
        public_key=first,
        user_id="ada",
    )

    save_registration(host, registration)

    assert public_key_text(load_or_create_key(host)) == first
    assert load_registration(host) == registration


@pytest.mark.parametrize(
    "gateway_url",
    ["wss://linked-proxy-gateway.gumloop.com/v1/cli/connect", "ws://localhost:8443/v1/cli/connect"],
)
def test_registration_accepts_an_encrypted_or_local_gateway(gateway_url):
    registration = LinkedProxyRegistration(
        linked_proxy_id="dp-1", name="Ada's laptop", gateway_url=gateway_url, public_key="key"
    )

    assert registration.gateway_url == gateway_url


def test_registration_refuses_an_unencrypted_remote_gateway():
    with pytest.raises(ValidationError):
        LinkedProxyRegistration(
            linked_proxy_id="dp-1",
            name="Ada's laptop",
            gateway_url="ws://linked-proxy-gateway.gumloop.com/v1/cli/connect",
            public_key="key",
        )
