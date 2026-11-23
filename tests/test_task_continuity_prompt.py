from pathlib import Path
import unittest


class TaskContinuityPromptTests(unittest.TestCase):
    def test_clear_bounded_requests_must_run_to_their_endpoint(self):
        prompt = (Path(__file__).resolve().parents[1] / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("[TASK COMPLETION AND CONTINUITY]", prompt)
        self.assertIn("complete the entire requested scope in one continuous attempt", prompt)
        self.assertIn('Do not ask "shall I continue?"', prompt)
        self.assertIn("until the explicit endpoint is reached", prompt)

    def test_long_spoken_responses_must_not_insert_confirmation_pauses(self):
        prompt = (Path(__file__).resolve().parents[1] / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("For long spoken responses, keep the delivery flowing", prompt)
        self.assertIn("do not insert conversational confirmation pauses between chunks", prompt)


if __name__ == "__main__":
    unittest.main()
