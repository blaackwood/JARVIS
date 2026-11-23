import unittest
from unittest.mock import patch

from core import screenview


MONITORS = [
    {"left": 0, "top": 0, "width": 2806, "height": 900},
    {"left": 1440, "top": 69, "width": 1366, "height": 768},
    {"left": 0, "top": 0, "width": 1440, "height": 900},
]


class FakeMSS:
    def __init__(self, monitors):
        self.monitors = monitors

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ScreenviewCoordinateTests(unittest.TestCase):
    def test_primary_is_selected_by_desktop_origin_not_enumeration_order(self):
        self.assertEqual(screenview._primary_monitor(MONITORS), MONITORS[2])

    def test_dpi_scale_uses_actual_primary_monitor(self):
        with patch.object(screenview, "_mss", return_value=FakeMSS(MONITORS)), \
             patch("pyautogui.size", return_value=(1440, 900)):
            self.assertAlmostEqual(screenview._physical_to_logical(), 1.0)

    def test_capture_fallback_selects_primary_monitor(self):
        with patch.object(screenview, "monitors", return_value=MONITORS):
            self.assertEqual(screenview.monitor_rect(), MONITORS[2])


if __name__ == "__main__":
    unittest.main()
