import json
import tempfile
import time
import unittest
from pathlib import Path

from core.tasks.engine import TaskEngine


ROOT = Path(__file__).resolve().parents[1]


class TaskAuditTests(unittest.TestCase):
    def test_state_transitions_are_written_to_append_only_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            engine = TaskEngine(root, Path(tmp) / "reports", [ROOT / "agents"],
                                autostart=False, log=lambda *_: None)
            task = engine.start(
                "Audit scheduled work",
                agent="general",
                minutes=2,
                not_before=time.time() + 3600,
            )
            self.assertTrue(engine.pause(task["id"]))

            audit = root / "audit.jsonl"
            rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(rows[0]["task_id"], task["id"])
            self.assertTrue(any(row["event"] == "scheduled" for row in rows))
            self.assertTrue(any(row["event"] == "paused by user" for row in rows))

    def test_audit_excludes_model_text_and_tool_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            engine = TaskEngine(root, Path(tmp) / "reports", [ROOT / "agents"],
                                autostart=False, log=lambda *_: None)
            task = engine.start(
                "Do not leak this query",
                agent="general",
                minutes=2,
                not_before=time.time() + 3600,
            )
            engine._event(task["id"], "tool", "web_search secret-token=abc123")
            engine._event(task["id"], "progress", "private model output")
            raw = (root / "audit.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event":"web_search"', raw)
            self.assertNotIn("secret-token", raw)
            self.assertNotIn("abc123", raw)
            self.assertNotIn("private model output", raw)

    def test_audit_survives_store_recreation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            first = TaskEngine(root, Path(tmp) / "reports", [ROOT / "agents"],
                               autostart=False, log=lambda *_: None)
            task = first.start(
                "Persistent audit",
                agent="general",
                minutes=2,
                not_before=time.time() + 3600,
            )
            before = (root / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            second = TaskEngine(root, Path(tmp) / "reports", [ROOT / "agents"],
                                autostart=False, log=lambda *_: None)
            second.pause(task["id"])
            after = (root / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertGreater(len(after), len(before))
            self.assertEqual(json.loads(after[0])["task_id"], task["id"])


if __name__ == "__main__":
    unittest.main()
