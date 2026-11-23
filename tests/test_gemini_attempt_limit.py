import unittest
from unittest.mock import MagicMock, patch

from core import gemini


class GeminiAttemptLimitTests(unittest.TestCase):
    def test_max_attempts_stops_after_the_requested_number_of_rungs(self):
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = RuntimeError("temporary outage")
        with (
            patch.object(gemini, "_provider_rungs", return_value=()),
            patch.object(gemini, "api_key", return_value="test-key"),
            patch.object(gemini, "usable_rungs", return_value=["first-model", "second-model"]),
            patch.object(gemini, "client", return_value=fake_client) as client_factory,
        ):
            result = gemini.call(
                "test prompt", tier=gemini.FAST, timeout_ms=10_000, max_attempts=1
            )
        self.assertIsNone(result)
        self.assertEqual(client_factory.call_count, 1)
        self.assertEqual(fake_client.models.generate_content.call_count, 1)

    def test_default_still_walks_the_ladder_for_existing_callers(self):
        fake_client = MagicMock()
        expected = MagicMock()
        fake_client.models.generate_content.side_effect = [
            RuntimeError("first rung unavailable"), expected
        ]
        with (
            patch.object(gemini, "_provider_rungs", return_value=()),
            patch.object(gemini, "api_key", return_value="test-key"),
            patch.object(gemini, "usable_rungs", return_value=["first-model", "second-model"]),
            patch.object(gemini, "client", return_value=fake_client),
        ):
            result = gemini.call("test prompt", tier=gemini.FAST, timeout_ms=10_000)
        self.assertIs(result, expected)
        self.assertEqual(fake_client.models.generate_content.call_count, 2)


class GeminiSpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_speech_returns_only_complete_pcm_in_the_selected_voice(self):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        self.assertTrue(callable(getattr(gemini, "speech_pcm", None)))
        configs = []

        async def receive():
            yield SimpleNamespace(data=b"\x01\x00", server_content=None)
            yield SimpleNamespace(data=b"\x02\x00", server_content=SimpleNamespace(turn_complete=True))

        session = SimpleNamespace(send_client_content=AsyncMock(), receive=receive)

        @asynccontextmanager
        async def connect(**kwargs):
            configs.append(kwargs)
            yield session

        fake = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect), aclose=AsyncMock()))
        with patch.object(gemini, "client", return_value=fake):
            pcm = await gemini.speech_pcm("A onda se propaga.", "Kore")
        self.assertEqual(pcm, b"\x01\x00\x02\x00")
        self.assertEqual(configs[0]["config"].speech_config.voice_config.prebuilt_voice_config.voice_name, "Kore")
        fake.aio.aclose.assert_awaited_once()

    async def test_close_failure_does_not_override_complete_pcm(self):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        async def receive():
            yield SimpleNamespace(data=b"\x01\x00", server_content=SimpleNamespace(turn_complete=True))
        @asynccontextmanager
        async def connect(**kwargs):
            yield SimpleNamespace(send_client_content=AsyncMock(), receive=receive)
        fake = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect),
                               aclose=AsyncMock(side_effect=RuntimeError("close failed"))))
        with patch.object(gemini, "client", return_value=fake):
            self.assertEqual(await gemini.speech_pcm("Uma frase.", "Kore"), b"\x01\x00")

    async def test_incomplete_speech_does_not_become_a_finished_beat(self):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        self.assertTrue(callable(getattr(gemini, "speech_pcm", None)))

        async def receive():
            yield SimpleNamespace(data=b"\x01\x00", server_content=None)

        @asynccontextmanager
        async def connect(**kwargs):
            yield SimpleNamespace(send_client_content=AsyncMock(), receive=receive)

        fake = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect), aclose=AsyncMock()))
        with patch.object(gemini, "client", return_value=fake):
            self.assertIsNone(await gemini.speech_pcm("A onda se propaga.", "Kore"))


if __name__ == "__main__":
    unittest.main()
