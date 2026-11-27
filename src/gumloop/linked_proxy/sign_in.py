"""The token the CLI signs in to the linked proxy gateway with: a compact EdDSA JWS
signed by this machine's linked proxy key. The gateway accepts a token only for its
own URL, for at most a minute, and only once."""

from __future__ import annotations

import base64
import json
import secrets
import time
from collections.abc import Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import PublicFormat

TOKEN_LIFETIME_SECONDS = 60


def public_key_text(key: Ed25519PrivateKey) -> str:
    """The raw public key in unpadded base64url, the form the backend registers."""
    return _encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def sign_in_token(
    key: Ed25519PrivateKey, *, linked_proxy_id: str, audience: str, gateway_token: str, now: float | None = None
) -> str:
    """``gateway_token`` is the backend's token for this linked proxy. The
    gateway learns the key to verify the sign-in token with from it."""
    issued_at = int(time.time() if now is None else now)
    header = {"alg": "EdDSA", "typ": "JWT"}
    claims = {
        "sub": linked_proxy_id,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + TOKEN_LIFETIME_SECONDS,
        "jti": secrets.token_urlsafe(16),
        "gateway_token": gateway_token,
    }
    signing_input = f"{_encode_json(header)}.{_encode_json(claims)}"
    return f"{signing_input}.{_encode(key.sign(signing_input.encode()))}"


def _encode_json(value: Mapping[str, str | int]) -> str:
    return _encode(json.dumps(value, separators=(",", ":")).encode())


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
