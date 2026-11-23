import io
import plistlib
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.cloud import CloudState, IMPORT_CHECK, MANIFEST, REQUIREMENTS, generate_cert
from core.routines.engine import RoutineEngine
from core.caldav_bridge import CalDAVBridge, parse_vtodo, serialize_vtodo


def _ics(uid="iphone-item", summary="Buy milk", due="20261117T120000Z", status="NEEDS-ACTION"):
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VTODO\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:20261116T120000Z\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DUE:{due}\r\n"
        f"STATUS:{status}\r\n"
        "END:VTODO\r\nEND:VCALENDAR\r\n"
    )


class FakeResponse:
    def __init__(self, status=207, content=b"", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


class FakeProcess:
    def poll(self):
        return None
    def terminate(self):
        pass
    def wait(self, timeout=None):
        return 0


class FakeHandler:
    def __init__(self, path):
        self.path = path
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass

    def send_error(self, status, message=None):
        self.status = status


class CalDAVBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = CloudState(self.root / "state")
        self.state.link.update(lambda d: d.update({
            "host": "cloud.example.invalid", "port": 7443, "secret": "not-used"
        }))
        self.routines = RoutineEngine(
            self.root / "routines.json", object(), autostart=False, log=lambda *_: None
        )
        self.runtime = SimpleNamespace(
            state=self.state, routines=self.routines, log=lambda *_: None
        )
        self.bridge = CalDAVBridge(self.runtime, port=55235)

    def tearDown(self):
        self.bridge.stop()
        self.tmp.cleanup()

    def _add_cloud_reminder(self, text="Desk reminder", due_ts=None):
        due_ts = due_ts or time.time() + 3600
        return self.routines.add(
            text, "say", text,
            trigger={"type": "time", "rule": {"type": "once", "at_ts": due_ts}},
            source="cloud", next_ts=due_ts, enabled=True,
            options={"jarvis_reminder": {
                "id": "stable-desk-1", "status": "open", "due_ts": due_ts,
                "message": text,
            }},
        )

    def test_cloud_deploy_manifest_contains_bridge_and_no_missing_files(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn("core/caldav_bridge.py", MANIFEST)
        self.assertIn("core.caldav_bridge", IMPORT_CHECK)
        self.assertIn("radicale", IMPORT_CHECK)
        self.assertIn("bcrypt", IMPORT_CHECK)
        self.assertTrue(any(dep.startswith("radicale>=") for dep in REQUIREMENTS))
        self.assertTrue(any(dep.startswith("bcrypt>=") for dep in REQUIREMENTS))
        missing = [item for item in MANIFEST if not (root / item).is_file()]
        self.assertEqual(missing, [])

    def test_vtodo_round_trip_preserves_summary_due_and_status(self):
        due = time.time() + 3600
        message = "Buy milk, bread; then call the doctor\nbring the note"
        source = {"uid": "uid-1@jarvis", "message": message, "due_ts": due,
                  "status": "open", "description": ""}
        parsed = parse_vtodo(serialize_vtodo(source))
        self.assertEqual(parsed["uid"], source["uid"])
        self.assertEqual(parsed["message"], message)
        self.assertEqual(parsed["status"], "open")
        self.assertAlmostEqual(parsed["due_ts"], int(due), delta=1)

    def test_date_only_reminder_is_not_given_an_invented_time(self):
        item = parse_vtodo(_ics(due="20261117"))
        self.assertIsNone(item["due_ts"])
        self.assertTrue(item["date_only"])

    def test_iphone_created_timed_item_imports_into_canonical_routines(self):
        due = time.time() + 7200
        item = {"uid": "iphone-new-1", "message": "Pick up a package",
                "due_ts": due, "status": "open", "description": ""}
        row = {"href": "/dav/jarvis/JARVIS/phone.ics", "etag": '"etag-1"', "item": item}
        with patch.object(self.bridge, "_list_items", return_value=[row]):
            result = self.bridge.sync_once()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["imported"], 1)
        rows = self.routines.list()
        self.assertEqual(len(rows), 1)
        meta = rows[0]["options"]["jarvis_reminder"]
        self.assertEqual(rows[0]["text"], "Pick up a package")
        self.assertEqual(meta["caldav_uid"], "iphone-new-1")
        self.assertTrue(meta["caldav_synced_once"])

    def test_iphone_completion_updates_the_same_jarvis_reminder(self):
        due = time.time() + 7200
        open_item = {"uid": "iphone-done-1", "message": "Submit the form",
                     "due_ts": due, "status": "open", "description": ""}
        done_item = {**open_item, "status": "done"}
        first = {"href": "/dav/jarvis/JARVIS/item.ics", "etag": '"etag-1"', "item": open_item}
        second = {"href": "/dav/jarvis/JARVIS/item.ics", "etag": '"etag-2"', "item": done_item}
        with patch.object(self.bridge, "_list_items", side_effect=[[first], [second]]):
            self.assertTrue(self.bridge.sync_once()["ok"])
            result = self.bridge.sync_once()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["updated_from_iphone"], 1)
        rows = self.routines.list()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["options"]["jarvis_reminder"]["status"], "done")

    def test_clearing_iphone_due_date_disables_old_jarvis_schedule(self):
        due = time.time() + 7200
        timed = {"uid": "iphone-clear-date-1", "message": "Read a book",
                 "due_ts": due, "status": "open", "description": ""}
        all_day = {**timed, "due_ts": None, "date_only": True}
        first = {"href": "/dav/jarvis/JARVIS/item.ics", "etag": '"etag-1"', "item": timed}
        second = {"href": "/dav/jarvis/JARVIS/item.ics", "etag": '"etag-2"', "item": all_day}
        with patch.object(self.bridge, "_list_items", side_effect=[[first], [second]]):
            self.bridge.sync_once()
            result = self.bridge.sync_once()
        self.assertTrue(result["ok"], result)
        saved = self.routines.list()[0]
        meta = saved["options"]["jarvis_reminder"]
        self.assertFalse(saved["enabled"])
        self.assertEqual(meta["due_ts"], 0.0)
        self.assertTrue(meta["caldav_date_only"])

    def test_iphone_deletion_cancels_local_record_without_recreating_it(self):
        due = time.time() + 7200
        item = {"uid": "iphone-delete-1", "message": "Old commitment",
                "due_ts": due, "status": "open", "description": ""}
        row = {"href": "/dav/jarvis/JARVIS/item.ics", "etag": '"etag-1"', "item": item}
        with patch.object(self.bridge, "_list_items", side_effect=[[row], []]), \
             patch.object(self.bridge, "_put_item") as put:
            self.bridge.sync_once()
            result = self.bridge.sync_once()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["cancelled"], 1)
        saved = self.routines.list()[0]
        self.assertFalse(saved["enabled"])
        self.assertEqual(saved["options"]["jarvis_reminder"]["status"], "cancelled")
        self.assertTrue(saved["options"]["jarvis_reminder"]["caldav_deleted_by_user"])
        put.assert_not_called()

    def test_local_reminder_is_published_to_apple_list(self):
        due = time.time() + 7200
        local = self._add_cloud_reminder("Pay the internet bill", due)
        with patch.object(self.bridge, "_list_items", return_value=[]), \
             patch.object(self.bridge, "_put_item", return_value=(
                 True, "/dav/jarvis/JARVIS/item.ics", '"etag-new"'
             )) as put:
            result = self.bridge.sync_once()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["published"], 1)
        put.assert_called_once()
        saved = self.routines.get(local["id"])
        meta = saved["options"]["jarvis_reminder"]
        self.assertTrue(meta["caldav_uid"].startswith("jarvis-"))
        self.assertEqual(meta["caldav_href"], "/dav/jarvis/JARVIS/item.ics")

    def test_profile_installs_root_certificate_and_caldav_account_without_embedded_password(self):
        cert_path = self.state.dir / "link-cert.pem"
        key_path = self.state.dir / "link-key.pem"
        generate_cert(cert_path, key_path, "cloud.example.invalid")
        self.bridge._process = FakeProcess()
        handler = FakeHandler(f"/caldav-setup/{self.bridge.setup_token}.mobileconfig")
        self.bridge.handle_setup_request(handler)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.headers["Content-Type"], "application/x-apple-aspen-config")
        profile = plistlib.loads(handler.wfile.getvalue())
        payloads = profile["PayloadContent"]
        by_type = {item["PayloadType"]: item for item in payloads}
        self.assertIn("com.apple.security.root", by_type)
        account = by_type["com.apple.caldav.account"]
        self.assertEqual(account["CalDAVAccountDescription"], "JARVIS")
        self.assertEqual(account["CalDAVUsername"], "jarvis")
        self.assertEqual(account["CalDAVHostName"], "cloud.example.invalid")
        self.assertEqual(account["CalDAVPort"], 7443)
        self.assertTrue(account["CalDAVUseSSL"])
        self.assertTrue(account["CalDAVPrincipalURL"].endswith("/dav/jarvis/"))
        self.assertNotIn("CalDAVPassword", account)

    def test_private_credential_page_is_token_gated_and_not_cached(self):
        generate_cert(self.state.dir / "link-cert.pem", self.state.dir / "link-key.pem",
                      "cloud.example.invalid")
        self.bridge._process = FakeProcess()
        good = FakeHandler(f"/caldav-setup/{self.bridge.setup_token}")
        self.bridge.handle_setup_request(good)
        self.assertEqual(good.status, 200)
        self.assertIn(self.bridge._password.encode(), good.wfile.getvalue())
        self.assertEqual(good.headers["Cache-Control"], "no-store")
        bad = FakeHandler("/caldav-setup/not-the-token")
        self.bridge.handle_setup_request(bad)
        self.assertEqual(bad.status, 404)


if __name__ == "__main__":
    unittest.main()

