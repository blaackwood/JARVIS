import unittest
from unittest.mock import patch

from core.api_key_validation import validate_gemini_api_key


class GeminiApiKeyValidationTests(unittest.TestCase):
    def test_rejects_empty_or_short_key_without_network(self):
        with patch("core.api_key_validation.genai.Client") as client:
            ok, message = validate_gemini_api_key("  ")
            self.assertFalse(ok)
            self.assertIn("complete", message.lower())
            client.assert_not_called()

    @patch("core.api_key_validation.genai.Client")
    def test_accepts_key_after_model_list_request(self, client_factory):
        client = client_factory.return_value
        client.models.list.return_value = [object()]

        ok, message = validate_gemini_api_key("AIza" + "x" * 35)

        self.assertTrue(ok)
        self.assertIn("accepted", message.lower())
        client.models.list.assert_called_once()

    @patch("core.api_key_validation.genai.Client")
    def test_rejects_invalid_key_without_disclosing_it(self, client_factory):
        client = client_factory.return_value
        error = RuntimeError("API key not valid")
        error.code = 400
        client.models.list.side_effect = error
        secret = "AIza" + "s" * 35

        ok, message = validate_gemini_api_key(secret)

        self.assertFalse(ok)
        self.assertIn("rejected", message.lower())
        self.assertNotIn(secret, message)

    @patch("core.api_key_validation.genai.Client")
    def test_reports_quota_exhaustion(self, client_factory):
        client = client_factory.return_value
        error = RuntimeError("RESOURCE_EXHAUSTED: quota exceeded")
        error.code = 429
        client.models.list.side_effect = error

        ok, message = validate_gemini_api_key("AIza" + "q" * 35)

        self.assertFalse(ok)
        self.assertIn("quota", message.lower())


if __name__ == "__main__":
    unittest.main()
