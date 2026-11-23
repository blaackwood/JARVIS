import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from actions import reminder as reminder_module


class ReminderCreationLifecycleTests(unittest.TestCase):
    def _params(self):
        due = datetime.now() + timedelta(days=2)
        return {"date": due.strftime("%Y-%m-%d"), "time": due.strftime("%H:%M"),
                "message": "Test reminder"}

    def test_failed_os_schedule_does_not_create_companion_reminders(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "notify.py"
            calls = []
            with (patch.object(reminder_module, "_get_os", return_value="windows"),
                  patch.object(reminder_module, "_write_notify_script", return_value=script),
                  patch.object(reminder_module, "_schedule_windows", return_value=""),
                  patch.object(reminder_module, "_mirror_to_cloud", side_effect=lambda *a: calls.append("cloud") or ""),
                  patch.object(reminder_module, "_add_spoken_routine", side_effect=lambda *a: calls.append("spoken") or "")):
                result = reminder_module.reminder(self._params())
            self.assertIn("couldn't register", result)
            self.assertEqual(calls, [])

    def test_companion_reminders_are_created_only_after_os_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "notify.py"
            calls = []
            def scheduled(*args):
                calls.append("os")
                return "JARVISReminder_test"
            with (patch.object(reminder_module, "_get_os", return_value="windows"),
                  patch.object(reminder_module, "_write_notify_script", return_value=script),
                  patch.object(reminder_module, "_schedule_windows", side_effect=scheduled),
                  patch.object(reminder_module, "_mirror_to_cloud", side_effect=lambda *a: calls.append("cloud") or ""),
                  patch.object(reminder_module, "_add_spoken_routine", side_effect=lambda *a: calls.append("spoken") or "")):
                result = reminder_module.reminder(self._params())
            self.assertIn("Reminder set", result)
            self.assertEqual(calls, ["os", "spoken", "cloud"])

    def test_reminder_record_uses_stable_id_inside_existing_routine_store(self):
        from core.routines.engine import RoutineEngine
        from core.routines import desktop
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(),
                                   autostart=False, log=lambda *_: None)
            due = datetime.now() + timedelta(days=2)
            with patch.object(desktop, "engine", return_value=engine):
                item = reminder_module._add_spoken_routine(
                    "Test reminder", due, "abc123stable", "JARVISReminder_abc123stable",
                    Path(tmp) / "JARVISReminder_abc123stable.py", "windows",
                    "schtasks:JARVISReminder_abc123stable",
                )
            self.assertEqual(item["source"], "reminder")
            self.assertEqual(item["options"]["jarvis_reminder"]["id"], "abc123stable")
            self.assertEqual(item["options"]["jarvis_reminder"]["status"], "open")
            self.assertEqual(len(engine.list()), 1)

    def test_one_shot_reminder_is_retained_as_done_after_delivery(self):
        from core.routines.engine import RoutineEngine
        from datetime import timezone
        now = datetime.now().astimezone()
        clock_value = now.timestamp()
        class Host:
            def ready(self): return True
            def idle_seconds(self): return 30
            def say(self, text): self.said = text
            def log(self, text): pass
        with tempfile.TemporaryDirectory() as tmp:
            host = Host()
            engine = RoutineEngine(Path(tmp) / "routines.json", host,
                                   clock=lambda: clock_value, autostart=False,
                                   log=lambda *_: None)
            due = clock_value - 1
            item = engine.add(
                "Test reminder", "say", "Test reminder",
                trigger={"type": "time", "rule": {"type": "once", "at_ts": due}},
                source="reminder", options={"jarvis_reminder": {"id": "abc123", "status": "open"}},
                next_ts=due,
            )
            engine._tick_time(item, clock_value, now, True)
            saved = engine.get(item["id"])
            self.assertIsNotNone(saved)
            self.assertFalse(saved["enabled"])
            self.assertEqual(saved["options"]["jarvis_reminder"]["status"], "done")
            self.assertEqual(saved["runs"], 1)

    def test_complete_refuses_to_change_state_when_os_cancellation_fails(self):
        from core.routines import desktop
        fake = _FakeReminderEngine()
        with (patch.object(desktop, "engine", return_value=fake),
              patch.object(reminder_module, "_cancel_os_schedule", return_value=(False, "still active"))):
            ok, detail = reminder_module.set_reminder_state("abc123", "done")
        self.assertFalse(ok)
        self.assertIn("still active", detail)
        self.assertEqual(fake.item["options"]["jarvis_reminder"]["status"], "open")
        self.assertTrue(fake.item["enabled"])

    def test_complete_cancels_os_before_persisting_done(self):
        from core.routines import desktop
        fake = _FakeReminderEngine()
        calls = []
        def cancel(meta):
            calls.append((meta["id"], fake.item["options"]["jarvis_reminder"]["status"]))
            return True, "cancelled"
        with (patch.object(desktop, "engine", return_value=fake),
              patch.object(reminder_module, "_cancel_os_schedule", side_effect=cancel)):
            ok, detail = reminder_module.set_reminder_state("abc123", "done")
        self.assertTrue(ok)
        self.assertEqual(calls, [("abc123", "open")])
        self.assertEqual(fake.item["options"]["jarvis_reminder"]["status"], "done")
        self.assertFalse(fake.item["enabled"])

    def test_windows_cancel_verifies_task_is_absent_after_delete(self):
        from types import SimpleNamespace
        meta = {"os_name": "windows", "task_name": "JARVISReminder_abc123",
                "scheduler_id": "schtasks:JARVISReminder_abc123", "script_path": ""}
        replies = [
            SimpleNamespace(returncode=0, stdout="task found", stderr=""),
            SimpleNamespace(returncode=0, stdout="SUCCESS: deleted", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="ERROR: The system cannot find the file specified."),
        ]
        with patch.object(reminder_module.subprocess, "run", side_effect=replies) as run, \
             patch.object(reminder_module, "_safe_script_path", return_value=None):
            ok, detail = reminder_module._cancel_os_schedule(meta)
        self.assertTrue(ok, detail)
        self.assertEqual(run.call_count, 3)

    def test_windows_cancel_fails_closed_if_delete_did_not_remove_task(self):
        from types import SimpleNamespace
        meta = {"os_name": "windows", "task_name": "JARVISReminder_abc123",
                "scheduler_id": "schtasks:JARVISReminder_abc123", "script_path": ""}
        replies = [
            SimpleNamespace(returncode=0, stdout="task found", stderr=""),
            SimpleNamespace(returncode=1, stdout="Access denied", stderr=""),
            SimpleNamespace(returncode=0, stdout="task still exists", stderr=""),
        ]
        with patch.object(reminder_module.subprocess, "run", side_effect=replies):
            ok, detail = reminder_module._cancel_os_schedule(meta)
        self.assertFalse(ok)
        self.assertIn("Access denied", detail)

    def test_windows_cancel_does_not_treat_arbitrary_query_error_as_missing(self):
        from types import SimpleNamespace
        meta = {"os_name": "windows", "task_name": "JARVISReminder_abc123",
                "scheduler_id": "schtasks:JARVISReminder_abc123", "script_path": ""}
        with patch.object(reminder_module.subprocess, "run",
                          return_value=SimpleNamespace(returncode=1, stdout="Access denied", stderr="")) as run:
            ok, detail = reminder_module._cancel_os_schedule(meta)
        self.assertFalse(ok)
        self.assertIn("Access denied", detail)
        run.assert_called_once()

    def test_cloud_failure_prevents_local_reminder_completion(self):
        from core.routines import desktop
        fake = _FakeReminderEngine()
        fake.item["options"]["jarvis_reminder"]["cloud_synced"] = True
        with (patch.object(desktop, "engine", return_value=fake),
              patch.object(reminder_module, "_cloud_reminder_state", return_value=(False, "offline")),
              patch.object(reminder_module, "_cancel_os_schedule") as cancel):
            ok, detail = reminder_module.set_reminder_state("abc123", "done")
        self.assertFalse(ok)
        self.assertIn("offline", detail)
        cancel.assert_not_called()
        self.assertTrue(fake.item["enabled"])
        self.assertEqual(fake.item["options"]["jarvis_reminder"]["status"], "open")

    def test_os_cancel_failure_rolls_back_cloud_state_to_open(self):
        from core.routines import desktop
        fake = _FakeReminderEngine()
        fake.item["options"]["jarvis_reminder"]["cloud_synced"] = True
        calls = []
        def cloud_state(_meta, state):
            calls.append(state)
            return True, state
        with (patch.object(desktop, "engine", return_value=fake),
              patch.object(reminder_module, "_cloud_reminder_state", side_effect=cloud_state),
              patch.object(reminder_module, "_cancel_os_schedule", return_value=(False, "still scheduled"))):
            ok, detail = reminder_module.set_reminder_state("abc123", "done")
        self.assertFalse(ok)
        self.assertEqual(calls, ["done", "open"])
        self.assertIn("still scheduled", detail)
        self.assertTrue(fake.item["enabled"])
        self.assertEqual(fake.item["options"]["jarvis_reminder"]["status"], "open")

    def test_reopen_cancels_new_local_job_if_cloud_copy_refuses(self):
        from core.routines import desktop
        fake = _FakeReminderEngine()
        fake.item["enabled"] = False
        fake.item["options"]["jarvis_reminder"].update({"status": "done", "cloud_synced": True})
        meta = dict(fake.item["options"]["jarvis_reminder"])
        with (patch.object(desktop, "engine", return_value=fake),
              patch.object(reminder_module, "_reschedule_os_schedule",
                           return_value=(True, "rescheduled", dict(meta, scheduler_id="schtasks:new"))) as schedule,
              patch.object(reminder_module, "_cloud_reminder_state", return_value=(False, "offline")),
              patch.object(reminder_module, "_cancel_os_schedule", return_value=(True, "cancelled")) as cancel):
            ok, detail = reminder_module.set_reminder_state("abc123", "open")
        self.assertFalse(ok)
        self.assertIn("offline", detail)
        schedule.assert_called_once()
        cancel.assert_called_once()
        self.assertFalse(fake.item["enabled"])
        self.assertEqual(fake.item["options"]["jarvis_reminder"]["status"], "done")

    def test_successful_cloud_mirror_is_recorded_on_canonical_reminder(self):
        from core.routines.engine import RoutineEngine
        from core.routines import desktop
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(), autostart=False,
                                   log=lambda *_: None)
            due = datetime.now() + timedelta(days=2)
            item = engine.add("Mirror me", "say", "Mirror me",
                              trigger={"type": "time", "rule": {"type": "once", "at_ts": due.timestamp()}},
                              source="reminder", next_ts=due.timestamp(),
                              options={"jarvis_reminder": {"id": "stable-456", "status": "open",
                                                            "due_ts": due.timestamp(), "message": "Mirror me"}})
            class Agent:
                @staticmethod
                def mirror_reminder(*_a, **_k): return True, "synced"
            config = {"pair_code": "jarvis://valid"}
            with (patch.object(desktop, "engine", return_value=engine),
                  patch("memory.config_manager.get_plugin_config", return_value=config),
                  patch("memory.config_manager.get_plugin_enabled", return_value=True),
                  patch.dict("sys.modules", {"plugins.cloud_agent": Agent})):
                text = reminder_module._mirror_to_cloud("Mirror me", due, "stable-456")
            saved = engine.get(item["id"])
            self.assertIn("phone", text.lower())
            self.assertTrue(saved["options"]["jarvis_reminder"]["cloud_synced"])

    def test_cloudflare_worker_mirrors_without_legacy_pair_code(self):
        from core.routines.engine import RoutineEngine
        from core.routines import desktop
        class Agent:
            @staticmethod
            def mirror_reminder(*_a, **_k):
                return True, "synced"
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(),
                                   autostart=False, log=lambda *_: None)
            due = datetime.now() + timedelta(days=2)
            item = engine.add("Worker mirror", "say", "Worker mirror",
                              trigger={"type": "time", "rule": {"type": "once", "at_ts": due.timestamp()}},
                              source="reminder", next_ts=due.timestamp(),
                              options={"jarvis_reminder": {"id": "worker-789", "status": "open",
                                                           "due_ts": due.timestamp(), "message": "Worker mirror"}})
            config = {"worker_url": "https://jarvis-reminders.example.workers.dev",
                      "worker_token": "x" * 40}
            with (patch.object(desktop, "engine", return_value=engine),
                  patch("memory.config_manager.get_plugin_config", return_value=config),
                  patch("memory.config_manager.get_plugin_enabled", return_value=True),
                  patch.dict("sys.modules", {"plugins.cloud_agent": Agent})):
                result = reminder_module._mirror_to_cloud("Worker mirror", due, "worker-789")
            saved = engine.get(item["id"])
            self.assertIn("Apple Reminders", result)
            self.assertTrue(saved["options"]["jarvis_reminder"]["cloud_synced"])

    def test_routines_update_routes_reminder_completion_through_coordinator(self):
        from actions import routines as routines_action
        from core.routines import desktop
        fake = _FakeReminderEngine()
        def set_state(reminder_id, state):
            self.assertEqual(reminder_id, "abc123")
            self.assertEqual(state, "done")
            fake.item["enabled"] = False
            fake.item["options"]["jarvis_reminder"]["status"] = "done"
            return True, "done"
        with patch.object(desktop, "engine", return_value=fake), \
             patch("actions.reminder.set_reminder_state", side_effect=set_state) as coordinator:
            result = routines_action.routines({"action": "update", "id": "routine-1", "enabled": False})
        coordinator.assert_called_once_with("abc123", "done")
        self.assertEqual(fake.update_calls, [])
        self.assertIn("done", result.lower())

    def test_routines_remove_cancels_reminder_instead_of_deleting_history(self):
        from actions import routines as routines_action
        from core.routines import desktop
        fake = _FakeReminderEngine()
        with patch.object(desktop, "engine", return_value=fake), \
             patch("actions.reminder.set_reminder_state", return_value=(True, "cancelled")) as coordinator:
            result = routines_action.routines({"action": "remove", "id": "routine-1"})
        coordinator.assert_called_once_with("abc123", "cancelled")
        self.assertIn("cancelled", result.lower())
        self.assertEqual(fake.remove_calls, [])


class _FakeReminderEngine:
    def __init__(self):
        self.update_calls = []
        self.remove_calls = []
        self.item = {
            "id": "routine-1", "name": "Test reminder", "source": "reminder", "enabled": True,
            "text": "Test reminder", "next_ts": 9999999999,
            "trigger": {"type": "time", "rule": {"type": "once", "at_ts": 9999999999}},
            "options": {"jarvis_reminder": {
                "id": "abc123", "status": "open", "due_ts": 9999999999,
                "message": "Test reminder", "os_name": "windows",
                "task_name": "JARVISReminder_abc123", "script_path": "C:\\Users\\test\\.jarvis\\reminders\\JARVISReminder_abc123.py",
                "scheduler_id": "schtasks:JARVISReminder_abc123",
            }},
        }
    def list(self): return [self.item]
    def get(self, rid): return dict(self.item) if rid == self.item["id"] else None
    def describe(self, item): return "once"
    def remove(self, rid):
        self.remove_calls.append(rid)
        return True
    def update(self, rid, **fields):
        self.update_calls.append((rid, dict(fields)))
        if "options" in fields:
            self.item["options"].update(fields.pop("options"))
        self.item.update(fields)
        return dict(self.item)


if __name__ == "__main__":
    unittest.main()
