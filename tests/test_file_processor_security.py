import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from actions import file_processor as fp
from core import authorization


class SelectedFile:
    def __init__(self, path=None):
        self.current_file = str(path) if path is not None else None

    def write_log(self, message):
        pass


class FileProcessorSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_the_file_selected_in_jarvis_is_accepted(self):
        selected = self.root / "selected.txt"
        other = self.root / "other.txt"
        selected.write_text("selected content", encoding="utf-8")
        other.write_text("other content", encoding="utf-8")

        path, kind, error = fp._validate_file_request(str(selected), SelectedFile(selected))
        self.assertEqual(path, selected.resolve())
        self.assertEqual(kind, "text")
        self.assertEqual(error, "")

        path, kind, error = fp._validate_file_request(str(other), SelectedFile(selected))
        self.assertIsNone(path)
        self.assertIn("does not match", error)

    def test_missing_selection_is_refused(self):
        selected = self.root / "sample.txt"
        selected.write_text("sample", encoding="utf-8")
        path, kind, error = fp._validate_file_request(str(selected), SelectedFile())
        self.assertIsNone(path)
        self.assertIn("Select or drop", error)

    def test_empty_and_oversized_files_are_refused(self):
        empty = self.root / "empty.txt"
        empty.write_bytes(b"")
        self.assertIn("empty", fp._validate_file_request(str(empty))[2].lower())

        large = self.root / "large.txt"
        with large.open("wb") as stream:
            stream.truncate(fp.MAX_FILE_BYTES["text"] + 1)
        self.assertIn("too large", fp._validate_file_request(str(large))[2].lower())

    def test_image_signature_and_dimensions_are_validated(self):
        fake = self.root / "fake.png"
        fake.write_text("not a png", encoding="utf-8")
        self.assertIn("Image validation failed",
                      fp._validate_file_request(str(fake))[2])

        valid = self.root / "valid.png"
        Image.new("RGB", (32, 24), "white").save(valid)
        path, kind, error = fp._validate_file_request(str(valid))
        self.assertEqual(path, valid.resolve())
        self.assertEqual(kind, "image")
        self.assertEqual(error, "")

    def test_pdf_signature_is_validated(self):
        fake = self.root / "fake.pdf"
        fake.write_bytes(b"not a PDF document")
        self.assertIn("not a PDF", fp._validate_file_request(str(fake))[2])

    def test_read_only_image_analysis_does_not_save_by_default(self):
        image = self.root / "sample.png"
        Image.new("RGB", (20, 20), "white").save(image)
        response = Mock()
        response.text = "A" * 700
        model = Mock()
        model.generate_content.return_value = response
        with patch.object(fp, "_gemini_client", return_value=model):
            result = fp.file_processor(
                {"file_path": str(image), "action": "describe"},
                player=SelectedFile(image))
        self.assertTrue(result)
        self.assertFalse((self.root / "sample_result.txt").exists())
        sent_parts = model.generate_content.call_args.args[0]
        image_part = sent_parts[1]
        self.assertIsNotNone(getattr(image_part, "inline_data", None))
        self.assertEqual(image_part.inline_data.mime_type, "image/png")
        self.assertTrue(image_part.inline_data.data)
        from core.gemini import _to_live_parts
        live_parts = _to_live_parts(sent_parts)
        self.assertIn("inline_data", live_parts[1])
        self.assertTrue(live_parts[1]["inline_data"]["data"])

    def test_translation_uses_selected_image_when_model_omits_path(self):
        image = self.root / "selected.png"
        Image.new("RGB", (24, 24), "white").save(image)
        response = Mock()
        response.text = "Translated text"
        model = Mock()
        model.generate_content.return_value = response
        with patch.object(fp, "_gemini_client", return_value=model):
            result = fp.file_processor({"action": "translate"}, player=SelectedFile(image))
        self.assertIn("Translated text", result)
        prompt_parts = model.generate_content.call_args.args[0]
        self.assertIn("Brazilian Portuguese", prompt_parts[0])

    def test_file_processor_actions_are_classified_by_side_effect(self):
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/photo.png", "action": "describe"}),
            "read_only")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"action": "translate"}), "read_only")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/photo.png", "action": "translate"}),
            "read_only")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/report.pdf", "action": "summarize"}),
            "read_only")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/scanned.pdf", "action": "ocr"}),
            "read_only")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/report.pdf", "action": "extract_text"}),
            "destructive_change")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/photo.png", "action": "resize"}),
            "destructive_change")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/photo.png", "action": "describe", "save": True}),
            "destructive_change")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/script.py", "action": "run"}),
            "unknown_high_impact")
        self.assertEqual(authorization.classify_action(
            "file_processor", {"file_path": "C:/upload/unknown.bin", "action": "analyze"}),
            "unknown_high_impact")


if __name__ == "__main__":
    unittest.main()
