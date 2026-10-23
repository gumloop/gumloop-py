from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from gumloop import AsyncGumloop


async def exchange(args: argparse.Namespace) -> None:
    # Optional media dependency; importing the example never opens a device or connection.
    from aiortc import RTCPeerConnection
    from aiortc import RTCSessionDescription
    from aiortc.contrib.media import MediaPlayer
    from aiortc.contrib.media import MediaRecorder

    token = os.environ["GUMLOOP_ACCESS_TOKEN"]
    player = MediaPlayer(str(args.input), format="wav")
    recorder = MediaRecorder(str(args.output), format="wav")
    peer = RTCPeerConnection()
    voice_id: str | None = None
    remote_audio = asyncio.Event()

    @peer.on("track")
    def on_track(track):
        if track.kind == "audio":
            recorder.addTrack(track)
            remote_audio.set()

    # The native Talk peer expects the provider event channel alongside audio.
    events = peer.createDataChannel("oai-events")

    @events.on("message")
    def on_message(message):
        if isinstance(message, str) and '"error"' in message:
            print(message)

    async with AsyncGumloop(access_token=token, stream_base_url=args.stream_base_url) as client:
        try:
            if player.audio is None:
                raise ValueError("The input WAV must contain an audio track.")
            peer.addTrack(player.audio)
            await peer.setLocalDescription(await peer.createOffer())
            if peer.localDescription is None:
                raise RuntimeError("The media peer did not produce an SDP offer.")
            started = await client.voice.start(
                args.agent_id, session_id=args.session_id, offer_sdp=peer.localDescription.sdp
            )
            voice_id = started.voice_session_id
            await peer.setRemoteDescription(RTCSessionDescription(sdp=started.answer_sdp, type="answer"))
            await asyncio.wait_for(remote_audio.wait(), timeout=30)
            await recorder.start()
            await asyncio.sleep(args.seconds)
        finally:
            try:
                if voice_id is not None:
                    await client.voice.end(args.agent_id, voice_id)
            finally:
                try:
                    await recorder.stop()
                finally:
                    if player.audio is not None:
                        player.audio.stop()
                    if player.video is not None:
                        player.video.stop()
                    await peer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a WAV to an enabled agent and record received audio.")
    parser.add_argument(
        "--agent-id", required=True, help="Concrete agent ID; gumball and analytics aliases are unsupported."
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--stream-base-url", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error("--input must be an existing WAV file")
    if args.output.exists() or args.output.is_symlink():
        parser.error("--output must be a new path")
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    asyncio.run(exchange(args))


if __name__ == "__main__":
    main()
