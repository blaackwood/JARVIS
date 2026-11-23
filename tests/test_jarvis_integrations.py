import tempfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from plugins import exam_lab, github_account
from core.plugin_loader import discover_plugins


def fake_second_reviewer(_page, _number, questions):
    return {
        idx: {
            "provider": "Cloud provider test double",
            "status": "complete",
            "issues": [],
            "notes": "Mocked second-pass result",
        }
        for idx, _question in enumerate(questions, 1)
    }


class ExamLabTests(unittest.TestCase):
    def test_exam_cloud_calls_google_directly_with_pinned_free_model(self):
        class FakeModels:
            def generate_content(self, **kwargs):
                self.kwargs = kwargs
                return "ok"
        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        fake = FakeClient()
        with patch.object(exam_lab.gemini, "api_key", return_value="test-key"):
            with patch.object(exam_lab.gemini, "client", return_value=fake) as client_factory:
                with patch.object(exam_lab.gemini, "call") as cloud_fallback:
                    result = exam_lab._exam_cloud_call(["prompt", "image"], timeout_ms=12345)

        self.assertEqual(result, "ok")
        client_factory.assert_called_once_with(timeout_ms=12345, key="test-key", retry_attempts=1)
        self.assertEqual(fake.models.kwargs, {
            "model": "gemini-3.1-flash-lite", "contents": ["prompt", "image"]
        })
        cloud_fallback.assert_not_called()

    def test_exam_cloud_quota_uses_configured_remote_vision_provider(self):
        class FakeModels:
            def generate_content(self, **_kwargs):
                raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        expected = type("Reply", (), {"text": '{"color":"red"}'})()
        with patch.object(exam_lab.gemini, "api_key", return_value="test-key"):
            with patch.object(exam_lab.gemini, "client", return_value=FakeClient()):
                with patch("memory.config_manager.get_providers", return_value={
                    "coding": "openai_compat@nvidia_nemotron", "sidecar": ""
                }):
                    with patch("memory.config_manager.get_provider_config", return_value={
                        "base_url": "https://api.example.test/v1",
                        "model": "nvidia/nemotron-super-vl",
                    }):
                        with patch.object(exam_lab.gemini, "call", return_value=expected) as fallback:
                            result = exam_lab._exam_cloud_call(["prompt", "image"], timeout_ms=23456)

        self.assertIs(result, expected)
        fallback.assert_called_once()
        self.assertEqual(fallback.call_args.kwargs["tier"], exam_lab.gemini.SMART)
        self.assertEqual(fallback.call_args.kwargs["provider"], "openai_compat@nvidia_nemotron")
        self.assertEqual(fallback.call_args.kwargs["timeout_ms"], 23456)

    def test_exam_cloud_quota_never_falls_back_to_a_local_provider(self):
        class FakeModels:
            def generate_content(self, **_kwargs):
                raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        with patch.object(exam_lab.gemini, "api_key", return_value="test-key"):
            with patch.object(exam_lab.gemini, "client", return_value=FakeClient()):
                with patch("memory.config_manager.get_providers", return_value={
                    "coding": "openai_compat@ollama", "sidecar": ""
                }):
                    with patch("memory.config_manager.get_provider_config", return_value={
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model": "llava:7b", "vision": "1",
                    }):
                        with patch.object(exam_lab.gemini, "call") as fallback:
                            with self.assertRaisesRegex(RuntimeError, "no configured remote vision provider"):
                                exam_lab._exam_cloud_call(["prompt", "image"])
        fallback.assert_not_called()

    def test_configured_cloud_vision_provider_skips_http_and_uses_vision_flag(self):
        configs = {
            "coding-http": {
                "base_url": "http://api.example.test/v1",
                "model": "vendor/model-vl",
            },
            "sidecar-cloud": {
                "base_url": "https://api.example.test/v1",
                "model": "vendor/general-model",
                "vision": "true",
            },
        }
        with patch("memory.config_manager.get_providers", return_value={
            "coding": "coding-http", "sidecar": "sidecar-cloud"
        }):
            with patch("memory.config_manager.get_provider_config",
                       side_effect=lambda provider_id: configs[provider_id]):
                self.assertEqual(
                    exam_lab._configured_cloud_vision_provider(),
                    "sidecar-cloud",
                )

    def test_configured_cloud_vision_provider_rejects_https_text_only_model(self):
        with patch("memory.config_manager.get_providers", return_value={
            "coding": "coding-text-only", "sidecar": ""
        }):
            with patch("memory.config_manager.get_provider_config", return_value={
                "base_url": "https://api.example.test/v1",
                "model": "vendor/general-chat",
            }):
                self.assertEqual(exam_lab._configured_cloud_vision_provider(), "")

    def test_exam_cloud_does_not_fallback_for_non_quota_provider_error(self):
        class FakeModels:
            def generate_content(self, **_kwargs):
                raise RuntimeError("503 service temporarily unavailable")

        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        with patch.object(exam_lab.gemini, "api_key", return_value="test-key"):
            with patch.object(exam_lab.gemini, "client", return_value=FakeClient()):
                with patch.object(exam_lab, "_configured_cloud_vision_provider") as select_provider:
                    with patch.object(exam_lab.gemini, "call") as cloud_fallback:
                        with self.assertRaisesRegex(RuntimeError, "503 service"):
                            exam_lab._exam_cloud_call(["prompt", "image"])

        select_provider.assert_not_called()
        cloud_fallback.assert_not_called()

    def test_cloud_failure_keeps_second_review_pending_for_cloud_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.png"
            Image.new("RGB", (500, 700), "white").save(source)

            def fake_analyzer(page, number):
                return {"questions": [{
                    "number": "1", "text": "Question",
                    "bbox": [100, 100, 900, 500], "confidence": 0.9,
                }]}, page

            with patch.object(exam_lab, "_cloud_second_review",
                              side_effect=TimeoutError("cloud unavailable")):
                folder, manifest = exam_lab.prepare_exam(
                    source, root / "out", analyzer=fake_analyzer,
                )
            self.assertEqual(manifest["questions"][0]["second_review"]["status"], "pending_cloud")
            self.assertTrue((folder / "review.html").is_file())
            review = (folder / "review.html").read_text(encoding="utf-8")
            self.assertIn("Revisao em nuvem pendente", review)

    def test_first_pass_quota_skips_page_without_local_ai(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.png"
            Image.new("RGB", (500, 700), "white").save(source)
            with patch.object(exam_lab, "_analyze_page",
                              side_effect=RuntimeError("Gemini quota exceeded; cloud fallbacks unavailable")):
                _folder, manifest = exam_lab.prepare_exam(source, root / "out")
            self.assertEqual(manifest["questions"], [])
            self.assertTrue(any("without local AI" in warning for warning in manifest["warnings"]))

    def test_box_coordinates_are_clamped_to_image(self):
        self.assertEqual(exam_lab._box_pixels([0, 0, 1000, 1000], 100, 200), (0, 0, 100, 200))

    def test_invalid_box_rejected(self):
        for box in ([0, 0, 0, 20], [0, 0, 1001, 20], [0, 0, 1], [0, 0, 0.01, 0.01]):
            with self.assertRaises(ValueError):
                exam_lab._box_pixels(box, 100, 100)

    def test_overlap(self):
        self.assertTrue(exam_lab._overlap((0, 0, 20, 20), (10, 10, 30, 30)))
        self.assertFalse(exam_lab._overlap((0, 0, 10, 10), (10, 10, 20, 20)))

    def test_prepare_creates_review_and_pending_manifest_with_second_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.png"
            Image.new("RGB", (500, 700), "white").save(source)

            def fake_analyzer(page, number):
                return {
                    "questions": [{
                        "number": "1", "text": "2+2?",
                        "alternatives": ["A) 4"],
                        "bbox": [100, 100, 900, 500],
                        "confidence": 0.95,
                    }]
                }, page

            folder, manifest = exam_lab.prepare_exam(
                source, root / "out", analyzer=fake_analyzer,
                second_reviewer=fake_second_reviewer,
            )
            self.assertTrue((folder / "review.html").is_file())
            self.assertTrue((folder / "questions.json").is_file())
            self.assertEqual(len(manifest["questions"]), 1)
            q = manifest["questions"][0]
            self.assertEqual(q["review_status"], "pending_review")
            self.assertEqual(q["second_review"]["status"], "complete")
            self.assertTrue((folder / q["crop_image"]).is_file())
            self.assertTrue((folder / q["page_image"]).is_file())
            self.assertFalse(manifest["pipeline"]["openai_api_used"])
            review_html = (folder / "review.html").read_text(encoding="utf-8")
            self.assertIn("Segundo modelo", review_html)

    def test_pdf_input_renders_pages_and_exports_crops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "two_pages.pdf"
            first = Image.new("RGB", (500, 700), "white")
            second = Image.new("RGB", (500, 700), "white")
            first.save(source, format="PDF", save_all=True, append_images=[second], resolution=96)

            def fake_analyzer(page, number):
                return {
                    "questions": [{
                        "number": str(number), "text": "Question",
                        "bbox": [100, 100, 900, 700], "confidence": 0.9,
                    }]
                }, page

            folder, manifest = exam_lab.prepare_exam(
                source, root / "out", analyzer=fake_analyzer,
                second_reviewer=fake_second_reviewer,
            )
            self.assertEqual(len(manifest["questions"]), 2)
            self.assertTrue((folder / "pages/page_002.jpg").is_file())
            self.assertTrue((folder / "crops/page_002_question_001.png").is_file())
            self.assertTrue(all(q["second_review"]["status"] == "complete" for q in manifest["questions"]))

    def test_shared_context_links_to_questions_on_following_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "two_pages.pdf"
            first = Image.new("RGB", (500, 700), "white")
            second = Image.new("RGB", (500, 700), "white")
            first.save(source, format="PDF", save_all=True, append_images=[second], resolution=96)

            def fake_analyzer(page, number):
                questions = [{
                    "number": "01" if number == 1 else "02",
                    "text": "Question uses shared text",
                    "bbox": [100, 100, 900, 700], "confidence": 0.9,
                }]
                contexts = [{
                    "id": "passage_01_02", "kind": "shared_passage",
                    "applies_to_numbers": ["01"], "applies_to_range": [1, 2],
                    "bbox": [0, 0, 500, 300], "confidence": 0.95,
                    "notes": "Shared reading passage",
                }] if number == 1 else []
                return {"questions": questions, "shared_contexts": contexts}, page

            folder, manifest = exam_lab.prepare_exam(
                source, root / "out", analyzer=fake_analyzer,
                second_reviewer=fake_second_reviewer,
            )
            self.assertEqual(len(manifest["context_groups"]), 1)
            self.assertTrue((folder / manifest["context_groups"][0]["image"]).is_file())
            for q in manifest["questions"]:
                self.assertEqual(q["context_images"], [manifest["context_groups"][0]["image"]])
            self.assertIn("context_images", manifest["questions"][1])
            self.assertIn("Contexto compartilhado associado", (folder / "review.html").read_text(encoding="utf-8"))

    def test_second_reviewer_failure_does_not_discard_gemini_crops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.png"
            Image.new("RGB", (500, 700), "white").save(source)

            def fake_analyzer(page, number):
                return {"questions": [{
                    "number": "1", "text": "Question",
                    "bbox": [100, 100, 900, 500], "confidence": 0.9,
                }]}, page

            def failing_reviewer(*_args):
                raise TimeoutError("local model timed out")

            folder, manifest = exam_lab.prepare_exam(
                source, root / "out", analyzer=fake_analyzer,
                second_reviewer=failing_reviewer,
            )
            self.assertEqual(len(manifest["questions"]), 1)
            self.assertEqual(manifest["questions"][0]["second_review"]["status"], "unavailable")
            self.assertTrue((folder / manifest["questions"][0]["crop_image"]).is_file())
            self.assertTrue(manifest["warnings"])


class GitHubPluginTests(unittest.TestCase):
    def test_repo_validation(self):
        self.assertTrue(github_account._REPO.fullmatch("owner/repo"))
        self.assertFalse(github_account._REPO.fullmatch("../repo"))
        self.assertFalse(github_account._REPO.fullmatch("owner/repo/other"))

    def test_plugins_load_and_github_settings_action_is_callable(self):
        registry = discover_plugins(Path("plugins"), set(), logger=lambda _: None)
        rows = {x["name"]: x for x in registry.list_for_ui()}
        self.assertTrue(rows["github_account"]["valid"])
        self.assertTrue(rows["exam_lab"]["valid"])
        sections = registry.settings_schemas()
        github = next(x for x in sections if x["namespace"] == "github_account")
        self.assertTrue(callable(github["action"]["run"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
