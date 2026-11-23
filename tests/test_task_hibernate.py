import tempfile
import time
import unittest
from pathlib import Path

from core.tasks.engine import TaskEngine


ROOT = Path(__file__).resolve().parents[1]


class TaskHibernateTests(unittest.TestCase):
    def make_engine(self, root):
        return TaskEngine(
            root=root,
            reports_dir=root / "reports",
            agents_dirs=[ROOT / "agents"],
            autostart=False,
            log=lambda *_: None,
        )

    def test_hibernate_pauses_queued_and_scheduled_tasks_and_preserves_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            engine = self.make_engine(root)
            queued = engine.start("Queued work", agent="general", minutes=5)
            scheduled = engine.start(
                "Scheduled work", agent="general", minutes=5,
                not_before=time.time() + 3600,
            )

            ok, pending = engine.pause_all(timeout=1.0)
            self.assertTrue(ok)
            self.assertEqual(pending, [])
            self.assertEqual(engine.get(queued["id"])["status"], "paused")
            self.assertEqual(engine.get(scheduled["id"])["status"], "paused")

            # Hibernation stops the scheduler without cancelling parked work.
            engine.shutdown(wait=0, cancel_active=False)
            restarted = self.make_engine(root)
            self.assertEqual(restarted.get(queued["id"])["status"], "paused")
            self.assertEqual(restarted.get(scheduled["id"])["status"], "paused")
            restarted.shutdown(wait=0, cancel_active=True)

    def test_hibernate_waits_for_running_task_checkpoint(self):
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            entered = threading.Event()
            release = threading.Event()

            class FakeTools:
                has_web = False

                def declarations(self):
                    return [{"name": "noop", "parameters": {"type": "OBJECT", "properties": {}}}]

                def execute(self, name, args):
                    return "checkpoint saved"

            def ask(system, turns, declarations):
                entered.set()
                self.assertTrue(release.wait(3), "test did not release model call")
                return {"text": "round finished", "calls": [
                    {"id": "call-1", "name": "noop", "args": {}}
                ]}

            root = Path(tmp) / "tasks"
            engine = TaskEngine(
                root=root,
                reports_dir=root / "reports",
                agents_dirs=[ROOT / "agents"],
                tools_factory=lambda task, profile: FakeTools(),
                ask_fn=ask,
                tick=0.02,
                autostart=True,
                log=lambda *_: None,
            )
            try:
                task = engine.start("Active work", agent="general", minutes=5)
                self.assertTrue(entered.wait(3), "task worker did not start")
                releaser = threading.Thread(
                    target=lambda: (time.sleep(0.15), release.set()),
                    daemon=True,
                )
                releaser.start()
                ok, pending = engine.pause_all(timeout=2.0)
                self.assertTrue(ok)
                self.assertEqual(pending, [])
                self.assertEqual(engine.get(task["id"])["status"], "paused")
                self.assertTrue(engine.store.load_turns(task["id"]))
            finally:
                release.set()
                engine.shutdown(wait=2, cancel_active=True)

    def test_hibernate_does_not_change_terminal_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            engine = self.make_engine(root)
            task = engine.start("Completed work", agent="general", minutes=5)
            engine._finish(task["id"], "done", result="complete")

            ok, pending = engine.pause_all(timeout=1.0)
            self.assertTrue(ok)
            self.assertEqual(pending, [])
            self.assertEqual(engine.get(task["id"])["status"], "done")
            engine.shutdown(wait=0, cancel_active=True)


if __name__ == "__main__":
    unittest.main()
