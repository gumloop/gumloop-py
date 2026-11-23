from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from gumloop.linked_proxy.sign_in import public_key_text
from gumloop.linked_proxy.sign_in import sign_in_token

AUDIENCE = "wss://linked-proxy-gateway.gumloop.com/v1/cli/connect"


def _decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_token_is_signed_by_the_registered_key_for_one_minute_and_carries_the_gateway_token():
    key = Ed25519PrivateKey.generate()
    public_key = Ed25519PublicKey.from_public_bytes(_decode(public_key_text(key)))

    token = sign_in_token(key, linked_proxy_id="dp-1", audience=AUDIENCE, gateway_token="token-1", now=1_800_000_000)
    other = sign_in_token(key, linked_proxy_id="dp-1", audience=AUDIENCE, gateway_token="token-1", now=1_800_000_000)

    header, claims, signature = token.split(".")
    public_key.verify(_decode(signature), f"{header}.{claims}".encode())
    assert json.loads(_decode(header))["alg"] == "EdDSA"
    decoded = json.loads(_decode(claims))
    assert {name: decoded[name] for name in ("sub", "aud", "iat", "exp", "gateway_token")} == {
        "sub": "dp-1",
        "aud": AUDIENCE,
        "iat": 1_800_000_000,
        "exp": 1_800_000_060,
        "gateway_token": "token-1",
    }
    assert decoded["jti"] != json.loads(_decode(other.split(".")[1]))["jti"]
