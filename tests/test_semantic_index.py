import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import semantic_index as si


class SemanticIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.memory = root / "memory"
        self.projects = self.memory / "projects"
        self.tasks = self.memory / "tasks"
        self.projects.mkdir(parents=True)
        self.tasks.mkdir(parents=True)
        self.long_term = self.memory / "long_term.json"
        self.db = self.memory / "semantic_index.sqlite3"
        self.long_term.write_text(json.dumps({
            "identity": {},
            "preferences": {"memory": {"value": "Prefere memória confiável e pesquisa por significado."}},
            "projects": {"jarvis": {"value": "Projeto principal Jarvis."}},
            "relationships": {"Ana": {"value": "Pessoa que participa do projeto Jarvis."}},
            "wishes": {},
            "notes": {},
            "sessions": [{"id": "s1", "date": "2026-11-14", "summary": "Decidiu avançar o projeto Jarvis."}],
        }, ensure_ascii=False), encoding="utf-8")
        (self.projects / "jarvis-main.json").write_text(json.dumps({
            "name": "Jarvis Main",
            "status": "Active",
            "decisions": ["Controlar navegador e desktop."],
            "blockers": [],
            "next_steps": ["Integrar memória semântica."],
            "notes": ["Ana ajudará a testar o assistente."],
        }, ensure_ascii=False), encoding="utf-8")
        (self.tasks / "task-1.json").write_text(json.dumps({
            "id": "task-1",
            "title": "Controlar navegador no Jarvis Main",
            "task": "Testar clique visual e navegação no navegador.",
            "status": "done",
            "result": "Clique confirmado no primeiro vídeo.",
        }, ensure_ascii=False), encoding="utf-8")
        self.patches = [
            patch.object(si, "LONG_TERM_PATH", self.long_term),
            patch.object(si, "PROJECTS_DIR", self.projects),
            patch.object(si, "TASKS_DIR", self.tasks),
            patch.object(si, "DB_PATH", self.db),
        ]
        for p in self.patches:
            p.start()
        si.refresh_semantic_index(force=True)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_diacritic_insensitive_search_finds_durable_facts(self):
        result = si.search_semantic_memory("memoria")
        self.assertIn("[fact]", result)
        self.assertIn("memória", result)

    def test_projects_and_tasks_are_indexed_with_relationships(self):
        result = si.search_semantic_memory("clique visual")
        self.assertIn("[task]", result)
        self.assertIn("Jarvis Main", result)
        self.assertIn("mentions project", result.lower())

    def test_session_summaries_are_indexed_as_events(self):
        result = si.search_semantic_memory("decidiu avançar")
        self.assertIn("[event]", result)

    def test_credential_like_documents_are_excluded(self):
        fake_key = "AIza" + ("1234567890" * 3)  # synthetic test fixture only
        (self.projects / "unsafe.json").write_text(json.dumps({
            "name": "Unsafe Project",
            "notes": ["api_key=" + fake_key],
        }), encoding="utf-8")
        si.refresh_semantic_index(force=True)
        result = si.search_semantic_memory(fake_key)
        self.assertIn("NO_SEMANTIC_MATCHES", result)

    def test_project_mentions_link_to_people(self):
        result = si.search_semantic_memory("ajudará a testar")
        self.assertIn("Ana", result)
        self.assertIn("mentions person", result.lower())

    def test_raw_conversation_turns_are_not_copied_into_semantic_index(self):
        history = self.memory / "conversations" / "history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text(
            '{"speaker":"user","text":"rawchatmarker928374"}\\n',
            encoding="utf-8",
        )
        si.refresh_semantic_index(force=True)
        self.assertIn("NO_SEMANTIC_MATCHES", si.search_semantic_memory("rawchatmarker928374"))

    def test_credential_in_entity_name_is_not_indexed(self):
        fake_key = "AIza" + ("1234567890" * 3)  # synthetic test fixture only
        (self.projects / "unsafe-name.json").write_text(json.dumps({
            "name": "api_key=" + fake_key,
            "notes": ["Ordinary project note"],
        }), encoding="utf-8")
        si.refresh_semantic_index(force=True)
        self.assertIn("NO_SEMANTIC_MATCHES", si.search_semantic_memory(fake_key))

    def test_refresh_is_idempotent_without_source_changes(self):
        first = si.refresh_semantic_index(force=True)
        second = si.refresh_semantic_index()
        self.assertTrue(first["updated"])
        self.assertFalse(second["updated"])
        self.assertEqual(first["documents"], second["documents"])


if __name__ == "__main__":
    unittest.main()
