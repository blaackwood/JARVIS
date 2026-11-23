import json
import unittest
from unittest.mock import patch

from core import screenview


class ScreenviewVirtualDesktopTests(unittest.TestCase):
    def test_model_payload_contains_virtual_and_active_monitor_bounds(self):
        view = screenview.View(
            app="chrome.exe", title="YouTube", source="uia", degraded=False,
            bounds=(0, 0, 1440, 900), window_rect=(1440, 69, 1366, 768),
        )
        virtual = {"left": 0, "top": 0, "width": 2806, "height": 900}
        active = {"left": 1440, "top": 0, "width": 1366, "height": 900}
        with patch.object(screenview, "virtual_rect", return_value=virtual), \
             patch.object(screenview, "monitor_rect", return_value=active):
            payload = json.loads(view.to_model_json())
        self.assertEqual(payload["virtual_screen"], virtual)
        self.assertEqual(payload["active_monitor"], active)


if __name__ == "__main__":
    unittest.main()
