import unittest
from unittest.mock import patch

from actions import browser_control as browser


class DefaultBrowserDetectionTests(unittest.TestCase):
    def test_windows_program_ids_map_to_their_real_browsers(self):
        cases = {
            "ChromeHTML": "chrome",
            "MSEdgeHTM": "edge",
            "FirefoxURL-308046B0AF4A39CB": "firefox",
            "BraveHTML": "brave",
            "OperaStable": "opera",
            "OperaGXStable": "operagx",
            "VivaldiHTM": "vivaldi",
        }
        for prog_id, expected in cases.items():
            with self.subTest(prog_id=prog_id):
                self.assertEqual(browser._browser_from_identifier(prog_id), expected)

    def test_unknown_identifier_is_not_silently_replaced_with_chrome(self):
        self.assertIsNone(browser._browser_from_identifier("UnknownBrowserHTML"))

    def test_linux_unknown_default_does_not_guess_chrome(self):
        fake = type("Result", (), {"returncode": 0, "stdout": "unknown-browser.desktop"})()
        with patch.object(browser, "_OS", "Linux"), patch.object(browser.subprocess, "run", return_value=fake):
            self.assertIsNone(browser._detect_default_browser())

    def test_browser_instructions_do_not_refer_to_missing_screen_agent(self):
        description = browser.TOOL["description"]
        self.assertNotIn("call 'screen_agent'", description)
        self.assertIn("execute the steps sequentially with this tool", description)
        self.assertIn("screen_perception", description)
        self.assertIn("screen_process", description)

    def test_current_windows_default_is_detected_from_userchoice(self):
        if browser._OS != "Windows":
            self.skipTest("Windows registry is only available on Windows")
        detected = browser._detect_default_browser()
        self.assertIn(detected, {"chrome", "edge", "firefox", "opera", "operagx", "brave", "vivaldi"})


if __name__ == "__main__":
    unittest.main()
