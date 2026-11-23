import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gui.window import MainWindow


class FirstRunApiGateTests(unittest.TestCase):
    def test_missing_key_keeps_setup_locked(self):
        with patch("gui.window._read_full_config", return_value={}):
            self.assertFalse(MainWindow._check_config(SimpleNamespace()))

    def test_short_key_keeps_setup_locked(self):
        config = {"os_system": "windows", "gemini_api_key": "short"}
        with patch("gui.window._read_full_config", return_value=config):
            self.assertFalse(MainWindow._check_config(SimpleNamespace()))

    def test_local_only_without_personal_key_stays_locked(self):
        config = {"os_system": "windows", "local_only": True}
        with patch("gui.window._read_full_config", return_value=config):
            self.assertFalse(MainWindow._check_config(SimpleNamespace()))


    def test_validated_personal_key_remains_valid_when_local_mode_is_selected(self):
        config = {
            "os_system": "windows",
            "gemini_api_key": "AIza" + "x" * 35,
            "local_only": True,
            "providers": {"mode": "pipeline"},
        }
        with patch("gui.window._read_full_config", return_value=config):
            self.assertTrue(MainWindow._check_config(SimpleNamespace()))

    def test_complete_personal_key_releases_setup_gate(self):
        config = {
            "os_system": "windows",
            "gemini_api_key": "AIza" + "x" * 35,
            "local_only": False,
        }
        with patch("gui.window._read_full_config", return_value=config):
            self.assertTrue(MainWindow._check_config(SimpleNamespace()))

    def test_setup_cannot_be_saved_without_validation_flag(self):
        with self.assertRaisesRegex(ValueError, "validated"):
            MainWindow._on_setup_done(
                SimpleNamespace(), "AIza" + "x" * 35, "Windows"
            )


if __name__ == "__main__":
    unittest.main()
