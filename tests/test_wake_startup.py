from pathlib import Path
import tempfile
import unittest

from core.wake_startup import clear_stale_stop_marker, sleep_on_command


class WakeStartupTests(unittest.TestCase):
    def test_stale_stop_marker_is_cleared_at_fresh_login(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "wake_daemon.stop"
            marker.write_text("stop", encoding="utf-8")
            self.assertTrue(clear_stale_stop_marker(marker))
            self.assertFalse(marker.exists())

    def test_missing_stop_marker_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "wake_daemon.stop"
            self.assertTrue(clear_stale_stop_marker(marker))
            self.assertFalse(marker.exists())

    def test_sleep_command_keeps_wake_detector_active(self):
        calls = []
        ok, message = sleep_on_command(
            True,
            lambda: True,
            lambda **kwargs: calls.append(kwargs),
        )
        self.assertTrue(ok)
        self.assertIn("remains active", message)
        self.assertEqual(calls, [{"reason": "user asked me to rest"}])

    def test_sleep_command_refuses_when_wake_word_is_disabled(self):
        calls = []
        ok, message = sleep_on_command(
            False,
            lambda: calls.append("ensure") or True,
            lambda **kwargs: calls.append(kwargs),
        )
        self.assertFalse(ok)
        self.assertIn("disabled", message)
        self.assertEqual(calls, [])

    def test_sleep_command_stays_awake_if_detector_cannot_start(self):
        calls = []
        ok, message = sleep_on_command(
            True,
            lambda: False,
            lambda **kwargs: calls.append(kwargs),
        )
        self.assertFalse(ok)
        self.assertIn("staying awake", message)
        self.assertEqual(calls, [])

    def test_directory_at_marker_path_fails_safely(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "wake_daemon.stop"
            marker.mkdir()
            self.assertFalse(clear_stale_stop_marker(marker))
            self.assertTrue(marker.is_dir())


if __name__ == "__main__":
    unittest.main()
