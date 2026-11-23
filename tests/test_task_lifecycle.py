import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.tasks.engine import TaskEngine


ROOT = Path(__file__).resolve().parents[1]


class TaskLifecycleTests(unittest.TestCase):
    def make_engine(self, root):
        return TaskEngine(
            root=root,
            reports_dir=root / "reports",
            agents_dirs=[ROOT / "agents"],
            autostart=False,
            log=lambda *_: None,
        )

    def test_scheduled_task_can_be_paused_and_resumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            engine = self.make_engine(root)
            task = engine.start(
                "Research a subject",
                agent="researcher",
                minutes=5,
                not_before=time.time() + 3600,
            )

            self.assertEqual(task["status"], "scheduled")
            self.assertTrue(engine.pause(task["id"]))
            self.assertEqual(engine.get(task["id"])["status"], "paused")
            self.assertFalse(engine.pause(task["id"]))

            self.assertTrue(engine.resume(task["id"]))
            resumed = engine.get(task["id"])
            self.assertEqual(resumed["status"], "queued")
            self.assertEqual(resumed["not_before"], 0.0)
            self.assertFalse(engine.resume(task["id"]))

    def test_paused_state_survives_engine_recreation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            first = self.make_engine(root)
            task = first.start(
                "Continue later",
                agent="general",
                minutes=5,
                not_before=time.time() + 3600,
            )
            self.assertTrue(first.pause(task["id"]))

            second = self.make_engine(root)
            self.assertEqual(second.get(task["id"])["status"], "paused")
            self.assertTrue(second.resume(task["id"]))
            self.assertEqual(second.get(task["id"])["status"], "queued")

    def test_paused_task_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.make_engine(Path(tmp) / "tasks")
            task = engine.start(
                "Cancel this later task",
                agent="general",
                minutes=5,
                not_before=time.time() + 3600,
            )
            self.assertTrue(engine.pause(task["id"]))
            self.assertTrue(engine.cancel(task["id"]))
            self.assertEqual(engine.get(task["id"])["status"], "cancelled")
            self.assertFalse(engine.resume(task["id"]))

    def test_interrupted_pausing_task_recovers_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            first = self.make_engine(root)
            task = first.start(
                "Recover interrupted pause",
                agent="general",
                minutes=5,
                not_before=time.time() + 3600,
            )
            first.store.update(task["id"], status="pausing")
            second = self.make_engine(root)
            recovered = second.get(task["id"])
            self.assertEqual(recovered["status"], "queued")
            self.assertEqual(recovered["attempts"], 1)

    def test_cancel_during_pending_pause_overrides_pause(self):
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
                self.assertTrue(release.wait(3), "test did not release the model call")
                return {"text": "first round", "calls": [
                    {"id": "call-1", "name": "noop", "args": {}}
                ]}

            engine = TaskEngine(
                root=Path(tmp) / "tasks",
                reports_dir=Path(tmp) / "reports",
                agents_dirs=[ROOT / "agents"],
                tools_factory=lambda task, profile: FakeTools(),
                ask_fn=ask,
                tick=0.02,
                autostart=True,
                log=lambda *_: None,
            )
            try:
                task = engine.start("Cancel while pause is pending",
                                    agent="general", minutes=5)
                self.assertTrue(entered.wait(3), "task worker did not start")
                self.assertTrue(engine.pause(task["id"]))
                self.assertEqual(engine.get(task["id"])["status"], "pausing")
                self.assertTrue(engine.cancel(task["id"]))
                release.set()

                deadline = time.time() + 3
                while time.time() < deadline and engine.get(task["id"])["status"] != "cancelled":
                    time.sleep(0.02)

                current = engine.get(task["id"])
                self.assertEqual(current["status"], "cancelled")
                self.assertFalse(any("paused at a saved checkpoint" in e["text"]
                                     for e in current.get("events") or []))
            finally:
                release.set()
                engine.shutdown(wait=2)

    def test_running_task_pauses_after_saving_current_round(self):
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
                self.assertTrue(release.wait(3), "test did not release the model call")
                return {"text": "working", "calls": [
                    {"id": "call-1", "name": "noop", "args": {}}
                ]}

            root = Path(tmp) / "tasks"
            engine = TaskEngine(
                root=root,
                reports_dir=Path(tmp) / "reports",
                agents_dirs=[ROOT / "agents"],
                tools_factory=lambda task, profile: FakeTools(),
                ask_fn=ask,
                tick=0.02,
                autostart=True,
                log=lambda *_: None,
            )
            try:
                task = engine.start("Pause during model call", agent="general", minutes=5)
                self.assertTrue(entered.wait(3), "task worker did not start")
                self.assertTrue(engine.pause(task["id"]))
                release.set()

                deadline = time.time() + 3
                while time.time() < deadline:
                    current = engine.get(task["id"])
                    if current["status"] == "paused":
                        break
                    time.sleep(0.02)

                self.assertEqual(engine.get(task["id"])["status"], "paused")
                turns = engine.store.load_turns(task["id"])
                self.assertTrue(any(t.get("role") == "tool" for t in turns))
                self.assertTrue(engine.resume(task["id"]))
            finally:
                release.set()
                engine.shutdown(wait=2)

    def test_resume_during_pause_waits_for_checkpoint_then_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            entered = threading.Event()
            release = threading.Event()
            calls = {"count": 0}

            class FakeTools:
                has_web = False

                def declarations(self):
                    return [{"name": "noop", "parameters": {"type": "OBJECT", "properties": {}}}]

                def execute(self, name, args):
                    return "checkpoint saved"

            def ask(system, turns, declarations):
                calls["count"] += 1
                if calls["count"] == 1:
                    entered.set()
                    self.assertTrue(release.wait(3), "test did not release the model call")
                    return {"text": "first round", "calls": [
                        {"id": "call-1", "name": "noop", "args": {}}
                    ]}
                return {"text": "resumed and completed", "calls": []}

            engine = TaskEngine(
                root=Path(tmp) / "tasks",
                reports_dir=Path(tmp) / "reports",
                agents_dirs=[ROOT / "agents"],
                tools_factory=lambda task, profile: FakeTools(),
                ask_fn=ask,
                tick=0.02,
                autostart=True,
                log=lambda *_: None,
            )
            try:
                task = engine.start("Resume immediately after pause request",
                                    agent="general", minutes=5)
                self.assertTrue(entered.wait(3), "task worker did not start")
                self.assertTrue(engine.pause(task["id"]))
                self.assertEqual(engine.get(task["id"])["status"], "pausing")
                self.assertTrue(engine.resume(task["id"]))
                self.assertTrue(engine.get(task["id"]).get("resume_pending"))
                release.set()

                deadline = time.time() + 3
                while time.time() < deadline:
                    current = engine.get(task["id"])
                    events = current.get("events") or []
                    if any("resumed after pending pause checkpoint" in e["text"] for e in events):
                        break
                    time.sleep(0.02)

                current = engine.get(task["id"])
                events = current.get("events") or []
                self.assertTrue(any("resumed after pending pause checkpoint" in e["text"]
                                    for e in events))
                self.assertFalse(any("paused at a saved checkpoint" in e["text"] for e in events))
                self.assertIn(current["status"], ("queued", "running", "done"))
                self.assertFalse(current.get("resume_pending"))
            finally:
                release.set()
                engine.shutdown(wait=2)

    def test_shutdown_cancels_all_unfinished_states_and_never_recovers_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tasks"
            engine = self.make_engine(root)
            statuses = ["queued", "scheduled", "running", "pausing",
                        "waiting_quota", "paused"]
            tasks = []
            for status in statuses:
                task = engine.start("Shutdown test " + status, agent="general",
                                    minutes=5, not_before=time.time() + 3600)
                engine.store.update(task["id"], status=status)
                tasks.append(task["id"])

            engine.add_routine("Keep my schedule", "daily", "23:59")
            engine.shutdown(wait=0, cancel_active=True)

            for tid in tasks:
                current = engine.get(tid)
                self.assertEqual(current["status"], "cancelled", tid)
                self.assertIn("Jarvis was closed", current.get("cancel_reason", ""))
            self.assertEqual(len(engine.list_routines()), 1)

            restarted = self.make_engine(root)
            for tid in tasks:
                self.assertEqual(restarted.get(tid)["status"], "cancelled", tid)
            with self.assertRaises(RuntimeError):
                engine.start("Must not start after shutdown", agent="general")
            restarted.shutdown(wait=0, cancel_active=True)

    def test_shutdown_cancels_inflight_model_call_without_running_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            entered = threading.Event()
            release = threading.Event()
            executed = []

            class FakeTools:
                has_web = False

                def declarations(self):
                    return [{"name": "dangerous_test_tool",
                             "parameters": {"type": "OBJECT", "properties": {}}}]

                def execute(self, name, args):
                    executed.append(name)
                    return "should not execute"

            def ask(system, turns, declarations):
                entered.set()
                self.assertTrue(release.wait(3), "test did not release model call")
                return {"text": "tool requested", "calls": [
                    {"id": "call-1", "name": "dangerous_test_tool", "args": {}}
                ]}

            engine = TaskEngine(
                root=Path(tmp) / "tasks",
                reports_dir=Path(tmp) / "reports",
                agents_dirs=[ROOT / "agents"],
                tools_factory=lambda task, profile: FakeTools(),
                ask_fn=ask, tick=0.02, autostart=True, log=lambda *_: None,
            )
            try:
                task = engine.start("Close while model is thinking",
                                    agent="general", minutes=5)
                self.assertTrue(entered.wait(3), "task worker did not start")
                engine.shutdown(wait=0, cancel_active=True)
                self.assertEqual(engine.get(task["id"])["status"], "cancelled")
                release.set()

                deadline = time.time() + 3
                while time.time() < deadline and any(
                    th.is_alive() for th in engine._workers.values()
                ):
                    time.sleep(0.02)

                self.assertEqual(executed, [])
                self.assertEqual(engine.get(task["id"])["status"], "cancelled")
            finally:
                release.set()
                engine.shutdown(wait=2, cancel_active=True)

    def test_completed_task_cannot_be_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.make_engine(Path(tmp) / "tasks")
            task = engine.start(
                "Already finished",
                agent="general",
                minutes=5,
                not_before=time.time() + 3600,
            )
            engine.store.update(task["id"], status="done")
            self.assertFalse(engine.pause(task["id"]))


if __name__ == "__main__":
    unittest.main()
