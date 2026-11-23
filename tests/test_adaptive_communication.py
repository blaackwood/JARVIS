import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import memory_manager as mm


PROMPT_PATH = Path(__file__).resolve().parents[1] / "core" / "prompt.txt"


class AdaptiveCommunicationTests(unittest.TestCase):
    def test_prompt_does_not_force_one_global_communication_persona(self):
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        voice = prompt.split("[VOICE]", 1)[1].split("[ACKNOWLEDGE BEFORE A SILENCE]", 1)[0]
        self.assertIn("NOT a fixed persona", voice)
        self.assertIn("balanced level of warmth and detail", voice)
        self.assertIn("Some people enjoy extended conversation", voice)
        self.assertNotIn('address the user as "senhor" by default', voice)

    def test_adaptive_profile_is_saved_and_injected_from_local_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({"preferences": {"communication_style": {
                    "value": "Prefers detailed explanations, examples and a conversational tone."
                }}})
                prompt_memory = mm.format_memory_for_prompt(mm.load_memory())
        self.assertIn("detailed explanations", prompt_memory)
        self.assertIn("conversational tone", prompt_memory)

    def test_two_installations_keep_independent_communication_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "person_a.json"
            second = Path(folder) / "person_b.json"
            with patch.object(mm, "MEMORY_PATH", first):
                mm.update_memory({"preferences": {"communication_style": {
                    "value": "Prefers concise, direct answers."
                }}})
                first_prompt = mm.format_memory_for_prompt(mm.load_memory())
            with patch.object(mm, "MEMORY_PATH", second):
                mm.update_memory({"preferences": {"communication_style": {
                    "value": "Prefers detailed, friendly conversations."
                }}})
                second_prompt = mm.format_memory_for_prompt(mm.load_memory())
        self.assertIn("concise, direct", first_prompt)
        self.assertNotIn("detailed, friendly", first_prompt)
        self.assertIn("detailed, friendly", second_prompt)
        self.assertNotIn("concise, direct", second_prompt)


if __name__ == "__main__":
    unittest.main()
