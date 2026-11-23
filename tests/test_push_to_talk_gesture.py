import inspect
import unittest
import platform

from core.hotkey import PushToTalk
from core.ink_gesture import InkGestureWatcher


class SharedHotkeyGestureTests(unittest.TestCase):
    def test_secondary_chord_callback_receives_only_state_transitions(self):
        events = []
        hotkeys = PushToTalk(lambda held: None, on_secondary_change=events.append)
        hotkeys._set_secondary_held(True)
        hotkeys._set_secondary_held(True)  # duplicate state is ignored
        hotkeys._set_secondary_held(False)
        self.assertEqual(events, [True, False])

    def test_windows_default_avoids_altgr_conflict(self):
        hotkeys = PushToTalk(lambda held: None)
        if platform.system() == "Windows":
            self.assertEqual(hotkeys._secondary_chord, ("ctrl", "shift"))
            self.assertEqual(hotkeys.secondary_label, "Ctrl+Shift")

    def test_secondary_callback_can_be_attached_after_ptt_is_created(self):
        events = []
        hotkeys = PushToTalk(lambda held: None)
        hotkeys.set_secondary_callback(events.append)
        hotkeys._set_secondary_held(True)
        hotkeys._set_secondary_held(False)
        self.assertEqual(events, [True, False])

    def test_ink_watcher_is_armed_externally_and_never_reads_keyboard(self):
        watcher = InkGestureWatcher(
            on_state=lambda held: None,
            on_points=lambda points, snapped: None,
            on_release=lambda points: None,
        )
        watcher.set_held(True)
        self.assertTrue(watcher._armed)
        watcher.set_held(False)
        self.assertFalse(watcher._armed)
        source = inspect.getsource(InkGestureWatcher)
        self.assertIn("GetCursorPos", source)
        self.assertNotIn("GetAsyncKeyState", source)


if __name__ == "__main__":
    unittest.main()
