import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import memory_manager as mm


class MemoryContinuityTests(unittest.TestCase):
    def test_recent_session_context_is_in_prompt(self):
        memory = {
            "identity": {"name": {"value": "Gabriel"}},
            "sessions": [
                {"date": "2026-11-12", "summary": "O projeto Lerum recebeu uma atualização."},
                {"date": "2026-11-13", "summary": "O Jarvis teve a busca de notícias corrigida."},
            ],
        }
        prompt = mm.format_memory_for_prompt(memory)
        self.assertIn("RECENT SESSION CONTEXT", prompt)
        self.assertIn("O Jarvis teve a busca de notícias corrigida.", prompt)
        self.assertIn("historical", prompt)

    def test_session_summaries_can_be_recalled_by_keyword(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            path.write_text(json.dumps({
                "identity": {}, "preferences": {}, "projects": {},
                "relationships": {}, "wishes": {}, "notes": {},
                "sessions": [
                    {"date": "2026-11-13", "summary": "O projeto Jarvis recebeu melhorias na memória."}
                ],
            }, ensure_ascii=False), encoding="utf-8")
            with patch.object(mm, "MEMORY_PATH", path):
                result = mm.search_memory("memória")
        self.assertIn("sessions/2026-11-13", result)
        self.assertIn("melhorias na memória", result)

    def test_empty_session_list_does_not_break_prompt(self):
        prompt = mm.format_memory_for_prompt({"identity": {}, "sessions": []})
        self.assertEqual(prompt, "")

    def test_briefing_marks_session_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            path.write_text(json.dumps({
                "identity": {}, "preferences": {}, "projects": {},
                "relationships": {}, "wishes": {}, "notes": {},
                "sessions": [{"date": "2026-11-13", "summary": "Resumo persistente."}],
            }, ensure_ascii=False), encoding="utf-8")
            with patch.object(mm, "MEMORY_PATH", path):
                first = mm.get_last_session_for_briefing()
                stored = json.loads(path.read_text(encoding="utf-8"))
                second = mm.get_last_session_for_briefing()
        self.assertEqual(first["summary"], "Resumo persistente.")
        self.assertEqual(len(stored["sessions"]), 1)
        self.assertTrue(stored["sessions"][0].get("briefed_at"))
        self.assertIsNone(second)

    def test_session_context_is_bounded_to_recent_entries(self):
        memory = {"identity": {}, "sessions": [
            {"date": f"2026-11-{day:02d}", "summary": f"Resumo {day}"}
            for day in range(1, 7)
        ]}
        prompt = mm.format_memory_for_prompt(memory)
        self.assertNotIn("Resumo 1", prompt)
        self.assertIn("Resumo 4", prompt)
        self.assertIn("Resumo 6", prompt)

    def test_sensitive_credential_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                with self.assertRaises(ValueError):
                    mm.update_memory({"notes": {"api_key": {"value": "AIza" + "A" * 30}}})
                self.assertFalse(path.exists())

    def test_unsupported_category_is_rejected_without_partial_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                with self.assertRaises(ValueError):
                    mm.update_memory({
                        "preferences": {"favorite_color": {"value": "azul"}},
                        "secrets": {"credential": {"value": "do not store"}},
                    })
                self.assertFalse(path.exists())

    def test_invalid_key_and_oversized_value_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                with self.assertRaises(ValueError):
                    mm.update_memory({"notes": {"../outside": {"value": "x"}}})
                with self.assertRaises(ValueError):
                    mm.update_memory({"notes": {"oversized": {"value": "x" * 381}}})
                self.assertFalse(path.exists())

    def test_old_memory_gets_sessions_as_list(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            path.write_text('{"identity": {}}', encoding="utf-8")
            with patch.object(mm, "MEMORY_PATH", path):
                memory = mm.load_memory()
        self.assertEqual(memory["sessions"], [])

    def test_forget_session_removes_only_requested_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            path.write_text(json.dumps({
                "identity": {}, "preferences": {}, "projects": {},
                "relationships": {}, "wishes": {}, "notes": {},
                "sessions": [
                    {"id": "2026-11-12T10:00:00.000001", "date": "2026-11-12", "summary": "Antigo"},
                    {"id": "2026-11-13T10:00:00.000001", "date": "2026-11-13", "summary": "Atual"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            with patch.object(mm, "MEMORY_PATH", path):
                result = mm.forget("2026-11-12T10:00:00.000001", "sessions")
                remaining = mm.load_memory()["sessions"]
        self.assertEqual(result, "Forgotten: sessions/2026-11-12T10:00:00.000001")
        self.assertEqual([x["summary"] for x in remaining], ["Atual"])

    def test_session_history_retains_more_than_three_entries(self):
        self.assertEqual(mm._SESSION_MAX, 100)

    def test_same_day_session_deletion_requires_unique_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            path.write_text(json.dumps({
                "identity": {}, "preferences": {}, "projects": {},
                "relationships": {}, "wishes": {}, "notes": {},
                "sessions": [
                    {"date": "2026-11-13", "summary": "Primeiro"},
                    {"date": "2026-11-13", "summary": "Segundo"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            with patch.object(mm, "MEMORY_PATH", path):
                result = mm.forget("2026-11-13", "sessions")
                remaining = mm.load_memory()["sessions"]
        self.assertIn("Multiple summaries", result)
        self.assertEqual(len(remaining), 2)

    def test_same_fact_is_not_saved_under_a_second_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({"preferences": {"favorite_food": {"value": "Pizza"}}})
                result = mm.save_memory_item("notes", "food_choice", "pizza")
                memory = mm.load_memory()
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["match"], "preferences/favorite_food")
        self.assertNotIn("food_choice", memory["notes"])

    def test_existing_key_conflict_is_not_overwritten_without_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({"identity": {"city": {"value": "Piedade"}}})
                result = mm.save_memory_item("identity", "city", "Hortolândia")
                value = mm.load_memory()["identity"]["city"]["value"]
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(value, "Piedade")

    def test_explicit_approval_replaces_only_the_conflicting_fact(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({
                    "identity": {"city": {"value": "Piedade"}},
                    "preferences": {"favorite_food": {"value": "Pizza"}},
                })
                result = mm.save_memory_item(
                    "identity", "city", "Hortolândia", confirm_overwrite=True
                )
                memory = mm.load_memory()
        self.assertEqual(result["status"], "saved")
        self.assertEqual(memory["identity"]["city"]["value"], "Hortolândia")
        self.assertEqual(memory["preferences"]["favorite_food"]["value"], "Pizza")

    def test_near_duplicate_is_flagged_but_not_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            first = "Prefere estudar matemática pela manhã todos os dias"
            second = "Prefere estudar matematica pela manha todos os dias"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({"preferences": {"study_routine": {"value": first}}})
                result = mm.save_memory_item("notes", "routine_note", second)
                memory = mm.load_memory()
        self.assertEqual(result["status"], "possible_duplicate")
        self.assertNotIn("routine_note", memory["notes"])

    def test_duplicate_can_be_saved_separately_only_after_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long_term.json"
            with patch.object(mm, "MEMORY_PATH", path):
                mm.update_memory({"preferences": {"favorite_food": {"value": "Pizza"}}})
                result = mm.save_memory_item(
                    "notes", "food_choice", "pizza", confirm_duplicate=True
                )
                memory = mm.load_memory()
        self.assertEqual(result["status"], "saved")
        self.assertEqual(memory["notes"]["food_choice"]["value"], "pizza")


if __name__ == "__main__":
    unittest.main()
