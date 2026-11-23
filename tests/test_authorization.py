import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import authorization
from core.action_loader import ActionRecord, ActionRegistry


class AuthorizationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.policy_path = root / "policy.json"
        self.audit_path = root / "decisions.jsonl"
        self.p_policy = patch.object(authorization, "_POLICY_PATH", self.policy_path)
        self.p_audit = patch.object(authorization, "_AUDIT_PATH", self.audit_path)
        self.p_policy.start()
        self.p_audit.start()

    def tearDown(self):
        self.p_policy.stop()
        self.p_audit.stop()
        self.temp.cleanup()

    def test_default_policy_distinguishes_allow_confirm_and_deny(self):
        policy = authorization.get_policy()["classes"]
        self.assertEqual(policy["read_only"], "allow")
        self.assertEqual(policy["persistent_automation"], "allow")
        self.assertEqual(policy["destructive_change"], "confirm")
        self.assertEqual(policy["security_bypass"], "deny")
        self.assertEqual(policy["credential_exposure"], "deny")

    def test_policy_change_persists_and_is_audited(self):
        authorization.set_rule("read_only", "confirm")
        self.assertEqual(authorization.get_policy()["classes"]["read_only"], "confirm")
        rows = [json.loads(x) for x in self.audit_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["event"], "policy_changed")
        self.assertEqual(rows[-1]["source"], "human_confirmed")

    def test_classifier_marks_recurring_automation_and_destructive_actions(self):
        self.assertEqual(authorization.classify_action(
            "background_tasks", {"action": "routine_add"}), "persistent_automation")
        self.assertEqual(authorization.classify_action(
            "file_controller", {"action": "delete"}), "destructive_change")
        self.assertEqual(authorization.classify_action(
            "file_controller", {"action": "organize_desktop"}), "reversible_change")
        with patch("actions.file_controller._resolve_path") as resolve:
            from pathlib import Path
            resolve.return_value = Path(self.temp.name) / "new.txt"
            self.assertEqual(authorization.classify_action(
                "file_controller", {"action": "create_file", "path": self.temp.name, "name": "new.txt"}),
                "reversible_change")
            self.assertEqual(authorization.classify_action(
                "file_controller", {"action": "write", "path": self.temp.name, "name": "new.txt"}),
                "reversible_change")
            existing = Path(self.temp.name) / "policy.json"
            existing.write_text("original", encoding="utf-8")
            resolve.return_value = Path(self.temp.name)
            self.assertEqual(authorization.classify_action(
                "file_controller", {"action": "write", "path": self.temp.name, "name": "policy.json"}),
                "destructive_change")
        self.assertEqual(authorization.classify_action(
            "file_controller", {"action": "write"}), "unknown_high_impact")
        self.assertEqual(authorization.classify_action(
            "computer_settings", {"action": "toggle_wifi"}), "destructive_change")
        self.assertEqual(authorization.classify_action(
            "web_search", {}), "read_only")
        self.assertEqual(authorization.classify_action(
            "jarvis_health", {"scope": "full"}), "read_only")
        self.assertEqual(authorization.authorize(
            "jarvis_health", {"scope": "full"}), ("read_only", "allow"))
        self.assertEqual(authorization.classify_action(
            "file_processor", {"action": "translate"}), "read_only")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"action": "translate", "file_path": "photo.png"}), "read_only")

    def test_authorization_check_is_audited(self):
        action_class, decision = authorization.authorize(
            "background_tasks", {"action": "routine_add"})
        self.assertEqual((action_class, decision), ("persistent_automation", "allow"))
        row = json.loads(self.audit_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(row["event"], "authorization_check")
        self.assertEqual(row["decision"], "allow")

    def test_focus_mode_is_a_reversible_user_requested_session(self):
        self.assertEqual(authorization.classify_action("focus_mode", {"action": "start"}), "reversible_change")
        self.assertEqual(authorization.authorize("focus_mode", {"action": "start"}), ("reversible_change", "allow"))

    def test_unknown_action_is_denied_by_default(self):
        action_class, decision = authorization.authorize("unclassified_tool", {})
        self.assertEqual(action_class, "unknown_high_impact")
        self.assertEqual(decision, "deny")

    def test_visual_board_actions_are_allowed_as_reversible_changes(self):
        for name in ("show_visual", "present_visual_lesson", "draw_right_triangle", "clear_visual"):
            with self.subTest(name=name):
                action_class, decision = authorization.authorize(name, {})
                self.assertEqual(action_class, "reversible_change")
                self.assertEqual(decision, "allow")

    def test_confirm_class_action_fails_closed_without_hud(self):
        from core import confirm
        calls = []
        confirm.bind(show=None, hide=None, log=None)
        record = ActionRecord(name="file_controller", valid=True,
                              handler=lambda parameters: calls.append(parameters) or "deleted")
        registry = ActionRegistry({"file_controller": record}, logger=lambda *_: None)
        result = registry.run("file_controller", {"action": "delete"})
        self.assertIn("cannot confirm", result.lower())
        self.assertEqual(calls, [])

    def test_confirm_class_action_waits_for_human_hud(self):
        from core import confirm
        import threading
        calls = []
        shown = []
        shown_event = threading.Event()
        confirm.bind(show=lambda title, detail: (shown.append((title, detail)),
                                                  shown_event.set()),
                     hide=lambda: None, log=lambda msg: None)
        record = ActionRecord(name="file_controller", valid=True,
                              handler=lambda parameters: calls.append(parameters) or "deleted")
        registry = ActionRegistry({"file_controller": record}, logger=lambda *_: None)
        result_box = []
        with patch.object(authorization, "_POLICY_PATH", self.policy_path), \
             patch.object(authorization, "_AUDIT_PATH", self.audit_path):
            worker = threading.Thread(
                target=lambda: result_box.append(
                    registry.run("file_controller", {"action": "delete"})))
            worker.start()
            self.assertTrue(shown_event.wait(1), "HUD was not requested")
            self.assertEqual(calls, [])
            self.assertEqual(len(shown), 1)
            confirm.resolve(True)
            self.assertTrue(confirm.wait_for_workers(timeout=2))
            worker.join(2)
            self.assertFalse(worker.is_alive(), "tool call did not receive its final result")
            self.assertEqual(len(calls), 1)
            self.assertEqual(result_box, ["deleted"])
        confirm.bind(show=None, hide=None, log=None)


if __name__ == "__main__":
    unittest.main()
