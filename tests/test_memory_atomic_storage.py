import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import memory_manager as mm


class MemoryAtomicStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "long_term.json"
        self.patch = patch.object(mm, "MEMORY_PATH", self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def _fact(self, value):
        return {
            "identity": {"name": {"value": value}},
            "preferences": {}, "projects": {}, "relationships": {},
            "wishes": {}, "notes": {}, "sessions": [],
        }

    def test_each_save_keeps_the_previous_valid_memory_as_backup(self):
        first = self._fact("First")
        second = self._fact("Second")
        mm.save_memory(first)
        mm.save_memory(second)

        backup = self.path.with_suffix(".json.bak")
        self.assertTrue(backup.exists())
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["identity"]["name"]["value"], "First")
        self.assertEqual(mm.load_memory()["identity"]["name"]["value"], "Second")

    def test_corrupt_primary_is_restored_from_last_good_backup(self):
        mm.save_memory(self._fact("First"))
        mm.save_memory(self._fact("Second"))
        self.path.write_text("{ truncated json", encoding="utf-8")

        recovered = mm.load_memory()

        self.assertEqual(recovered["identity"]["name"]["value"], "First")
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["identity"]["name"]["value"],
            "First",
        )

    def test_failed_atomic_replace_keeps_the_previous_primary_intact(self):
        mm.save_memory(self._fact("Stable"))
        with patch.object(mm.os, "replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(OSError):
                mm.save_memory(self._fact("Uncommitted"))

        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["identity"]["name"]["value"],
            "Stable",
        )
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_missing_primary_is_restored_from_backup(self):
        mm.save_memory(self._fact("First"))
        mm.save_memory(self._fact("Second"))
        self.path.unlink()

        recovered = mm.load_memory()

        self.assertEqual(recovered["identity"]["name"]["value"], "First")
        self.assertTrue(self.path.exists())

    def test_briefing_updates_also_rotate_atomic_backup(self):
        mm.save_memory(self._fact("Before briefing"))
        mm.save_session_summary("A session summary.")
        result = mm.get_last_session_for_briefing()
        backup = self.path.with_suffix(".json.bak")

        self.assertTrue(backup.exists())
        previous_session = json.loads(backup.read_text(encoding="utf-8"))["sessions"][0]
        self.assertEqual(previous_session["summary"], "A session summary.")
        self.assertNotIn("briefed_at", previous_session)
        self.assertEqual(result["summary"], "A session summary.")
        self.assertTrue(result.get("briefed_at"))
        self.assertTrue(mm.load_memory()["sessions"][0].get("briefed_at"))


if __name__ == "__main__":
    unittest.main()
