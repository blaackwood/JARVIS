import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import conversation_history as history


class ConversationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "history.jsonl"
        self.patch = patch.object(history, "_ARCHIVE", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_append_and_retrieve_across_sessions(self):
        self.assertTrue(history.append_message("s1", "user", "Open my project"))
        self.assertTrue(history.append_message("s1", "assistant", "Opening it"))
        self.assertTrue(history.append_message("s2", "user", "Continue the project"))
        rows = history.recent_messages(3)
        self.assertEqual([r["session_id"] for r in rows], ["s1", "s1", "s2"])
        self.assertEqual(rows[-1]["text"], "Continue the project")

    def test_search_finds_older_conversation(self):
        history.append_message("old", "user", "We decided to use persistent checkpoints")
        history.append_message("new", "user", "Hello")
        hits = history.search_messages("persistent checkpoints")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["session_id"], "old")

    def test_credentials_are_redacted(self):
        history.append_message("s", "user", "api_key=ABC123 password:hello")
        text = history.recent_messages(1)[0]["text"]
        self.assertNotIn("ABC123", text)
        self.assertNotIn("hello", text)
        self.assertIn("[REDACTED]", text)

    def test_context_includes_previous_sessions_for_a_fresh_connection(self):
        history.append_message("old-session", "user", "We chose the second monitor")
        history.append_message("new-session", "user", "Continue")
        context = history.format_recent_context(8)
        self.assertIn("We chose the second monitor", context)
        self.assertIn("Continue", context)

    def test_context_is_chronological(self):
        history.append_message("s1", "user", "First")
        history.append_message("s1", "assistant", "Second")
        context = history.format_recent_context(2)
        self.assertLess(context.index("First"), context.index("Second"))

    def test_search_skips_json_values_that_are_not_objects(self):
        self.path.write_text(
            '[1, 2]\n"plain string"\nnull\n42\ntrue\nfalse\n'
            '{"speaker":"user","text":"keep this matching phrase","session_id":"s"}\n',
            encoding="utf-8",
        )
        hits = history.search_messages("KEEP this matching phrase")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["text"], "keep this matching phrase")

    def test_search_skips_malformed_json_and_continues(self):
        self.path.write_text(
            '{"speaker":\n'
            '{"speaker":"assistant","text":"valid result after broken line"}\n',
            encoding="utf-8",
        )
        hits = history.search_messages("valid result")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["speaker"], "assistant")

    def test_search_preserves_limit_with_non_object_records(self):
        self.path.write_text(
            '[]\n'
            '{"speaker":"user","text":"same phrase one"}\n'
            'null\n'
            '{"speaker":"assistant","text":"same phrase two"}\n'
            '17\n'
            '{"speaker":"user","text":"same phrase three"}\n',
            encoding="utf-8",
        )
        hits = history.search_messages("same phrase", limit=2)
        self.assertEqual(
            [row["text"] for row in hits],
            ["same phrase two", "same phrase three"],
        )

    def test_recent_messages_and_search_both_ignore_non_object_records(self):
        self.path.write_text(
            'null\n'
            '{"speaker":"user","text":"normal conversation","session_id":"s"}\n'
            '["bad", "record"]\n',
            encoding="utf-8",
        )
        self.assertEqual(len(history.recent_messages()), 1)
        self.assertEqual(len(history.search_messages("normal conversation")), 1)


if __name__ == "__main__":
    unittest.main()
