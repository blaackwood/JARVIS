import unittest

from core.voice_commands import is_microphone_mute_command, normalize_voice_command


class VoiceMicrophoneCommandTests(unittest.TestCase):
    def test_accepts_requested_portuguese_phrase(self):
        self.assertTrue(is_microphone_mute_command("Jarvis, mutar microfone"))

    def test_accepts_common_portuguese_imperatives(self):
        phrases = (
            "Jarvis, mute o microfone",
            "Jarvis, pode mutar o meu microfone",
            "Járvis, silencia o microfone!",
            "Hey Jarvis, desligue o microfone",
            "Jarvis, coloque o microfone no mudo",
            "Jarvis, microfone no mudo",
            "Jarvis, desative o mic",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(is_microphone_mute_command(phrase))

    def test_accepts_english_equivalents(self):
        self.assertTrue(is_microphone_mute_command("Jarvis, mute the microphone"))
        self.assertTrue(is_microphone_mute_command("Hey Jarvis, turn off mic"))

    def test_rejects_ordinary_or_ambiguous_conversation(self):
        phrases = (
            "Como faço para mutar o microfone?",
            "Eu quero mutar o microfone",
            "Jarvis, não mutar o microfone",
            "Jarvis, como mutar o microfone?",
            "Mutar microfone",
            "Jarvis, mutar o microfone depois",
            "Jarvis, mutar o áudio",
            "",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertFalse(is_microphone_mute_command(phrase))

    def test_normalization_removes_accents_and_punctuation(self):
        self.assertEqual(normalize_voice_command("Járvis, MUTAR microfone!"),
                         "jarvis mutar microfone")

    def test_accepts_incremental_transcript_chunks(self):
        from main import _append_transcript_chunk

        received = ["Jarvis"]
        candidate = list(received)
        _append_transcript_chunk("mutar microfone", candidate)
        self.assertTrue(is_microphone_mute_command(" ".join(candidate)))

    def test_accepts_cumulative_transcript_snapshots(self):
        from main import _append_transcript_chunk

        received = ["Jarvis"]
        candidate = list(received)
        _append_transcript_chunk("Jarvis mutar microfone", candidate)
        self.assertTrue(is_microphone_mute_command(" ".join(candidate)))


if __name__ == "__main__":
    unittest.main()
