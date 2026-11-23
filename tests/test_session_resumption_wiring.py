from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")


class SessionResumptionWiringTests(unittest.TestCase):
    def test_live_config_passes_the_last_resumable_handle(self):
        self.assertRegex(
            SOURCE,
            r"session_resumption\s*=\s*types\.SessionResumptionConfig\(\s*handle=self\._resume_handle\s*\)",
        )

    def test_only_resumable_server_updates_replace_the_handle(self):
        start = SOURCE.index("_sru = getattr(response, \"session_resumption_update\"")
        block = SOURCE[start:start + 700]
        self.assertIn('getattr(_sru, "resumable", False)', block)
        self.assertIn('getattr(_sru, "new_handle", None)', block)
        self.assertIn("self._resume_handle = _sru.new_handle", block)

    def test_rejected_or_expired_handle_is_cleared_before_retry(self):
        start = SOURCE.index("if _resumed_with and (")
        block = SOURCE[start:start + 900]
        self.assertIn('"resum" in str(e).lower()', block)
        self.assertIn("self._resume_handle = None", block)
        self.assertIn("continue", block)

    def test_fresh_processes_inject_recent_archived_dialogue(self):
        self.assertIn(
            'history_str = (\n            "" if self._resume_handle else _format_recent_history(8)',
            SOURCE,
        )
        self.assertIn("if history_str:", SOURCE)
        self.assertIn("parts.append(history_str)", SOURCE)


if __name__ == "__main__":
    unittest.main()
