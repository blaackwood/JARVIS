import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import authorization, confirm
from actions import background_tasks as background_module


class FakeEngine:
    def __init__(self):
        self.created = []
        self.removed = []
    def add_routine(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "routine-test-001", "at": kwargs["at"],
                "next_run": time.time() + 3600,
                "frequency": kwargs["frequency"], "weekday": kwargs.get("weekday")}
    def remove_routine(self, routine_id):
        self.removed.append(routine_id)
        return routine_id == "routine-test-001"


class AuthorizationLivePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.p_policy = patch.object(authorization, "_POLICY_PATH", root / "policy.json")
        self.p_audit = patch.object(authorization, "_AUDIT_PATH", root / "audit.jsonl")
        self.p_policy.start()
        self.p_audit.start()
        self.engine = FakeEngine()
        self.shown = []
        self.logs = []
        confirm.bind(show=lambda title, detail: self.shown.append((title, detail)),
                     hide=lambda: None, log=self.logs.append)
        self.ensure_patch = patch("core.tasks.desktop.ensure", return_value=self.engine)
        self.ensure_patch.start()

    def tearDown(self):
        if confirm.pending_title():
            confirm.resolve(False)
        self.assertTrue(confirm.wait_for_workers(timeout=2.0),
                        "confirmation worker did not finish before temp cleanup")
        confirm.bind(show=None, hide=None, log=None)
        self.ensure_patch.stop()
        self.p_policy.stop()
        self.p_audit.stop()
        self.temp.cleanup()

    def _wait(self, predicate):
        deadline = time.time() + 2
        while not predicate() and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(predicate(), "confirmation worker did not finish")

    def test_recurring_routine_is_created_without_hud_approval(self):
        result = background_module.background_tasks({
            "action": "routine_add", "task": "Teste isolado", "frequency": "daily",
            "at": "23:59", "minutes": 1,
        })
        self.assertIn("Routine created", result)
        self.assertEqual(len(self.engine.created), 1)
        self.assertEqual(self.shown, [])

    def test_recurring_routine_creation_is_audited_as_automatic(self):
        background_module.background_tasks({
            "action": "routine_add", "task": "Teste automatico", "frequency": "daily",
            "at": "23:59", "minutes": 1,
        })
        audit_path = Path(self.temp.name) / "audit.jsonl"
        audit = audit_path.read_text(encoding="utf-8")
        self.assertIn("routine_created", audit)
        self.assertIn("automatic_policy", audit)
        self.assertEqual(self.shown, [])

    def test_approved_routine_is_created_and_audited(self):
        result = background_module.background_tasks({
            "action": "routine_add", "task": "Teste aprovado", "frequency": "daily",
            "at": "23:59", "minutes": 1,
        })
        self.assertIn("Routine created", result)
        self.assertEqual(self.engine.created[0]["task"], "Teste aprovado")
        audit_path = Path(self.temp.name) / "audit.jsonl"
        audit = audit_path.read_text(encoding="utf-8")
        self.assertIn("routine_created", audit)
        self.assertIn("automatic_policy", audit)

    def test_routine_removal_is_automatic_and_audited(self):
        result = background_module.background_tasks({
            "action": "routine_remove", "routine_id": "routine-test-001",
        })
        self.assertIn("removed", result.lower())
        self.assertEqual(self.engine.removed, ["routine-test-001"])
        audit_path = Path(self.temp.name) / "audit.jsonl"
        audit = audit_path.read_text(encoding="utf-8")
        self.assertIn("routine_removed", audit)
        self.assertIn("automatic_policy", audit)

    def test_policy_change_waits_for_human_approval(self):
        from actions.authorization import authorization as authorization_handler
        result = authorization_handler({
            "action": "set", "class": "reversible_change", "decision": "deny",
        })
        self.assertIn("CONFIRMATION_PENDING", result)
        self.assertEqual(authorization.get_policy()["classes"]["reversible_change"], "allow")
        confirm.resolve(True)
        self._wait(lambda: authorization.get_policy()["classes"]["reversible_change"] == "deny")
        audit_path = Path(self.temp.name) / "audit.jsonl"
        self._wait(lambda: audit_path.exists() and "policy_changed" in
                   audit_path.read_text(encoding="utf-8"))

    def test_policy_change_cancel_does_not_persist(self):
        from actions.authorization import authorization as authorization_handler
        result = authorization_handler({
            "action": "set", "class": "reversible_change", "decision": "deny",
        })
        self.assertIn("CONFIRMATION_PENDING", result)
        confirm.resolve(False)
        time.sleep(0.05)
        self.assertEqual(authorization.get_policy()["classes"]["reversible_change"], "allow")

    def test_multiple_routines_can_be_created_without_confirmation_queue(self):
        first = background_module.background_tasks({
            "action": "routine_add", "task": "Primeira", "frequency": "daily",
            "at": "23:59", "minutes": 1,
        })
        second = background_module.background_tasks({
            "action": "routine_add", "task": "Segunda", "frequency": "daily",
            "at": "23:59", "minutes": 1,
        })
        self.assertIn("Routine created", first)
        self.assertIn("Routine created", second)
        self.assertEqual(len(self.engine.created), 2)
        self.assertEqual(self.shown, [])


if __name__ == "__main__":
    unittest.main()
