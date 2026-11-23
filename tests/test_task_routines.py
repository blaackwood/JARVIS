import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from core.tasks.engine import TaskEngine


ROOT = Path(__file__).resolve().parents[1]


class TaskRoutineTests(unittest.TestCase):
    def make_engine(self, root):
        return TaskEngine(root, root / "reports", [ROOT / "agents"],
                          autostart=False, log=lambda *_: None)

    def test_daily_routine_persists_and_runs_once_when_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            first = self.make_engine(root)
            routine = first.add_routine("Prepare a daily briefing", "daily", "08:30",
                                        agent="general", minutes=5)
            self.assertGreater(routine["next_run"], time.time())
            second = self.make_engine(root)
            self.assertEqual(second.list_routines()[0]["id"], routine["id"])

            data = second.list_routines()
            data[0]["next_run"] = time.time() - 1
            (root / "routines.json").write_text(json.dumps(data), encoding="utf-8")
            second._dispatch_recurring()
            second._dispatch_recurring()

            matches = [t for t in second.store.all()
                       if t.get("recurrence_id") == routine["id"]]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["origin"], "routine")
            self.assertEqual(matches[0]["status"], "queued")
            self.assertGreater(second.list_routines()[0]["next_run"], time.time())

    def test_weekly_routine_selects_requested_weekday(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.make_engine(Path(tmp) / "tasks")
            weekday = (datetime.now().weekday() + 2) % 7
            routine = engine.add_routine("Weekly review", "weekly", "09:15",
                                         weekday=weekday)
            due = datetime.fromtimestamp(routine["next_run"])
            self.assertEqual(due.weekday(), weekday)
            self.assertEqual(due.strftime("%H:%M"), "09:15")

    def test_invalid_schedule_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.make_engine(Path(tmp) / "tasks")
            with self.assertRaises(ValueError):
                engine.add_routine("Bad time", "daily", "25:90")
            with self.assertRaises(ValueError):
                engine.add_routine("Missing weekday", "weekly", "10:00")

    def test_routine_can_be_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.make_engine(Path(tmp) / "tasks")
            routine = engine.add_routine("Remove me", "daily", "08:30")
            self.assertTrue(engine.remove_routine(routine["id"]))
            self.assertFalse(engine.remove_routine(routine["id"]))
            self.assertEqual(engine.list_routines(), [])


if __name__ == "__main__":
    unittest.main()
