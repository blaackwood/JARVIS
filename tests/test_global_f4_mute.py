"""Regression tests for the system-wide F4 microphone mute shortcut.

The production GUI is imported directly through the active gui package.
"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gui.window import MainWindow


class GlobalF4MuteTests(unittest.TestCase):
    def _window_double(self):
        calls = []
        window = SimpleNamespace(
            _f4_was_down=False,
            _toggle_mute=lambda: calls.append("toggle"),
        )
        return window, calls

    def test_global_f4_toggles_once_per_physical_press(self):
        states = iter([
            0,          # idle
            0x8000,     # first press
            0x8000,     # held
            0x8000,     # still held
            0,          # release
            0,          # idle
            0x8000,     # second press
            0,          # release
        ])
        checked_keys = []

        def get_async_key_state(vk):
            checked_keys.append(vk)
            return next(states)

        fake_ctypes = SimpleNamespace(
            windll=SimpleNamespace(
                user32=SimpleNamespace(GetAsyncKeyState=get_async_key_state)
            )
        )
        window, calls = self._window_double()

        with patch.dict(sys.modules, {"ctypes": fake_ctypes}):
            for _ in range(8):
                MainWindow._poll_global_f4(window)

        self.assertEqual(calls, ["toggle", "toggle"])
        self.assertEqual(checked_keys, [0x73] * 8)
        self.assertFalse(window._f4_was_down)

    def test_global_f4_does_not_toggle_when_windows_api_is_unavailable(self):
        window, calls = self._window_double()
        with patch.dict(sys.modules, {"ctypes": SimpleNamespace()}):
            MainWindow._poll_global_f4(window)

        self.assertEqual(calls, [])
        self.assertFalse(window._f4_was_down)


if __name__ == "__main__":
    unittest.main()
