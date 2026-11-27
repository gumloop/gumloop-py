from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gumloop.linked_proxy.frames import Frame
from gumloop.linked_proxy.frames import FrameType
from gumloop.linked_proxy.frames import ProtocolError

FIXTURE = Path(__file__).parent / "fixtures" / "frames.json"
# The linked proxy gateway pins its own copy of this file by the same hash; change both together.
FIXTURE_SHA256 = "9ee8961d2453640ec7c4ab45c3592262ec66fb2be68bad34373012893d63a6e9"


def _fixture() -> dict[str, list[dict[str, str | int]]]:
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256
    return json.loads(raw)


@pytest.mark.parametrize("case", _fixture()["valid"], ids=lambda case: str(case["name"]))
def test_frames_decode_and_encode_like_the_gateway(case: dict[str, str | int]) -> None:
    encoded = bytes.fromhex(str(case["frame"]))

    frame = Frame.decode(encoded)

    assert frame.type is FrameType(case["type"])
    assert frame.stream_id == case["stream_id"]
    assert frame.payload == bytes.fromhex(str(case["payload"]))
    assert frame.encode() == encoded


@pytest.mark.parametrize("case", _fixture()["invalid"], ids=lambda case: str(case["name"]))
def test_frames_the_gateway_refuses_are_refused(case: dict[str, str | int]) -> None:
    with pytest.raises(ProtocolError):
        Frame.decode(bytes.fromhex(str(case["frame"])))
