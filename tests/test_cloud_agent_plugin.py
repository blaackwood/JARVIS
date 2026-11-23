import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from plugins import cloud_agent
from core.plugin_loader import discover_plugins


class CloudAgentPluginTests(unittest.TestCase):
    def setUp(self):
        for name, kwargs in (
            ("_worker_config", {"return_value": None}),
            ("_worker_request", {"side_effect": AssertionError("Unexpected cloud request")}),
            ("start_reminder_sync", {"return_value": False}),
        ):
            patcher = patch.object(cloud_agent, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_plugin_is_discoverable_and_settings_keep_pair_code_private(self):
        root = Path(__file__).resolve().parents[1]
        registry = discover_plugins(root / "plugins", set(), logger=lambda *_: None)
        self.assertTrue(registry.has("cloud_agent"))
        record = registry._plugins["cloud_agent"]
        self.assertTrue(record.valid)
        settings = record.settings
        self.assertEqual(settings["namespace"], "cloud_agent")
        self.assertEqual(settings["fields"][0]["key"], "pair_code")
        self.assertEqual(settings["fields"][0]["type"], "password")

    def test_test_connection_requires_real_jarvis_cloud_endpoint(self):
        client = Mock()
        client.request.side_effect = [
            {"server": "jarvis-cloud", "name": "JARVIS",
             "telegram_configured": True, "telegram_phones": 1},
            {"ok": True, "setup_profile_url": "https://cloud.test/caldav-setup/token.mobileconfig",
             "credentials_url": "https://cloud.test/caldav-setup/token", "username": "jarvis"},
        ]
        with patch.object(cloud_agent, "_client", return_value=client):
            ok, detail = cloud_agent._test_connection({"pair_code": "test-code"})
        self.assertTrue(ok)
        self.assertIn("Telegram is configured", detail)
        self.assertIn("Install profile:", detail)
        self.assertIn("caldav-setup/token.mobileconfig", detail)
        self.assertEqual(client.request.call_args_list[0].args, ("POST", "hello", {}))
        self.assertEqual(client.request.call_args_list[1].args, ("POST", "caldav_info", {}))

    def test_test_connection_rejects_non_jarvis_endpoint(self):
        client = Mock()
        client.request.return_value = {"server": "other"}
        with patch.object(cloud_agent, "_client", return_value=client):
            ok, detail = cloud_agent._test_connection({"pair_code": "test-code"})
        self.assertFalse(ok)
        self.assertIn("did not identify", detail)

    def test_mirror_uses_desktop_stable_id_and_local_timezone(self):
        client = Mock()
        client.request.return_value = {"result": "status=done action=schedule id=cloud1"}
        due = datetime.now().astimezone() + timedelta(days=2)
        with patch.object(cloud_agent, "_client", return_value=client), \
             patch.object(cloud_agent, "_local_offset_minutes", return_value=-180):
            ok, detail = cloud_agent.mirror_reminder("Call the dentist", due, "local123")
        self.assertTrue(ok, detail)
        args = client.request.call_args.args
        body = args[2]
        self.assertEqual(args[:2], ("POST", "schedule"))
        self.assertEqual(body["action"], "add")
        self.assertEqual(body["external_id"], "local123")
        self.assertEqual(body["at"], due.strftime("%Y-%m-%d %H:%M"))
        self.assertEqual(body["tz_offset_min"], -180)

    def test_state_updates_use_stable_external_id(self):
        client = Mock()
        client.request.return_value = {"result": "status=done action=schedule id=local123 status=done"}
        with patch.object(cloud_agent, "_client", return_value=client):
            ok, detail = cloud_agent.set_reminder_state("local123", "done")
        self.assertTrue(ok, detail)
        args = client.request.call_args
        self.assertEqual(args.args[1], "schedule")
        self.assertEqual(args.args[2]["action"], "complete")
        self.assertEqual(args.args[2]["id"], "local123")

    def test_sync_recovers_lost_cloud_create_response_by_external_id(self):
        import tempfile
        from core.routines import desktop
        from core.routines.engine import RoutineEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(), autostart=False,
                                   log=lambda *_: None)
            due = datetime.now().astimezone() + timedelta(days=2)
            local = engine.add("Buy coffee", "say", "Buy coffee",
                               trigger={"type": "time", "rule": {"type": "once", "at_ts": due.timestamp()}},
                               source="reminder", next_ts=due.timestamp(),
                               options={"jarvis_reminder": {"id": "stable-lost-789", "status": "open",
                                   "due_ts": due.timestamp(), "message": "Buy coffee",
                                   "cloud_synced": False, "task_name": "JARVISReminder_lost789",
                                   "scheduler_id": "schtasks:JARVISReminder_lost789", "os_name": "windows"}})
            client = Mock()
            client.request.return_value = {"reminders": [{"id": "stable-lost-789", "cloud_id": "remote-42",
                "status": "open", "due_ts": due.timestamp(), "message": "Buy coffee"}]}
            with (patch.object(desktop, "engine", return_value=engine),
                  patch.object(cloud_agent, "_pair_code", return_value="paired"),
                  patch.object(cloud_agent, "_client", return_value=client)):
                ok, detail = cloud_agent.sync_reminder_states()
            self.assertTrue(ok, detail)
            rows = [r for r in engine.list() if r.get("source") == "reminder"]
            self.assertEqual(len(rows), 1)
            meta = engine.get(local["id"])["options"]["jarvis_reminder"]
            self.assertTrue(meta["cloud_synced"])
            self.assertEqual(meta["cloud_id"], "remote-42")
            self.assertIn("sync_recovered_at", meta)

    def test_sync_pulls_telegram_done_into_local_routine_and_cancels_os_job(self):
        import tempfile
        from core.routines import desktop
        from core.routines.engine import RoutineEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(), autostart=False,
                                   log=lambda *_: None)
            due = datetime.now().astimezone() + timedelta(days=2)
            local = engine.add("Call the dentist", "say", "Call the dentist",
                               trigger={"type": "time", "rule": {"type": "once", "at_ts": due.timestamp()}},
                               source="reminder", next_ts=due.timestamp(),
                               options={"jarvis_reminder": {"id": "stable-123", "status": "open",
                                   "due_ts": due.timestamp(), "message": "Call the dentist",
                                   "cloud_synced": True, "task_name": "JARVISReminder_stable123",
                                   "scheduler_id": "schtasks:JARVISReminder_stable123", "os_name": "windows"}})
            client = Mock()
            client.request.return_value = {"reminders": [{"id": "stable-123", "status": "done",
                                                            "due_ts": due.timestamp(), "message": "Call the dentist",
                                                            "completed_at": 12345}]}
            with (patch.object(desktop, "engine", return_value=engine),
                  patch.object(cloud_agent, "_pair_code", return_value="paired"),
                  patch.object(cloud_agent, "_client", return_value=client),
                  patch("actions.reminder._cancel_os_schedule", return_value=(True, "cancelled")) as cancel):
                ok, detail = cloud_agent.sync_reminder_states()
            self.assertTrue(ok, detail)
            cancel.assert_called_once()
            saved = engine.get(local["id"])
            self.assertFalse(saved["enabled"])
            self.assertEqual(saved["options"]["jarvis_reminder"]["status"], "done")
            self.assertEqual(saved["options"]["jarvis_reminder"]["completed_at"], 12345)

    def test_sync_imports_phone_created_reminder_into_local_hud_store(self):
        import tempfile
        from core.routines import desktop
        from core.routines.engine import RoutineEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(), autostart=False,
                                   log=lambda *_: None)
            due = datetime.now().astimezone() + timedelta(days=3)
            client = Mock()
            client.request.return_value = {"reminders": [{
                "id": "rphone123", "cloud_id": "rphone123", "status": "open",
                "due_ts": due.timestamp(), "message": "Buy a notebook",
            }]}
            script = Path(tmp) / "JARVISReminder_rphone123.py"
            with (patch.object(desktop, "engine", return_value=engine),
                  patch.object(cloud_agent, "_pair_code", return_value="paired"),
                  patch.object(cloud_agent, "_client", return_value=client),
                  patch("actions.reminder._get_os", return_value="windows"),
                  patch("actions.reminder._write_notify_script", return_value=script),
                  patch("actions.reminder._schedule_windows", return_value="schtasks:JARVISReminder_rphone123")):
                ok, detail = cloud_agent.sync_reminder_states()
            self.assertTrue(ok, detail)
            rows = [r for r in engine.list() if r.get("source") == "reminder"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "Buy a notebook")
            meta = rows[0]["options"]["jarvis_reminder"]
            self.assertEqual(meta["id"], "rphone123")
            self.assertTrue(meta["cloud_synced"])
            self.assertEqual(meta["scheduler_id"], "schtasks:JARVISReminder_rphone123")
            self.assertTrue(rows[0]["enabled"])

    def test_sync_pulls_telegram_snooze_into_local_trigger(self):
        import tempfile
        from core.routines import desktop
        from core.routines.engine import RoutineEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(), autostart=False,
                                   log=lambda *_: None)
            due = datetime.now().astimezone() + timedelta(days=2)
            snoozed = due + timedelta(hours=2)
            local = engine.add("Pay bill", "say", "Pay bill",
                               trigger={"type": "time", "rule": {"type": "once", "at_ts": due.timestamp()}},
                               source="reminder", next_ts=due.timestamp(),
                               options={"jarvis_reminder": {"id": "stable-456", "status": "open",
                                   "due_ts": due.timestamp(), "message": "Pay bill", "cloud_synced": True,
                                   "task_name": "JARVISReminder_stable456", "scheduler_id": "schtasks:old",
                                   "os_name": "windows"}})
            client = Mock()
            client.request.return_value = {"reminders": [{"id": "stable-456", "status": "open",
                                                            "due_ts": snoozed.timestamp(), "message": "Pay bill"}]}
            with (patch.object(desktop, "engine", return_value=engine),
                  patch.object(cloud_agent, "_pair_code", return_value="paired"),
                  patch.object(cloud_agent, "_client", return_value=client),
                  patch("actions.reminder._reschedule_os_schedule",
                        return_value=(True, "rescheduled", {"task_name": "JARVISReminder_stable456",
                            "scheduler_id": "schtasks:new", "script_path": "", "os_name": "windows"})) as schedule):
                ok, detail = cloud_agent.sync_reminder_states()
            self.assertTrue(ok, detail)
            schedule.assert_called_once()
            saved = engine.get(local["id"])
            meta = saved["options"]["jarvis_reminder"]
            self.assertAlmostEqual(meta["due_ts"], snoozed.timestamp(), delta=0.001)
            self.assertAlmostEqual(saved["next_ts"], snoozed.timestamp(), delta=0.001)
            self.assertEqual(meta["scheduler_id"], "schtasks:new")

    def test_sync_refuses_unsupported_cloud_server_shape_without_changing_local_state(self):
        client = Mock()
        client.request.return_value = {"result": "Nothing scheduled."}
        from core.routines import desktop
        with patch.object(desktop, "engine", return_value=Mock(list=Mock(return_value=[]))), \
             patch.object(cloud_agent, "_pair_code", return_value="paired"), \
             patch.object(cloud_agent, "_client", return_value=client):
            ok, detail = cloud_agent.sync_reminder_states()
        self.assertFalse(ok)
        self.assertIn("does not support structured reminder sync", detail)

    def test_cloudflare_worker_settings_are_available_without_removing_legacy_pairing(self):
        fields = cloud_agent.PLUGIN_SETTINGS["fields"]
        self.assertEqual([row["key"] for row in fields],
                         ["pair_code", "worker_url", "worker_token"])
        self.assertEqual(fields[1]["type"], "text")
        self.assertEqual(fields[2]["type"], "password")

    def test_cloudflare_worker_connection_returns_apple_profile_links(self):
        with (patch.object(cloud_agent, "_worker_config", return_value=("https://jarvis.test", "x" * 48)),
              patch.object(cloud_agent, "_worker_request", side_effect=[
                  {"ok": True, "server": "jarvis-cloudflare"},
                  {"ok": True, "setup_profile_url": "https://jarvis.test/setup/JARVIS.mobileconfig",
                   "credentials_url": "https://jarvis.test/setup", "username": "jarvis"}
              ]) as request,
              patch.object(cloud_agent, "start_reminder_sync", return_value=True)):
            ok, detail = cloud_agent._test_connection({"worker_url": "https://jarvis.test",
                                                       "worker_token": "x" * 48})
        self.assertTrue(ok)
        self.assertIn("JARVIS Cloudflare storage", detail)
        self.assertIn("JARVIS.mobileconfig", detail)
        self.assertEqual(request.call_args_list[0].args[:2], ("GET", "api/health"))
        self.assertEqual(request.call_args_list[1].args[:2], ("GET", "api/setup"))

    def test_cloudflare_worker_mirror_uses_stable_id_and_epoch_timestamp(self):
        client_response = {"ok": True}
        due = datetime.now().astimezone() + timedelta(days=2)
        with (patch.object(cloud_agent, "_worker_config", return_value=("https://jarvis.test", "x" * 48)),
              patch.object(cloud_agent, "_worker_request", return_value=client_response) as request):
            ok, detail = cloud_agent.mirror_reminder("Call the dentist", due, "local123")
        self.assertTrue(ok, detail)
        args = request.call_args.args
        self.assertEqual(args[:2], ("POST", "api/reminders"))
        self.assertEqual(args[2]["action"], "upsert")
        self.assertEqual(args[2]["id"], "local123")
        self.assertEqual(args[2]["message"], "Call the dentist")
        self.assertAlmostEqual(args[2]["due_ts"], due.timestamp(), delta=0.001)

    def test_cloudflare_worker_state_uses_api_and_validates_status(self):
        with (patch.object(cloud_agent, "_worker_config", return_value=("https://jarvis.test", "x" * 48)),
              patch.object(cloud_agent, "_worker_request", return_value={"ok": True}) as request):
            ok, detail = cloud_agent.set_reminder_state("local123", "done")
            self.assertTrue(ok, detail)
            self.assertEqual(request.call_args.args[:2], ("POST", "api/reminders"))
            self.assertEqual(request.call_args.args[2], {
                "action": "state", "id": "local123", "status": "done"
            })
            ok, detail = cloud_agent.set_reminder_state("local123", "maybe")
            self.assertFalse(ok)
            self.assertIn("state must be", detail)
            self.assertEqual(request.call_count, 1)

    def test_cloudflare_worker_sync_pulls_phone_reminder_into_local_store(self):
        import tempfile
        from core.routines import desktop
        from core.routines.engine import RoutineEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = RoutineEngine(Path(tmp) / "routines.json", object(), autostart=False,
                                   log=lambda *_: None)
            due = datetime.now().astimezone() + timedelta(days=3)
            with (patch.object(desktop, "engine", return_value=engine),
                  patch.object(cloud_agent, "_worker_config", return_value=("https://jarvis.test", "x" * 48)),
                  patch.object(cloud_agent, "_worker_request", return_value={"reminders": [{
                      "id": "rphone-cloud-1", "cloud_id": "rphone-cloud-1", "status": "open",
                      "due_ts": due.timestamp(), "message": "Buy a notebook"
                  }]}),
                  patch("actions.reminder._get_os", return_value="windows"),
                  patch("actions.reminder._write_notify_script", return_value=Path(tmp) / "notify.py"),
                  patch("actions.reminder._schedule_windows", return_value="schtasks:JARVISReminder_rphone-cloud-1")):
                ok, detail = cloud_agent.sync_reminder_states()
            self.assertTrue(ok, detail)
            rows = [row for row in engine.list() if row.get("source") == "reminder"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "Buy a notebook")
            self.assertTrue(rows[0]["options"]["jarvis_reminder"]["cloud_synced"])

    def test_state_rejects_unknown_status_without_network(self):
        client = Mock()
        with patch.object(cloud_agent, "_client", return_value=client):
            ok, detail = cloud_agent.set_reminder_state("local123", "maybe")
        self.assertFalse(ok)
        self.assertIn("state must be", detail)
        client.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
