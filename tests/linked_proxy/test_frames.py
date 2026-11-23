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
FIXTURE_SHA256 = "a19bdf1ec020eeab8bbf966c0ee6e4a0eb47748b0d27983ff5b758dcf84489c1"


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
