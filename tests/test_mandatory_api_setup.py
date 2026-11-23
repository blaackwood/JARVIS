"""Regression tests for the mandatory per-installation Gemini key setup."""
import unittest
from unittest.mock import MagicMock, patch

from core.api_key_validation import validate_gemini_api_key


class GeminiKeyValidationTests(unittest.TestCase):
    def test_rejects_empty_or_malformed_key_without_network(self):
        valid, message = validate_gemini_api_key("short key")
        self.assertFalse(valid)
        self.assertIn("complete Gemini API key", message)

    def test_accepts_key_when_google_model_listing_succeeds(self):
        fake_client = MagicMock()
        fake_client.models.list.return_value = iter([object()])
        with patch("google.genai.Client", return_value=fake_client):
            valid, message = validate_gemini_api_key("A" * 40)
        self.assertTrue(valid)
        self.assertIn("accepted", message)
        fake_client.close.assert_called_once()

    def test_rejects_key_refused_by_google(self):
        fake_client = MagicMock()
        fake_client.models.list.side_effect = RuntimeError("API key not valid")
        with patch("google.genai.Client", return_value=fake_client):
            valid, message = validate_gemini_api_key("A" * 40)
        self.assertFalse(valid)
        self.assertIn("Google rejected", message)


class MandatorySetupGateTests(unittest.TestCase):
    def test_local_only_choice_cannot_skip_first_run_key_requirement(self):
        from gui.window import MainWindow
        settings = {"os_system": "Windows", "local_only": True}
        with patch("gui.window._read_full_config", return_value=settings):
            self.assertFalse(MainWindow._check_config(None))

    def test_own_key_satisfies_setup_even_if_alternate_engine_is_selected(self):
        from gui.window import MainWindow
        settings = {
            "os_system": "Windows",
            "gemini_api_key": "A" * 40,
            "local_only": True,
            "providers": {"mode": "pipeline"},
        }
        with patch("gui.window._read_full_config", return_value=settings):
            self.assertTrue(MainWindow._check_config(None))


if __name__ == "__main__":
    unittest.main()
