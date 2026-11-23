import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from actions import file_processor as fp


class PdfOcrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _make_scanned_pdf(self, name="scanned.pdf", pages=1):
        images = []
        for index in range(pages):
            image = Image.new("RGB", (800, 1100), "white")
            ImageDraw.Draw(image).text((60, 80), f"SCANNED PAGE {index + 1}", fill="black")
            images.append(image)
        path = self.root / name
        images[0].save(path, format="PDF", save_all=True, append_images=images[1:])
        for image in images:
            image.close()
        return path

    @staticmethod
    def _model(*responses):
        model = Mock()
        model.generate_content.side_effect = [
            Mock(text=response) for response in responses
        ]
        return model

    def test_ocr_renders_scanned_page_and_sends_inline_image(self):
        path = self._make_scanned_pdf()
        model = self._model("SCANNED-731")
        with patch.object(fp, "_gemini_client", return_value=model):
            result = fp._process_pdf(path, "ocr", {})
        self.assertEqual(result, "SCANNED-731")
        self.assertEqual(model.generate_content.call_count, 1)
        parts = model.generate_content.call_args.args[0]
        image_parts = [part for part in parts if getattr(part, "inline_data", None)]
        self.assertEqual(len(image_parts), 1)
        self.assertEqual(image_parts[0].inline_data.mime_type, "image/png")
        self.assertTrue(image_parts[0].inline_data.data)

    def test_ocr_page_limit_is_enforced_and_reported(self):
        path = self._make_scanned_pdf(pages=3)
        model = self._model("PAGE-1", "PAGE-2")
        with patch.object(fp, "_gemini_client", return_value=model), \
             patch.object(fp, "PDF_OCR_MAX_PAGES", 2), \
             patch.object(fp, "PDF_OCR_BATCH_SIZE", 1):
            result = fp._ocr_pdf_text(path)
        self.assertEqual(model.generate_content.call_count, 2)
        self.assertIn("PAGE-1", result)
        self.assertIn("PAGE-2", result)
        self.assertIn("first 2 of 3 pages", result)

    def test_summarize_automatically_uses_ocr_for_image_only_pdf(self):
        path = self._make_scanned_pdf()
        model = self._model("OCR TEXT FROM SCAN", "Summary of scanned document")
        with patch.object(fp, "_gemini_client", return_value=model):
            result = fp._process_pdf(path, "summarize", {})
        self.assertEqual(result, "Summary of scanned document")
        self.assertEqual(model.generate_content.call_count, 2)
        first_payload = model.generate_content.call_args_list[0].args[0]
        self.assertTrue(any(getattr(part, "inline_data", None) for part in first_payload))

    def test_explicit_ocr_does_not_save_unless_requested(self):
        path = self._make_scanned_pdf()
        model = self._model("Recognized words")
        with patch.object(fp, "_gemini_client", return_value=model):
            result = fp._process_pdf(path, "ocr", {})
        self.assertEqual(result, "Recognized words")
        self.assertFalse((self.root / "scanned_ocr.txt").exists())


if __name__ == "__main__":
    unittest.main()
