import threading
import unittest
from unittest.mock import Mock, patch

from core import confirm
from core.action_loader import ActionRecord, ActionRegistry


class FakeView:
    def __init__(self, *, degraded=False, source="uia", pid=321,
                 handle=654, title="Disposable Target", app="testapp.exe"):
        self.degraded = degraded
        self.source = source
        self.pid = pid
        self.window_handle = handle
        self.title = title
        self.app = app


class ScreenConfirmationFocusTests(unittest.TestCase):
    def setUp(self):
        self.shown = threading.Event()
        self.show = Mock(side_effect=lambda *_: self.shown.set())
        self.hide = Mock()
        self.log = Mock()
        confirm.bind(show=self.show, hide=self.hide, log=self.log)
        self.handler = Mock(return_value="ACTION_DELIVERED_AND_VERIFIED")
        record = ActionRecord(name="screen_perception", handler=self.handler,
                              valid=True)
        self.registry = ActionRegistry({"screen_perception": record}, logger=Mock())

    def tearDown(self):
        if confirm.pending_title():
            confirm.resolve(False)
        self.assertTrue(confirm.wait_for_workers(timeout=2.0))
        confirm.bind(show=None, hide=None, log=None)

    def _start_confirmed_action(self, parameters):
        results = []
        worker = threading.Thread(
            target=lambda: results.append(
                self.registry.run("screen_perception", parameters, {})))
        worker.start()
        self.assertTrue(self.shown.wait(1), "HUD was not requested")
        self.assertTrue(confirm.pending_title())
        return worker, results

    def test_preflight_refuses_unreadable_target_before_confirmation(self):
        with patch("core.authorization.authorize",
                   return_value=("destructive_change", "confirm")), \
             patch("core.authorization.record") as audit, \
             patch("core.screenview.look", return_value=FakeView(degraded=True)):
            result = self.registry.run(
                "screen_perception", {"action": "click", "target": "Delete"}, {})
        self.assertIn("SCREEN_UNAVAILABLE", result)
        self.show.assert_not_called()
        self.handler.assert_not_called()
        audit.assert_called_once()

    def test_approval_restores_exact_window_then_takes_fresh_snapshot(self):
        initial, fresh = FakeView(), FakeView()
        with patch("core.authorization.authorize",
                   return_value=("destructive_change", "confirm")), \
             patch("core.authorization.record") as audit, \
             patch("core.screenview.look", side_effect=[initial, fresh]) as look, \
             patch("core.screenview.activate_window", return_value=True) as activate:
            worker, results = self._start_confirmed_action(
                {"action": "click", "target": "Delete test item", "role": "button"})
            self.show.assert_called_once()
            self.assertIn("Disposable Target", self.show.call_args.args[1])
            confirm.resolve(True)
            self.assertTrue(confirm.wait_for_workers(timeout=2.0))
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(results, ["ACTION_DELIVERED_AND_VERIFIED"])

        activate.assert_called_once_with(321, 654, "Disposable Target")
        self.assertEqual(look.call_count, 2)
        self.handler.assert_called_once()
        self.assertTrue(any(call.args[0] == "action_confirmed"
                            for call in audit.call_args_list))

    def test_cancel_returns_final_result_without_running_action(self):
        with patch("core.authorization.authorize",
                   return_value=("destructive_change", "confirm")), \
             patch("core.authorization.record"), \
             patch("core.screenview.look", return_value=FakeView()):
            worker, results = self._start_confirmed_action(
                {"action": "click", "target": "Delete test item"})
            confirm.resolve(False)
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(results, ["ACTION_CANCELLED_BY_USER: nothing was executed."])

        self.handler.assert_not_called()

    def test_failed_restore_never_runs_action(self):
        with patch("core.authorization.authorize",
                   return_value=("destructive_change", "confirm")), \
             patch("core.authorization.record") as audit, \
             patch("core.screenview.look", return_value=FakeView()), \
             patch("core.screenview.activate_window", return_value=False):
            worker, results = self._start_confirmed_action(
                {"action": "click", "target": "Delete test item"})
            confirm.resolve(True)
            self.assertTrue(confirm.wait_for_workers(timeout=2.0))
            worker.join(2)
            self.assertFalse(worker.is_alive())

        self.handler.assert_not_called()
        self.assertIn("ACTION_NOT_EXECUTED", results[0])
        self.assertTrue(any(call.args[0] == "action_blocked"
                            for call in audit.call_args_list))

    def test_changed_window_after_approval_never_runs_action(self):
        initial = FakeView()
        changed = FakeView(pid=999, handle=888, title="Different Window")
        with patch("core.authorization.authorize",
                   return_value=("destructive_change", "confirm")), \
             patch("core.authorization.record") as audit, \
             patch("core.screenview.look", side_effect=[initial, changed]), \
             patch("core.screenview.activate_window", return_value=True):
            worker, results = self._start_confirmed_action(
                {"action": "click", "target": "Delete test item"})
            confirm.resolve(True)
            self.assertTrue(confirm.wait_for_workers(timeout=2.0))
            worker.join(2)
            self.assertFalse(worker.is_alive())

        self.handler.assert_not_called()
        self.assertIn("ACTION_NOT_EXECUTED", results[0])
        self.assertTrue(any(call.args[0] == "action_blocked"
                            for call in audit.call_args_list))


if __name__ == "__main__":
    unittest.main()
