import unittest
from unittest.mock import patch

from actions import conversation_history


class ConversationHistoryToolTests(unittest.TestCase):
    def test_search_returns_original_user_and_assistant_turns(self):
        rows = [
            {"timestamp": "2026-11-14T08:00:00+00:00", "speaker": "user", "text": "We chose SQLite"},
            {"timestamp": "2026-11-14T08:00:10+00:00", "speaker": "assistant", "text": "I will implement SQLite"},
        ]
        with patch.object(conversation_history, "search_messages", return_value=rows):
            result = conversation_history.search_conversation_history({"query": "SQLite"})
        self.assertIn("User: We chose SQLite", result)
        self.assertIn("JARVIS: I will implement SQLite", result)

    def test_empty_query_is_refused(self):
        result = conversation_history.search_conversation_history({"query": " "})
        self.assertIn("QUERY_REQUIRED", result)

    def test_tool_is_declared_for_dynamic_discovery(self):
        self.assertEqual(conversation_history.TOOL["name"], "search_conversation_history")
        self.assertIn("handler", conversation_history.TOOL)


if __name__ == "__main__":
    unittest.main()
