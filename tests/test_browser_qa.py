import json
import tempfile
import unittest
from pathlib import Path

from core.browser_qa import _server_spec, audit_web_project, format_diagnostics


class BrowserQATests(unittest.TestCase):
    def test_non_web_folder_is_not_treated_as_a_web_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit_web_project(Path(tmp), visual_review=False)
        self.assertFalse(report["supported"])
        self.assertTrue(report["ok"])

    def test_static_html_is_detected_without_node_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                "<!doctype html><html lang='pt-BR'><head><title>Demo</title></head>"
                "<body><main><h1>Projeto de teste</h1>"
                "<button type='button' aria-label='Abrir'>Abrir</button></main></body></html>",
                encoding="utf-8",
            )
            spec = _server_spec(root)
            self.assertEqual(spec["kind"], "static")
            self.assertEqual(spec["framework"], "static")

    def test_arbitrary_npm_script_is_never_launched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "node_modules").mkdir()
            (root / "package.json").write_text(json.dumps({
                "scripts": {"dev": "python steal_data.py && vite"}
            }), encoding="utf-8")
            self.assertIsNone(_server_spec(root))

    def test_allowlisted_vite_script_is_recognized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "node_modules").mkdir()
            (root / "package.json").write_text(json.dumps({
                "scripts": {"dev": "cross-env NODE_ENV=development vite"}
            }), encoding="utf-8")
            spec = _server_spec(root)
            self.assertEqual(spec["kind"], "npm")
            self.assertEqual(spec["framework"], "vite")

    def test_static_browser_audit_captures_desktop_and_mobile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                "<!doctype html><html lang='pt-BR'><head><title>JARVIS QA</title>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<style>body{margin:0}main{max-width:900px;margin:auto;padding:24px}</style>"
                "</head><body><main><h1>Teste visual</h1>"
                "<p>Conteúdo suficiente para renderização.</p>"
                "<button type='button' aria-label='Ação segura'>Executar</button>"
                "</main></body></html>",
                encoding="utf-8",
            )
            report = audit_web_project(root, visual_review=False, server_timeout=5)
            self.assertTrue(report["supported"])
            self.assertTrue(report["ok"], report["diagnostics"])
            self.assertIn("desktop", report["page_summary"])
            self.assertIn("mobile", report["page_summary"])
            self.assertEqual(len(report["screenshots"]), 2)
            self.assertTrue(all(Path(p).is_file() for p in report["screenshots"]))
            self.assertTrue((Path(report["evidence_dir"]) / "report.json").is_file())

    def test_javascript_exception_fails_browser_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                "<!doctype html><html><head><title>Broken</title></head>"
                "<body><h1>Visible app</h1><script>throw new Error('QA_SENTINEL');</script>"
                "</body></html>",
                encoding="utf-8",
            )
            report = audit_web_project(root, visual_review=False, server_timeout=5)
            self.assertFalse(report["ok"])
            self.assertTrue(any("JavaScript" in d for d in report["diagnostics"]))
            self.assertIn("QA_SENTINEL", " ".join(report["page_errors"] + report["console_errors"]))

    def test_diagnostics_include_evidence_location(self):
        report = {
            "supported": True,
            "framework": "static",
            "summary": {"failed": 1},
            "diagnostics": ["No JavaScript console errors: ReferenceError"],
            "page_summary": {},
            "evidence_dir": "C:/qa/evidence",
            "visual_review": {"issues": []},
        }
        text = format_diagnostics(report)
        self.assertIn("ReferenceError", text)
        self.assertIn("C:/qa/evidence", text)

    def test_recognized_framework_without_node_modules_is_not_served_as_static(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<h1>Source only</h1>", encoding="utf-8")
            (root / "package.json").write_text(json.dumps({
                "scripts": {"dev": "vite"},
            }), encoding="utf-8")
            self.assertIsNone(_server_spec(root))

    def test_unknown_server_script_without_node_modules_is_not_served_as_static(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<h1>Source only</h1>", encoding="utf-8")
            (root / "package.json").write_text(json.dumps({
                "scripts": {"dev": "custom-server"},
            }), encoding="utf-8")
            self.assertIsNone(_server_spec(root))

    def test_external_scripts_are_blocked_and_cannot_be_called_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                "<!doctype html><html><head><title>Isolated</title></head><body>"
                "<h1>Local content</h1>"
                "<script src='https://example.invalid/remote.js'></script>"
                "<script>if (window.REMOTE_SCRIPT_RAN) document.body.dataset.remote='yes';</script>"
                "</body></html>", encoding="utf-8")
            report = audit_web_project(root, visual_review=False, server_timeout=5)
            self.assertFalse(report["ok"])
            self.assertTrue(any(item["resource_type"] == "script"
                                for item in report["external_requests_attempted"]))
            self.assertTrue(any("external network" in item.lower()
                                for item in report["diagnostics"]))

    def test_external_websockets_are_intercepted_before_connecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                "<!doctype html><html><head><title>WebSocket isolation</title></head><body>"
                "<h1>Local content</h1><script>new WebSocket('wss://example.invalid/socket');</script>"
                "</body></html>", encoding="utf-8")
            report = audit_web_project(root, visual_review=False, server_timeout=5)
            self.assertFalse(report["ok"])
            self.assertTrue(any(item["resource_type"] == "websocket"
                                for item in report["external_requests_attempted"]))


if __name__ == "__main__":
    unittest.main()
