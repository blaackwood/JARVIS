import json
import tempfile
import time
import unittest
from pathlib import Path

from core.tasks.engine import MAX_ATTEMPTS, TaskEngine
from core.tasks.store import TaskStore


ROOT = Path(__file__).resolve().parents[1]


class CrashRecoveryTests(unittest.TestCase):
    def test_task_file_recovers_from_valid_staged_temp_when_target_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = {"id": "t-recover-1", "status": "running", "title": "Recover"}
            (root / "t-recover-1.json.tmp").write_text(
                json.dumps(task), encoding="utf-8"
            )
            store = TaskStore(root)
            self.assertEqual(store.get(task["id"]), task)
            self.assertTrue((root / "t-recover-1.json").exists())
            self.assertFalse((root / "t-recover-1.json.tmp").exists())

    def test_corrupt_task_file_uses_valid_staged_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = {"id": "t-recover-2", "status": "queued", "title": "Staged"}
            (root / "t-recover-2.json").write_text("{broken", encoding="utf-8")
            (root / "t-recover-2.json.tmp").write_text(
                json.dumps(task), encoding="utf-8"
            )
            store = TaskStore(root)
            self.assertEqual(store.get(task["id"]), task)
            self.assertEqual(json.loads((root / "t-recover-2.json").read_text()), task)

    def test_valid_published_task_wins_over_stale_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = {"id": "t-recover-3", "status": "paused"}
            stale = {"id": "t-recover-3", "status": "running"}
            (root / "t-recover-3.json").write_text(json.dumps(current), encoding="utf-8")
            (root / "t-recover-3.json.tmp").write_text(json.dumps(stale), encoding="utf-8")
            store = TaskStore(root)
            self.assertEqual(store.get(current["id"]), current)
            self.assertFalse((root / "t-recover-3.json.tmp").exists())

    def test_checkpoint_recovers_from_valid_staged_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = TaskStore(root)
            turns = [{"role": "user", "text": "saved checkpoint"}]
            (root / "t-checkpoint.turns.json.tmp").write_text(
                json.dumps(turns), encoding="utf-8"
            )
            self.assertEqual(store.load_turns("t-checkpoint"), turns)
            self.assertTrue((root / "t-checkpoint.turns.json").exists())

    def test_running_task_recovers_from_last_saved_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            first = TaskEngine(root, root / "reports", [ROOT / "agents"],
                               autostart=False, log=lambda *_: None)
            task = first.start("Recover a running task", agent="general", minutes=5)
            saved = [{"role": "user", "text": "last durable round"}]
            first.store.save_turns(task["id"], saved)
            first.store.update(task["id"], status="running", attempts=0)

            restarted = TaskEngine(root, root / "reports", [ROOT / "agents"],
                                   autostart=False, log=lambda *_: None)
            recovered = restarted.get(task["id"])
            self.assertEqual(recovered["status"], "queued")
            self.assertEqual(recovered["attempts"], 1)
            self.assertEqual(restarted.store.load_turns(task["id"]), saved)
            self.assertTrue(any(
                "resuming after an interruption" in event.get("text", "")
                for event in recovered.get("events", [])
            ))

    def test_repeated_crash_limit_fails_instead_of_retrying_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            first = TaskEngine(root, root / "reports", [ROOT / "agents"],
                               autostart=False, log=lambda *_: None)
            task = first.start("Repeated crash", agent="general", minutes=5)
            first.store.update(task["id"], status="running", attempts=MAX_ATTEMPTS)

            restarted = TaskEngine(root, root / "reports", [ROOT / "agents"],
                                   autostart=False, log=lambda *_: None)
            recovered = restarted.get(task["id"])
            self.assertEqual(recovered["status"], "failed")
            self.assertIn("interrupted", recovered.get("error", ""))


if __name__ == "__main__":
    unittest.main()
