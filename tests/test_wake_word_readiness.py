import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.wake_word import is_ready


class WakeWordReadinessTests(unittest.TestCase):
    def test_readiness_check_does_not_import_openwakeword_package(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "openwakeword"
            models = package / "resources" / "models"
            models.mkdir(parents=True)
            init_file = package / "__init__.py"
            init_file.write_text("# fake package location", encoding="utf-8")
            for name in (
                "hey_jarvis_v0.1.onnx",
                "melspectrogram.onnx",
                "embedding_model.onnx",
            ):
                (models / name).write_bytes(b"model")

            previous = sys.modules.pop("openwakeword", None)
            try:
                with patch(
                    "importlib.util.find_spec",
                    return_value=SimpleNamespace(origin=str(init_file)),
                ):
                    self.assertTrue(is_ready())
                self.assertNotIn("openwakeword", sys.modules)
            finally:
                if previous is not None:
                    sys.modules["openwakeword"] = previous

    def test_readiness_is_false_when_any_required_model_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "openwakeword"
            models = package / "resources" / "models"
            models.mkdir(parents=True)
            init_file = package / "__init__.py"
            init_file.write_text("# fake package location", encoding="utf-8")
            (models / "hey_jarvis_v0.1.onnx").write_bytes(b"model")
            with patch(
                "importlib.util.find_spec",
                return_value=SimpleNamespace(origin=str(init_file)),
            ):
                self.assertFalse(is_ready())


if __name__ == "__main__":
    unittest.main()
