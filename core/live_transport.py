"""Ordered outbound messages for Gemini Live: audio, pen-crop image, text and turn end."""
from __future__ import annotations


async def send_realtime_message(session, message: dict) -> None:
    """Send one outbound queue item, preserving the caller's queue order."""
    from google.genai import types

    kind = str(message.get("kind") or "audio")
    if kind == "video":
        await session.send_realtime_input(
            video=types.Blob(
                data=message["data"],
                mime_type=message.get("mime_type", "image/png"),
            )
        )
    elif kind == "text":
        await session.send_realtime_input(text=str(message.get("text") or ""))
    elif kind == "audio_end":
        await session.send_realtime_input(audio_stream_end=True)
    elif kind == "audio":
        await session.send_realtime_input(
            audio=types.Blob(
                data=message["data"],
                mime_type=message.get("mime_type", "audio/pcm"),
            )
        )
    else:
        raise ValueError(f"Unsupported realtime queue message kind: {kind}")
