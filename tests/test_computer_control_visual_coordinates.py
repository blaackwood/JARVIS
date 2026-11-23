import json
import unittest
from unittest.mock import patch

from actions.computer_control import (
    _prepare_visual_screen,
    _screen_pixel_to_mouse,
    computer_control,
)


class ComputerControlVisualCoordinatesTests(unittest.TestCase):
    def test_second_monitor_coordinates_are_offset_into_virtual_desktop(self):
        point = _screen_pixel_to_mouse(
            600, 300, 1366, 768,
            {"left": 1440, "top": 69, "width": 1366, "height": 768},
            1.0,
            {"left": 0, "top": 0, "width": 2806, "height": 900},
        )
        self.assertEqual(point, (2040, 369))

    def test_mixed_dpi_screenshot_coordinates_are_scaled(self):
        point = _screen_pixel_to_mouse(
            600, 300, 2732, 1536,
            {"left": 1440, "top": 0, "width": 1366, "height": 768},
            2.0,
            {"left": 0, "top": 0, "width": 2806, "height": 900},
        )
        self.assertEqual(point, (1740, 150))

    def test_visual_click_keeps_purchase_block(self):
        result = computer_control({"action": "screen_click", "description": "Checkout"})
        self.assertIn("PURCHASE_BLOCKED", result)

    def test_out_of_bounds_visual_point_is_rejected(self):
        self.assertIsNone(_screen_pixel_to_mouse(
            1400, 20, 1366, 768,
            {"left": 1440, "top": 0, "width": 1366, "height": 768},
            1.0,
            {"left": 0, "top": 0, "width": 2806, "height": 900},
        ))

    def test_minimizes_visible_jarvis_overlay_even_when_chrome_is_foreground(self):
        from types import SimpleNamespace
        browser = SimpleNamespace(source="uia", app="chrome.exe")
        fresh = SimpleNamespace(source="uia", app="chrome.exe")
        with (
            patch("core.screenview.look", side_effect=[browser, fresh]) as look,
            patch("actions.computer_control._minimize_jarvis_window",
                  return_value="JARVIS minimized: main window"),
            patch("actions.computer_control.time.sleep"),
        ):
            result = _prepare_visual_screen()
        self.assertIs(result, fresh)
        self.assertEqual(look.call_count, 2)

    def test_refuses_visual_search_if_jarvis_is_foreground_and_cannot_be_hidden(self):
        from types import SimpleNamespace
        self_view = SimpleNamespace(source="self", app="pythonw.exe")
        with (
            patch("core.screenview.look", return_value=self_view),
            patch("actions.computer_control._minimize_jarvis_window",
                  return_value="JARVIS window not found"),
        ):
            self.assertIsNone(_prepare_visual_screen())


if __name__ == "__main__":
    unittest.main()
