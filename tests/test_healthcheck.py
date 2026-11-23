import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from core.healthcheck import collect_health, format_health


class HealthcheckTests(unittest.TestCase):
    def _install(self, root: Path):
        (root / "config").mkdir(parents=True)
        (root / "memory").mkdir()
        (root / "memory" / "tasks").mkdir()
        (root / "agents").mkdir()
        (root / "plugins").mkdir()
        (root / "config" / "api_keys.json").write_text(
            json.dumps({"providers": {"mode": "gemini", "coding": "openai_compat@omniroute"},
                        "api_key": "DO_NOT_PRINT_THIS"}),
            encoding="utf-8",
        )
        (root / "memory" / "long_term.json").write_text(
            json.dumps({"preferences": {"language": {"value": "pt-BR"}}}), encoding="utf-8")
        (root / "memory" / "long_term.json.bak").write_text("{}", encoding="utf-8")
        db = sqlite3.connect(root / "memory" / "semantic_index.sqlite3")
        db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        db.close()
        profiles = {
            "general": "general", "researcher": "researcher",
            "document_analyst": "document_analyst", "study_coach": "study_coach",
            "quality_reviewer": "quality_reviewer",
        }
        for name in profiles:
            (root / "agents" / f"{name}.md").write_text(
                f"---\nname: {name}\ntools: notes\n---\nDo the assigned work safely.\n",
                encoding="utf-8",
            )
        (root / "plugins" / "exam_lab.py").write_text("# local review plugin\n", encoding="utf-8")
        (root / "memory" / "tasks" / "task-1.json").write_text(
            json.dumps({"id": "task-1", "status": "paused"}), encoding="utf-8")

    def test_healthy_local_install_has_expected_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            by_name = {c["name"]: c for c in snap["checks"]}
            self.assertEqual(by_name["config"]["status"], "ok")
            self.assertEqual(by_name["memory"]["status"], "ok")
            self.assertEqual(by_name["semantic_index"]["status"], "ok")
            self.assertEqual(by_name["agents"]["status"], "ok")
            self.assertEqual(by_name["tasks"]["status"], "ok")
            self.assertEqual(snap["task_data"]["by_status"], {"paused": 1})
            self.assertNotEqual(snap["overall"], "critical")

    def test_exam_lab_health_is_cloud_only_and_does_not_require_ollama(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            from core.healthcheck import _check_local_services
            cfg = {"providers": {"coding": "openai_compat@nvidia"}}
            with patch("core.healthcheck._probe_json",
                       side_effect=AssertionError("no local model should be probed")):
                checks = _check_local_services(cfg, root, enabled=True)
            by_name = {item["name"]: item for item in checks}
            self.assertIn("exam_cloud", by_name)
            self.assertEqual(by_name["exam_cloud"]["status"], "info")
            self.assertNotIn("ollama", by_name)
            self.assertIn("nenhum serviço Ollama local", by_name["exam_cloud"]["detail"])

    def test_invalid_task_json_is_reported_without_exposing_task_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            (root / "memory" / "tasks" / "broken.json").write_text("{", encoding="utf-8")
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            item = next(c for c in snap["checks"] if c["name"] == "tasks")
            self.assertEqual(item["status"], "warning")
            self.assertIn("inválido", item["detail"])
            report = format_health(snap)
            self.assertNotIn("DO_NOT_PRINT_THIS", report)
            self.assertNotIn("pt-BR", report)

    def test_corrupt_memory_detects_valid_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            (root / "memory" / "long_term.json").write_text("{", encoding="utf-8")
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            item = next(c for c in snap["checks"] if c["name"] == "memory")
            self.assertEqual(item["status"], "warning")
            self.assertIn("cópia .bak válida", item["detail"])

    def test_missing_required_agent_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            (root / "agents" / "quality_reviewer.md").unlink()
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            item = next(c for c in snap["checks"] if c["name"] == "agents")
            self.assertEqual(item["status"], "warning")
            self.assertIn("quality_reviewer", item["detail"])

    def test_staged_checkpoint_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            (root / "memory" / "tasks" / "pending.tmp").write_text("partial", encoding="utf-8")
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            item = next(c for c in snap["checks"] if c["name"] == "tasks")
            self.assertEqual(item["status"], "warning")
            self.assertIn("temporário", item["detail"])

    def test_corrupt_and_orphan_checkpoints_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            tasks = root / "memory" / "tasks"
            (tasks / "task-1.sq1.turns.json").write_text("{", encoding="utf-8")
            (tasks / "orphan.sq1.turns.json").write_text("[]", encoding="utf-8")
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            item = next(c for c in snap["checks"] if c["name"] == "tasks")
            self.assertEqual(item["status"], "warning")
            self.assertIn("checkpoint(s) inválido(s)", item["detail"])
            self.assertIn("sem tarefa correspondente", item["detail"])
            self.assertEqual(snap["task_data"]["invalid_checkpoints"], 1)
            self.assertEqual(snap["task_data"]["orphan_checkpoints"], 1)

    def test_audit_log_integrity_is_checked_without_exposing_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install(root)
            audit = root / "memory" / "tasks" / "audit.jsonl"
            audit.write_text(
                '{"t":1,"task_id":"private-task","kind":"state","event":"queued"}\n'
                '{"broken":\n',
                encoding="utf-8",
            )
            snap = collect_health(root, platform_name="Linux",
                                  probe_services=False, include_runtime=False)
            item = next(c for c in snap["checks"] if c["name"] == "tasks")
            report = format_health(snap)
            self.assertEqual(item["status"], "warning")
            self.assertEqual(snap["task_data"]["audit_rows"], 1)
            self.assertEqual(snap["task_data"]["invalid_audit_rows"], 1)
            self.assertNotIn("private-task", report)
            self.assertNotIn("queued", report)


if __name__ == "__main__":
    unittest.main()
