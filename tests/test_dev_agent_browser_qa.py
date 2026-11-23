import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import dev_agent
from core import browser_qa


class DevAgentBrowserIntegrationTests(unittest.TestCase):
    def _project(self, root):
        (root / "index.html").write_text(
            "<!doctype html><html><head><title>Demo</title></head>"
            "<body><h1>Demo</h1><script src='app.js'></script></body></html>",
            encoding="utf-8",
        )
        (root / "app.js").write_text("console.log('before');\n", encoding="utf-8")

    def test_browser_targets_choose_the_file_named_in_diagnostics(self):
        written = {"index.html": "<h1>App</h1>", "styles.css": "body{}", "app.js": "ok"}
        report = {"diagnostics": ["app.js: uncaught JavaScript exception"]}
        self.assertEqual(dev_agent._browser_targets(written, report), ["app.js"])

    def test_browser_targets_prioritize_css_for_mobile_layout_failures(self):
        written = {"app.js": "ok", "styles.css": "body{}", "index.html": "<h1>App</h1>"}
        report = {"diagnostics": ["Mobile layout has horizontal overflow"]}
        self.assertEqual(dev_agent._browser_targets(written, report)[0], "styles.css")

    def test_new_web_build_passes_only_after_browser_report_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            passing = {
                "supported": True, "ok": True, "framework": "static",
                "summary": {"passed": 14, "failed": 0},
                "diagnostics": [], "evidence_dir": str(root / "evidence"),
                "visual_review": {"available": True, "issues": []},
            }
            with patch.object(browser_qa, "audit_web_project", side_effect=[passing, passing]) as audit:
                report = dev_agent._test_browser_build(
                    root, {"index.html": (root / "index.html").read_text(encoding="utf-8"),
                           "app.js": (root / "app.js").read_text(encoding="utf-8")},
                    [{"path": "index.html"}, {"path": "app.js"}],
                    "demo", "javascript", "index.html")
            self.assertTrue(report["ok"])
            self.assertEqual(audit.call_args_list[0].kwargs, {"visual_review": False})
            self.assertEqual(audit.call_args_list[1].kwargs, {"visual_review": True})

    def test_browser_failure_is_repaired_then_playwright_is_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            failing = {
                "supported": True, "ok": False, "framework": "static",
                "summary": {"passed": 12, "failed": 1},
                "diagnostics": ["No uncaught JavaScript exceptions: app.js ReferenceError"],
                "evidence_dir": str(root / "evidence-1"),
                "visual_review": {"available": True, "issues": []},
            }
            passing = {
                "supported": True, "ok": True, "framework": "static",
                "summary": {"passed": 14, "failed": 0},
                "diagnostics": [], "evidence_dir": str(root / "evidence-2"),
                "visual_review": {"available": True, "issues": []},
            }
            with patch.object(browser_qa, "audit_web_project", side_effect=[failing, passing, passing]) as audit, \
                 patch.object(dev_agent, "_fix_files", return_value={"app.js": "console.log('repaired');"}) as fix:
                report = dev_agent._test_browser_build(
                    root, {"index.html": (root / "index.html").read_text(encoding="utf-8"),
                           "app.js": (root / "app.js").read_text(encoding="utf-8")},
                    [{"path": "index.html"}, {"path": "app.js"}],
                    "demo", "javascript", "index.html")
            self.assertTrue(report["ok"])
            self.assertEqual(audit.call_count, 3)
            self.assertEqual([call.kwargs["visual_review"] for call in audit.call_args_list],
                             [False, False, True])
            self.assertEqual(fix.call_count, 1)
            self.assertEqual(fix.call_args.kwargs["entry_point"], "app.js")

    def test_unsupported_web_server_is_not_reported_as_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            unsupported = {"supported": False, "ok": True,
                           "reason": "No safe server detected."}
            with patch.object(browser_qa, "audit_web_project", return_value=unsupported), \
                 patch.object(dev_agent, "_fix_files", return_value={}) as fix:
                report = dev_agent._test_browser_build(
                    root, {"index.html": (root / "index.html").read_text(encoding="utf-8"),
                           "app.js": (root / "app.js").read_text(encoding="utf-8")},
                    [{"path": "index.html"}, {"path": "app.js"}],
                    "demo", "javascript", "index.html")
            fix.assert_not_called()
            self.assertTrue(report["supported"])
            self.assertFalse(report["ok"])
            self.assertGreater(report["summary"]["failed"], 0)

    def test_existing_web_project_is_marked_unverified_if_safe_server_is_unknown(self):
        from core import code_checks
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            written = {
                "index.html": (root / "index.html").read_text(encoding="utf-8"),
                "app.js": (root / "app.js").read_text(encoding="utf-8"),
            }
            changes = [{"path": "index.html"}, {"path": "app.js"}]
            unsupported = {"supported": False, "ok": True,
                           "reason": "No safe server detected."}
            with patch.object(code_checks, "static_problems", return_value={}), \
                 patch.object(code_checks, "runtime_problems", return_value={}), \
                 patch.object(browser_qa, "audit_web_project", return_value=unsupported):
                result = dev_agent._test_and_fix(
                    root, written, changes, {}, "test", "", None,
                    stack={"test_cmd": None}, originals={}, baseline=None)
            self.assertIn("Browser QA (unverified)", result)
            self.assertIn("remains unverified", result["Browser QA (unverified)"])


    def test_major_visual_finding_is_repaired_then_visually_rechecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root)
            (root / "styles.css").write_text("main { width: 1200px; }\n", encoding="utf-8")
            technical_pass = {
                "supported": True, "ok": True, "framework": "static",
                "summary": {"passed": 14, "failed": 0},
                "diagnostics": [], "evidence_dir": str(root / "technical"),
                "visual_review": {"available": False, "issues": []},
            }
            visual_fail = {
                "supported": True, "ok": False, "framework": "static",
                "summary": {"passed": 14, "failed": 1},
                "diagnostics": ["Visual review: mobile defect 1: content is clipped off the right edge."],
                "evidence_dir": str(root / "visual-fail"),
                "visual_review": {"available": True, "issues": [{
                    "severity": "major", "screen": "mobile",
                    "issue": "Content is clipped off the right edge.",
                    "suggested_fix": "Use a fluid width and max-width.",
                }]},
            }
            visual_pass = {
                **technical_pass,
                "evidence_dir": str(root / "visual-pass"),
                "visual_review": {"available": True, "issues": []},
            }
            with patch.object(browser_qa, "audit_web_project",
                              side_effect=[technical_pass, visual_fail, technical_pass, visual_pass]) as audit, \
                 patch.object(dev_agent, "_fix_files",
                              return_value={"styles.css": "main { width: 100%; max-width: 1200px; }\n"}) as fix:
                report = dev_agent._test_browser_build(
                    root,
                    {"index.html": (root / "index.html").read_text(encoding="utf-8"),
                     "app.js": (root / "app.js").read_text(encoding="utf-8"),
                     "styles.css": (root / "styles.css").read_text(encoding="utf-8")},
                    [{"path": "index.html"}, {"path": "app.js"}, {"path": "styles.css"}],
                    "demo", "javascript", "app.js")
            self.assertTrue(report["ok"])
            self.assertEqual([call.kwargs["visual_review"] for call in audit.call_args_list],
                             [False, True, False, True])
            self.assertEqual(fix.call_args.kwargs["entry_point"], "styles.css")



if __name__ == "__main__":
    unittest.main()
