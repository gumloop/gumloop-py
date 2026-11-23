"""The linked proxy gateway's tunnel frames. Each binary WebSocket message is one
frame: a type byte, a big-endian uint32 stream id, then the payload. The
gateway defines the layout; ``tests/linked_proxy/fixtures/frames.json`` is a
byte copy of its fixture."""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass

MAX_DATA_LENGTH = 32 * 1024
# How many bytes each side may send on a new stream before the other grants more.
INITIAL_WINDOW = 256 * 1024
OPEN_FAIL_DIAL = "dial"

_HEADER = struct.Struct(">BI")
_WINDOW = struct.Struct(">I")
_MAX_FRAME_LENGTH = _HEADER.size + MAX_DATA_LENGTH
_MAX_TARGET_LENGTH = 253 + len(":65535")
_MAX_REASON_LENGTH = 32
_MAX_GATEWAY_TOKEN_LENGTH = 1024


class FrameType(enum.IntEnum):
    # The gateway asks for a connection to the "host:port" in the payload. Only the gateway opens streams.
    OPEN = 1
    OPEN_OK = 2
    # The payload is a refusal ("port", "address", "host") or OPEN_FAIL_DIAL.
    OPEN_FAIL = 3
    DATA = 4
    # Ends the stream both ways; the other side sends nothing back.
    CLOSE = 5
    # Lets the other side send as many more bytes as the big-endian uint32 payload.
    WINDOW = 6
    # A fresh gateway token, sent by the CLI only. It is the only frame on stream 0.
    GATEWAY_TOKEN = 7


class ProtocolError(Exception):
    """The gateway sent something the tunnel protocol doesn't allow."""


@dataclass(frozen=True)
class Frame:
    type: FrameType
    stream_id: int
    payload: bytes = b""

    def encode(self) -> bytes:
        return _HEADER.pack(self.type, self.stream_id) + self.payload

    @classmethod
    def decode(cls, data: bytes) -> Frame:
        """Checks the layout only; whether the frame fits its stream is the tunnel's check."""
        if not _HEADER.size <= len(data) <= _MAX_FRAME_LENGTH:
            raise ProtocolError(f"a {len(data)}-byte frame")
        type_byte, stream_id = _HEADER.unpack_from(data)
        payload = data[_HEADER.size :]
        if (stream_id == 0) != (type_byte == FrameType.GATEWAY_TOKEN):
            raise ProtocolError(f"frame type {type_byte} on stream {stream_id}")
        try:
            frame_type = FrameType(type_byte)
        except ValueError:
            raise ProtocolError(f"frame type {type_byte}") from None

        size = len(payload)
        valid = {
            FrameType.OPEN: 0 < size <= _MAX_TARGET_LENGTH,
            FrameType.OPEN_OK: size == 0,
            FrameType.OPEN_FAIL: 0 < size <= _MAX_REASON_LENGTH,
            FrameType.DATA: size > 0,
            FrameType.CLOSE: size == 0,
            FrameType.WINDOW: size == _WINDOW.size and _WINDOW.unpack(payload)[0] > 0,
            FrameType.GATEWAY_TOKEN: 0 < size <= _MAX_GATEWAY_TOKEN_LENGTH,
        }[frame_type]
        if not valid:
            raise ProtocolError(f"frame type {type_byte} with a {size}-byte payload")

        return cls(type=frame_type, stream_id=stream_id, payload=payload)

    @classmethod
    def window(cls, stream_id: int, increment: int) -> Frame:
        return cls(type=FrameType.WINDOW, stream_id=stream_id, payload=_WINDOW.pack(increment))

    @classmethod
    def gateway_token(cls, token: str) -> Frame:
        return cls(type=FrameType.GATEWAY_TOKEN, stream_id=0, payload=token.encode())

    @property
    def window_increment(self) -> int:
        return _WINDOW.unpack(self.payload)[0]
