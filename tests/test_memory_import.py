import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import memory_manager as mm


class MemoryImportTests(unittest.TestCase):
    def test_import_saves_searchable_memory_without_overwriting_existing_facts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({"preferences": {"tone": {"value": "formal"}}})
                result = mm.import_memory_text(
                    "My background",
                    "I am learning Python and building a personal assistant. "
                    "I prefer clear explanations and practical examples."
                )
                memory = mm.load_memory()
                found = mm.search_memory("building a personal assistant")
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["entries"], 1)
        self.assertEqual(memory["preferences"]["tone"]["value"], "formal")
        self.assertIn("building a personal assistant", found)
        self.assertIn("[My background]", found)

    def test_long_import_is_split_into_retrievable_chunks(self):
        text = " ".join(f"fact{i}" for i in range(900))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                result = mm.import_memory_text("Long context", text)
                memory = mm.load_memory()
        self.assertGreater(result["entries"], 1)
        imported = [v["value"] for k, v in memory["notes"].items()
                    if k.startswith("imported_long_context_")]
        self.assertEqual(len(imported), result["entries"])
        self.assertTrue(all(len(v) <= mm.MAX_VALUE_LENGTH for v in imported))

    def test_repeated_import_uses_new_keys_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.import_memory_text("Study", "Remember my study plan.")
                mm.import_memory_text("Study", "Remember another study plan.")
                memory = mm.load_memory()
        self.assertEqual(len(memory["notes"]), 2)

    def test_import_rejects_empty_or_oversized_content_without_partial_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                with self.assertRaises(ValueError):
                    mm.import_memory_text("Empty", "   ")
                with self.assertRaises(ValueError):
                    mm.import_memory_text("Too large", "x" * 12001)
                self.assertFalse(path.exists())

    def test_import_rejects_credential_like_content(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                with self.assertRaises(ValueError):
                    mm.import_memory_text("Secrets", "My API key: " + "x" * 40)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
