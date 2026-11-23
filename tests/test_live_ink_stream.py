import unittest

from core.live_transport import send_realtime_message


class FakeLiveSession:
    def __init__(self):
        self.messages = []

    async def send_realtime_input(self, **kwargs):
        self.messages.append(kwargs)


class LiveInkTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_then_video_then_grounding_then_end_are_ordered(self):
        session = FakeLiveSession()
        await send_realtime_message(
            session, {"kind": "audio", "data": b"\x00\x00", "mime_type": "audio/pcm"}
        )
        await send_realtime_message(
            session, {"kind": "video", "data": b"\x89PNG", "mime_type": "image/png"}
        )
        await send_realtime_message(
            session, {"kind": "text", "text": "[USER PEN GESTURE: circle.]"}
        )
        await send_realtime_message(session, {"kind": "audio_end"})

        self.assertEqual(len(session.messages), 4)
        self.assertIn("audio", session.messages[0])
        self.assertIn("video", session.messages[1])
        self.assertIn("text", session.messages[2])
        self.assertEqual(session.messages[2]["text"], "[USER PEN GESTURE: circle.]")
        self.assertEqual(session.messages[3], {"audio_stream_end": True})
        self.assertEqual(session.messages[1]["video"].mime_type, "image/png")

    async def test_unknown_message_kind_is_rejected(self):
        session = FakeLiveSession()
        with self.assertRaisesRegex(ValueError, "Unsupported realtime"):
            await send_realtime_message(session, {"kind": "control"})

    async def test_ordinary_audio_keeps_pcm_mime_type(self):
        session = FakeLiveSession()
        await send_realtime_message(session, {"data": b"pcm"})
        self.assertEqual(session.messages[0]["audio"].mime_type, "audio/pcm")


if __name__ == "__main__":
    unittest.main()
