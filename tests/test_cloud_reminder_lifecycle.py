import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from core.cloud import ToolBox, user_now
from core.routines.engine import RoutineEngine


class CloudReminderLifecycleTests(unittest.TestCase):
    def make_toolbox(self, root):
        engine = RoutineEngine(Path(root) / "routines.json", object(),
                               autostart=False, log=lambda *_: None)
        tasks = SimpleNamespace(agents=lambda: {"general": SimpleNamespace(minutes=15)})
        runtime = SimpleNamespace(routines=engine, tasks=tasks)
        toolbox = object.__new__(ToolBox)
        toolbox.rt = runtime
        return toolbox, engine

    def test_cloud_reminder_keeps_stable_id_and_can_be_completed_and_reopened(self):
        with tempfile.TemporaryDirectory() as tmp:
            toolbox, engine = self.make_toolbox(tmp)
            due = user_now() + timedelta(days=1)
            toolbox._t_schedule({
                "action": "add", "reminder": "Call the dentist",
                "at": due.strftime("%Y-%m-%d %H:%M"), "external_id": "local-reminder-123",
            }, {"chat": 123, "origin": "phone"})
            item = next(r for r in engine.list() if r.get("source") == "cloud")
            meta = item["options"]["jarvis_reminder"]
            self.assertEqual(meta["id"], "local-reminder-123")
            self.assertEqual(meta["cloud_id"], item["id"])
            self.assertEqual(meta["status"], "open")

            toolbox._t_schedule({"action": "complete", "id": "local-reminder-123"}, {"chat": 123})
            completed = engine.get(item["id"])
            self.assertFalse(completed["enabled"])
            self.assertEqual(completed["options"]["jarvis_reminder"]["status"], "done")

            toolbox._t_schedule({"action": "reopen", "id": "local-reminder-123"}, {"chat": 123})
            reopened = engine.get(item["id"])
            self.assertTrue(reopened["enabled"])
            self.assertEqual(reopened["options"]["jarvis_reminder"]["status"], "open")

    def test_add_with_same_external_id_is_idempotent_after_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            toolbox, engine = self.make_toolbox(tmp)
            due = user_now() + timedelta(days=1)
            args = {"action": "add", "reminder": "Pick up medicine",
                    "at": due.strftime("%Y-%m-%d %H:%M"), "external_id": "local-stable-777"}
            toolbox._t_schedule(args, {"chat": 777, "origin": "phone"})
            first = [r for r in engine.list() if r.get("source") == "cloud" and r.get("kind") == "say"]
            toolbox._t_schedule(args, {"chat": 777, "origin": "phone"})
            second = [r for r in engine.list() if r.get("source") == "cloud" and r.get("kind") == "say"]
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            self.assertEqual(first[0]["id"], second[0]["id"])

    def test_cloud_remove_retains_cancelled_reminder_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            toolbox, engine = self.make_toolbox(tmp)
            due = user_now() + timedelta(days=1)
            toolbox._t_schedule({
                "action": "add", "reminder": "Pay the bill",
                "at": due.strftime("%Y-%m-%d %H:%M"),
            }, {"chat": 456, "origin": "phone"})
            item = next(r for r in engine.list() if r.get("source") == "cloud")
            result = toolbox._t_schedule({"action": "remove", "id": item["id"]}, {"chat": 456})
            saved = engine.get(item["id"])
            self.assertIsNotNone(saved)
            self.assertEqual(saved["options"]["jarvis_reminder"]["status"], "cancelled")
            self.assertFalse(saved["enabled"])


if __name__ == "__main__":
    unittest.main()
