import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "_jarvis_agent_ui" / "server.py"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


class JarvisAgentUILiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="jarvis-agent-live-")
        cls.workspace = Path(cls.temp.name) / "workspace"
        cls.workspace.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = "http://127.0.0.1:%d" % cls.port
        env = dict(os.environ, PYTHONUTF8="1")
        cls.process = subprocess.Popen(
            [str(PYTHON), str(SERVER), "--no-open", "--port", str(cls.port),
             "--ws", str(cls.workspace)],
            cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 12
        cls.html = None
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError("Agent server exited during startup: %s" %
                                   cls.process.stderr.read().decode("utf-8", "replace")[-2000:])
            try:
                response = requests.get(cls.base + "/", timeout=0.4)
                if response.status_code == 200:
                    cls.html = response.text
                    break
            except requests.RequestException:
                pass
            time.sleep(0.1)
        if cls.html is None:
            cls.process.terminate()
            raise RuntimeError("Agent UI server did not become ready")
        match = re.search(r'<meta name="tk" content="([^"]+)"', cls.html)
        if not match:
            raise RuntimeError("Session token was not injected into the HTML")
        cls.token = match.group(1)
        cls.headers = {"X-Token": cls.token}

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "process", None) and cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=3)
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def test_main_page_and_static_assets_are_served(self):
        self.assertIn("<title>JARVIS — Agente</title>", self.html)
        for asset in ("app.js", "style.css", "extra.css", "icons.js"):
            response = requests.get(self.base + "/" + asset, timeout=5)
            self.assertEqual(response.status_code, 200, asset)
            self.assertGreater(len(response.content), 100, asset)

    def test_api_requires_session_token_and_rejects_foreign_host_and_origin(self):
        self.assertEqual(requests.get(self.base + "/api/state", timeout=5).status_code, 401)
        headers = dict(self.headers, Host="evil.example")
        self.assertEqual(requests.get(self.base + "/api/state", headers=headers, timeout=5).status_code, 403)
        headers = dict(self.headers, Origin="http://evil.example")
        self.assertEqual(requests.get(self.base + "/api/state", headers=headers, timeout=5).status_code, 403)

    def test_state_and_tree_api_are_available_without_exposing_secrets(self):
        response = requests.get(self.base + "/api/state", headers=self.headers, timeout=10)
        self.assertEqual(response.status_code, 200, response.text[:500])
        state = response.json()
        self.assertEqual(Path(state["ws"]).resolve(), self.workspace.resolve())
        self.assertIn("tasks", state)
        self.assertIn("providers", state)
        self.assertNotIn("api_key", response.text.lower())
        tree = requests.get(self.base + "/api/tree?path=.",
                            headers=self.headers, timeout=5)
        self.assertEqual(tree.status_code, 200, tree.text[:500])
        self.assertIsInstance(tree.json().get("items"), list)

    def test_agent_source_files_are_utf8_without_replacement_characters(self):
        root = ROOT / "_jarvis_agent_ui"
        for rel in ("server.py", "static/app.js", "static/index.html",
                    "static/style.css", "static/extra.css", "desktop/main.js"):
            with self.subTest(file=rel):
                text = (root / rel).read_text(encoding="utf-8")
                self.assertNotIn("\ufffd", text)

    def test_secret_and_git_metadata_paths_are_blocked(self):
        for path in (str(ROOT / "config" / "api_keys.json"),
                     str(ROOT / ".git" / "config")):
            response = requests.get(self.base + "/api/file",
                                    params={"path": path},
                                    headers=self.headers, timeout=5)
            self.assertEqual(response.status_code, 500, path)
            self.assertNotIn('"api_key"', response.text.lower())

    def test_browser_ui_renders_tabs_and_remains_responsive_without_console_errors(self):
        console_errors = []
        page_errors = []
        failed_requests = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.on("console", lambda msg: console_errors.append(msg.text[:400])
                        if msg.type == "error" else None)
                page.on("pageerror", lambda exc: page_errors.append(str(exc)[:400]))
                page.on("requestfailed", lambda req: failed_requests.append(
                    "%s %s" % (req.url[:250], req.failure)))
                page.goto(self.base + "/", wait_until="domcontentloaded", timeout=12000)
                page.wait_for_timeout(700)
                self.assertEqual(page.title(), "JARVIS — Agente")
                self.assertTrue(page.locator("#in").is_visible())
                self.assertTrue(page.locator("#nt").is_visible())
                self.assertIn("JARVIS", page.locator("body").inner_text())

                for key in ("pa", "pb", "pc", "pd"):
                    tab = page.locator('.tab[data-p="%s"]' % key)
                    self.assertTrue(tab.is_visible(), "tab " + key)
                    tab.click()
                    self.assertTrue(page.locator("#" + key).evaluate(
                        "(el) => el.classList.contains('on')"), "panel " + key)

                desktop_widths = page.evaluate(
                    "() => ({viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth})")
                self.assertLessEqual(desktop_widths["document"], desktop_widths["viewport"] + 1,
                                     str(desktop_widths))
                self.assertLessEqual(desktop_widths["body"], desktop_widths["viewport"] + 1,
                                     str(desktop_widths))

                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(350)
                mobile_widths = page.evaluate(
                    r"""() => {
                        const viewport = innerWidth;
                        const offenders = [...document.querySelectorAll('body *')]
                          .map(el => {
                            const r = el.getBoundingClientRect();
                            const chain = [];
                            let p = el;
                            for (let n = 0; p && n < 5; n++, p = p.parentElement) {
                              chain.push(p.tagName.toLowerCase() + (p.id ? '#' + p.id : '') +
                                (typeof p.className === 'string' && p.className ? '.' + p.className.toString().replace(/\s+/g,'.').slice(0,55) : ''));
                            }
                            return {tag: el.tagName.toLowerCase(), id: el.id,
                              cls: typeof el.className === 'string' ? el.className.slice(0,80) : '',
                              left: Math.round(r.left), right: Math.round(r.right),
                              width: Math.round(r.width), display: getComputedStyle(el).display,
                              position: getComputedStyle(el).position, chain};
                          })
                          .filter(x => x.display !== 'none' && x.width > 0 &&
                            (x.right > viewport + 2 || x.left < -viewport - 2))
                          .sort((a,b) => b.right-a.right).slice(0,16);
                        return {viewport, document: document.documentElement.scrollWidth,
                          body: document.body.scrollWidth, offenders};
                    }""")
                self.assertLessEqual(mobile_widths["document"], mobile_widths["viewport"] + 1,
                                     str(mobile_widths))
                self.assertLessEqual(mobile_widths["body"], mobile_widths["viewport"] + 1,
                                     str(mobile_widths))

                # On small screens the sidebar is a drawer, not a fixed 240px column.
                page.locator("#tsb").click()
                page.wait_for_timeout(250)
                drawer = page.locator(".sb").bounding_box()
                self.assertIsNotNone(drawer)
                self.assertGreater(drawer["x"] + drawer["width"], 0)
                self.assertLessEqual(drawer["x"], 1)
                page.locator("#tsb").click()
                page.wait_for_timeout(250)
                closed = page.locator(".sb").bounding_box()
                self.assertIsNotNone(closed)
                self.assertLessEqual(closed["x"] + closed["width"], 1)

                page.keyboard.press("Control+k")
                self.assertTrue(page.locator("#mod.o").count() == 1)
                page.keyboard.press("Escape")
                self.assertEqual(page.locator("#mod.o").count(), 0)
                page.screenshot(path=str(Path(self.temp.name) / "agent-mobile.png"),
                                full_page=True, animations="disabled")
            finally:
                browser.close()
        self.assertEqual(page_errors, [], "uncaught browser exceptions: %r" % page_errors)
        self.assertEqual(console_errors, [], "browser console errors: %r" % console_errors)
        self.assertEqual(failed_requests, [], "failed browser requests: %r" % failed_requests)


if __name__ == "__main__":
    unittest.main()
