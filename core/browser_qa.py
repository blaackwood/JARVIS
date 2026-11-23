"""Isolated Playwright smoke, responsive and visual QA for local web projects.

Only binds test servers to 127.0.0.1. It never uses the user's browser profile,
cookies, extensions or saved credentials. Development servers are started only
when their package script begins with a recognized framework command.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_SERVER_WAIT_SECONDS = 40
_PAGE_TIMEOUT_MS = 15_000
_VIEWPORTS = {"desktop": {"width": 1440, "height": 960},
              "mobile": {"width": 390, "height": 844}}
_SCRIPT_PREFIX = re.compile(
    r"^(?:cross-env\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*", re.I)
_FRAMEWORKS = (
    ("vite", re.compile(r"^vite(?:\s|$)", re.I),
     lambda p: ["--host", "127.0.0.1", "--port", str(p), "--strictPort"]),
    ("next", re.compile(r"^next\s+dev(?:\s|$)", re.I),
     lambda p: ["--hostname", "127.0.0.1", "--port", str(p)]),
    ("astro", re.compile(r"^astro\s+dev(?:\s|$)", re.I),
     lambda p: ["--host", "127.0.0.1", "--port", str(p)]),
    ("nuxt", re.compile(r"^nuxt\s+dev(?:\s|$)", re.I),
     lambda p: ["--host", "127.0.0.1", "--port", str(p)]),
    ("react-scripts", re.compile(r"^react-scripts\s+start(?:\s|$)", re.I), lambda p: []),
    ("vue-cli", re.compile(r"^vue-cli-service\s+serve(?:\s|$)", re.I),
     lambda p: ["--host", "127.0.0.1", "--port", str(p)]),
    ("angular", re.compile(r"^ng\s+serve(?:\s|$)", re.I),
     lambda p: ["--host", "127.0.0.1", "--port", str(p)]),
    ("webpack", re.compile(r"^webpack\s+serve(?:\s|$)", re.I),
     lambda p: ["--host", "127.0.0.1", "--port", str(p)]),
)


def _evidence_root(folder: Path) -> Path:
    digest = hashlib.sha256(str(folder.resolve()).lower().encode("utf-8")).hexdigest()[:16]
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        base = base / "JARVIS" / "BrowserQA"
    else:
        base = Path.home() / ".local" / "share" / "JARVIS" / "BrowserQA"
    out = base / digest / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _server_spec(folder: Path) -> dict[str, Any] | None:
    """Return only a static server or a narrowly allow-listed npm dev server."""
    package = folder / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        scripts = data.get("scripts") if isinstance(data, dict) else {}
        if isinstance(scripts, dict):
            has_server_script = any(isinstance(scripts.get(n), str) and scripts[n].strip()
                                    for n in ("dev", "start"))
            for script_name in ("dev", "start"):
                raw = scripts.get(script_name)
                if not isinstance(raw, str) or not raw.strip():
                    continue
                normalized = _SCRIPT_PREFIX.sub("", raw.strip(), count=1).strip()
                for framework, pattern, args in _FRAMEWORKS:
                    if pattern.match(normalized):
                        # A recognized script without its dependencies is not
                        # a runnable app; never serve the source HTML as a fake pass.
                        if not (folder / "node_modules").is_dir():
                            return None
                        return {"kind": "npm", "script": script_name,
                                "framework": framework, "args": args}
            # Do not bypass an unknown app server by serving its HTML source
            # directly; that would test a different application than users run.
            if has_server_script:
                return None
    # A root Python entry point may provide the actual API/server. Serving only
    # index.html would produce a misleading green test for a broken backend.
    if ((folder / "index.html").is_file()
            and not any((folder / n).is_file() for n in ("main.py", "app.py", "server.py", "manage.py"))):
        return {"kind": "static", "framework": "static"}
    return None


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


def _wait_ready(url: str, process: subprocess.Popen | None, timeout: float,
                log_path: Path | None) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last_error = "server did not respond"
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            detail = ""
            if log_path and log_path.is_file():
                try:
                    detail = log_path.read_text(encoding="utf-8", errors="replace")[-2500:]
                except OSError:
                    pass
            return False, f"Development server exited with code {process.returncode}. {detail}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Playwright-QA/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as response:
                if 200 <= response.status < 500:
                    return True, ""
                last_error = f"server returned HTTP {response.status}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
        time.sleep(0.35)
    detail = ""
    if log_path and log_path.is_file():
        try:
            detail = log_path.read_text(encoding="utf-8", errors="replace")[-1800:]
        except OSError:
            pass
    return False, f"Server did not become ready in {timeout:.0f}s: {last_error}. {detail}"


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        # npm can leave its child dev server alive after the launcher exits.
        # Terminate the complete process tree, not only npm itself.
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           shell=False, capture_output=True, timeout=5)
        except Exception:
            pass
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=4)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception:
                pass


def _audit_page(page) -> dict:
    return page.evaluate("""() => {
      const visible = el => {
        const s=getComputedStyle(el), r=el.getBoundingClientRect();
        return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
      };
      const named = el => Boolean((el.getAttribute('aria-label')||'').trim() ||
        (el.getAttribute('aria-labelledby')||'').trim() || (el.getAttribute('title')||'').trim() ||
        (el.innerText||el.value||'').trim());
      const controls=[...document.querySelectorAll('input,select,textarea')]
        .filter(el=>visible(el) && el.type!=='hidden');
      const bodyText=(document.body?.innerText||'').trim();
      const ids=[...document.querySelectorAll('[id]')].map(el=>el.id);
      return {
        title:document.title||'',
        headings:[...document.querySelectorAll('h1,h2')].filter(visible)
          .slice(0,12).map(el=>(el.innerText||'').trim()).filter(Boolean),
        textPreview:bodyText.slice(0,1200),
        meaningful:bodyText.length>0 || document.querySelectorAll(
          'canvas,svg,video,img,button,input,[role="application"]').length>0,
        visibleButtons:[...document.querySelectorAll('button,[role="button"]')]
          .filter(visible).map(el=>(el.getAttribute('aria-label')||el.innerText||'').trim()).slice(0,30),
        unnamedButtons:[...document.querySelectorAll('button,[role="button"]')]
          .filter(visible).filter(el=>!named(el)).length,
        unnamedControls:controls.filter(el=>!(el.labels&&el.labels.length) &&
          !el.getAttribute('aria-label')&&!el.getAttribute('aria-labelledby')).length,
        unnamedImages:[...document.images].filter(el=>visible(el)&&!el.hasAttribute('alt')).length,
        brokenImages:[...document.images].filter(el=>visible(el)&&el.complete&&el.naturalWidth===0)
          .map(el=>el.currentSrc||el.src).slice(0,10),
        emptyLinks:[...document.querySelectorAll('a')].filter(visible)
          .filter(el=>!el.getAttribute('href')).length,
        duplicateIds:[...new Set(ids.filter((id,i)=>ids.indexOf(id)!==i))],
        layout:{viewport:document.documentElement.clientWidth,
          document:document.documentElement.scrollWidth,
          body:document.body?.scrollWidth||0,height:document.documentElement.scrollHeight}
      };
    }""")


def _add_check(checks: list[dict], name: str, passed: bool, detail: Any = "",
               severity: str = "error") -> None:
    checks.append({"name": name, "passed": bool(passed),
                   "detail": str(detail)[:1200], "severity": severity})


def _visual_review(screenshots: list[Path], provider: str = "") -> dict:
    """Ask the configured coding-model ladder to identify only visible defects."""
    if not screenshots:
        return {"available": False, "issues": [], "note": "No screenshots were captured."}
    try:
        from google.genai import types as gtypes
        from core import gemini
        parts: list[Any] = [
            "You are the visual QA reviewer for a web application. Inspect the attached "
            "desktop and mobile screenshots as evidence, not as an invitation to redesign. "
            "Report only concrete, clearly visible defects that harm function or usability: "
            "overlap, clipped/off-screen content, unreadable contrast or text, broken images, "
            "missing critical content, severe spacing/layout failures, or mobile breakage. "
            "Do not invent invisible behavior or turn subjective style preferences into bugs. "
            "Return ONLY JSON: {\"issues\":[{\"severity\":\"blocker|major|minor\","
            "\"screen\":\"desktop|mobile\",\"issue\":\"specific visible evidence\","
            "\"suggested_fix\":\"smallest reasonable fix\"}]}. Return {\"issues\":[]} if sound."
        ]
        for path in screenshots[:2]:
            parts.append(gtypes.Part.from_bytes(data=path.read_bytes(), mime_type="image/png"))
        response = gemini.call(parts, tier=gemini.SMART, timeout_ms=90_000, provider=provider)
        raw = (getattr(response, "text", "") or "").strip() if response else ""
        if not raw:
            return {"available": False, "issues": [], "note": "Visual model unavailable."}
        match = re.search(r"\{.*\}", raw, re.S)
        parsed = json.loads(match.group(0)) if match else {}
        issues = parsed.get("issues") if isinstance(parsed, dict) else []
        clean = []
        for issue in (issues if isinstance(issues, list) else [])[:12]:
            if not isinstance(issue, dict) or not issue.get("issue"):
                continue
            severity = str(issue.get("severity", "minor")).lower()
            if severity not in ("blocker", "major", "minor"):
                severity = "minor"
            clean.append({"severity": severity,
                          "screen": str(issue.get("screen", "unknown"))[:20],
                          "issue": str(issue["issue"])[:500],
                          "suggested_fix": str(issue.get("suggested_fix", ""))[:400]})
        return {"available": True, "issues": clean}
    except Exception as exc:
        return {"available": False, "issues": [],
                "note": f"Visual review unavailable ({type(exc).__name__})."}


def audit_web_project(folder: Path | str, *, visual_review: bool = True,
                      server_timeout: int = _SERVER_WAIT_SECONDS) -> dict:
    """Run desktop/mobile Playwright QA for a static or allow-listed web project.

    supported=False means no safe browser entry point was detected. A supported
    app that cannot be served or tested returns ok=False, never a false pass.
    """
    folder = Path(folder).resolve()
    spec = _server_spec(folder)
    if spec is None:
        return {"supported": False, "ok": True, "reason": "No supported web entry point."}

    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    local_request_failures: list[str] = []
    external_request_failures: list[str] = []
    external_requests_attempted: list[str] = []
    local_http_errors: list[str] = []
    screenshots: list[Path] = []
    evidence = _evidence_root(folder)
    port = _port()
    url = f"http://127.0.0.1:{port}/"
    process = None
    log_handle = None
    static_server = None
    startup_error = ""
    visual = {"available": False, "issues": [], "note": "Not run."}
    page_summary: dict[str, Any] = {}

    try:
        if spec["kind"] == "static":
            handler = functools.partial(_QuietHandler, directory=str(folder))
            static_server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            static_server.daemon_threads = True
            threading.Thread(target=static_server.serve_forever, daemon=True,
                             name="jarvis-static-qa").start()
        else:
            npm = shutil.which("npm")
            if not npm:
                startup_error = "npm is not installed; the recognized development server cannot start."
            else:
                from core.code_checks import resolve_project_command
                command = resolve_project_command([npm, "run", spec["script"], "--",
                                                    *spec["args"](port)])
                if command is None:
                    startup_error = "Could not safely resolve npm to its Node CLI; no shell was used."
                else:
                    log_path = evidence / "dev-server.log"
                    log_handle = log_path.open("w", encoding="utf-8")
                    env = dict(os.environ)
                    env.update({"HOST": "127.0.0.1", "PORT": str(port),
                                "BROWSER": "none", "CI": "1", "NO_UPDATE_NOTIFIER": "1"})
                    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
                    process = subprocess.Popen(command, cwd=str(folder), env=env, shell=False,
                                               stdin=subprocess.DEVNULL, stdout=log_handle,
                                               stderr=subprocess.STDOUT, creationflags=flags)

        if startup_error:
            _add_check(checks, "Development server starts safely", False, startup_error)
        else:
            ready, why = _wait_ready(url, process, float(server_timeout),
                                     evidence / "dev-server.log" if spec["kind"] == "npm" else None)
            _add_check(checks, "Local web server becomes ready", ready, why or url)
            if ready:
                try:
                    from playwright.sync_api import sync_playwright
                except Exception as exc:
                    _add_check(checks, "Playwright browser runtime available", False,
                               f"{type(exc).__name__}: {exc}")
                else:
                    try:
                        with sync_playwright() as playwright:
                            browser = playwright.chromium.launch(headless=True)
                            try:
                                context = browser.new_context(viewport=_VIEWPORTS["desktop"],
                                                              device_scale_factor=1,
                                                              ignore_https_errors=False,
                                                              accept_downloads=False)
                                page = context.new_page()
                                page.set_default_timeout(_PAGE_TIMEOUT_MS)
                                local_origin = f"http://127.0.0.1:{port}"
                                def isolate_network(route):
                                    request_url = route.request.url
                                    if (request_url.startswith(local_origin + "/")
                                            or request_url in (local_origin, local_origin + "/")
                                            or request_url.startswith(("data:", "blob:", "about:"))):
                                        route.continue_()
                                    else:
                                        external_requests_attempted.append({
                                            "url": request_url[:350],
                                            "resource_type": route.request.resource_type})
                                        route.abort()
                                # Project code cannot call the Internet, cloud APIs, LAN or
                                # unrelated localhost services during an automatic audit.
                                page.route("**/*", isolate_network)
                                if hasattr(page, "route_web_socket"):
                                    def isolate_websocket(websocket_route):
                                        external_requests_attempted.append({
                                            "url": websocket_route.url[:350],
                                            "resource_type": "websocket"})
                                        websocket_route.close(code=1008, reason="Blocked by JARVIS QA isolation")
                                    page.route_web_socket("**/*", isolate_websocket)
                                def on_console(msg):
                                    if msg.type != "error":
                                        return
                                    if any(item["url"] in msg.text for item in external_requests_attempted):
                                        return  # explained by the deliberate network block
                                    if "ERR_BLOCKED_BY_CLIENT" in msg.text and external_requests_attempted:
                                        return
                                    console_errors.append(msg.text[:500])
                                page.on("console", on_console)
                                page.on("pageerror", lambda exc: page_errors.append(str(exc)[:700]))
                                def on_failed(req):
                                    item = f"{req.method} {req.url[:350]} — {req.failure}"
                                    (local_request_failures if req.url.startswith(local_origin)
                                     else external_request_failures).append(item)
                                page.on("requestfailed", on_failed)
                                page.on("response", lambda res: local_http_errors.append(
                                    f"HTTP {res.status} {res.url[:350]}")
                                    if res.status >= 400 and res.url.startswith(local_origin) else None)

                                response = None
                                navigation_error = ""
                                try:
                                    response = page.goto(url, wait_until="domcontentloaded",
                                                         timeout=_PAGE_TIMEOUT_MS)
                                    try:
                                        page.wait_for_load_state("networkidle", timeout=3500)
                                    except Exception:
                                        pass
                                    page.wait_for_timeout(350)
                                except Exception as exc:
                                    navigation_error = f"{type(exc).__name__}: {str(exc)[:350]}"

                                _add_check(checks, "Application route responds successfully",
                                           response is not None and 200 <= response.status < 400,
                                           f"HTTP {response.status}" if response else navigation_error)
                                if response is not None and response.status >= 400:
                                    local_http_errors.append(f"HTTP {response.status} {url}")

                                desktop = _audit_page(page) if response else {}
                                if desktop:
                                    page_summary["desktop"] = desktop
                                    _add_check(checks, "Desktop page renders meaningful content",
                                               desktop.get("meaningful", False),
                                               f"title={desktop.get('title')!r}; headings={desktop.get('headings')}")
                                    _add_check(checks, "Desktop document has a title",
                                               bool(desktop.get("title")), desktop.get("title"),
                                               severity="warning")
                                    _add_check(checks, "Visible buttons have accessible names",
                                               desktop.get("unnamedButtons", 0) == 0,
                                               desktop.get("unnamedButtons", 0))
                                    _add_check(checks, "Visible form controls have labels",
                                               desktop.get("unnamedControls", 0) == 0,
                                               desktop.get("unnamedControls", 0))
                                    _add_check(checks, "Images have alternative text",
                                               desktop.get("unnamedImages", 0) == 0,
                                               desktop.get("unnamedImages", 0), severity="warning")
                                    _add_check(checks, "Images load successfully",
                                               desktop.get("brokenImages", []) == [],
                                               desktop.get("brokenImages", []))
                                    _add_check(checks, "Visible links have destinations",
                                               desktop.get("emptyLinks", 0) == 0,
                                               desktop.get("emptyLinks", 0))
                                    _add_check(checks, "Element IDs are unique",
                                               desktop.get("duplicateIds", []) == [],
                                               desktop.get("duplicateIds", []))
                                    shot = evidence / "desktop.png"
                                    page.screenshot(path=str(shot), full_page=True,
                                                    animations="disabled", timeout=15_000)
                                    screenshots.append(shot)

                                page.set_viewport_size(_VIEWPORTS["mobile"])
                                page.wait_for_timeout(250)
                                mobile = _audit_page(page) if response else {}
                                if mobile:
                                    page_summary["mobile"] = mobile
                                    layout = mobile.get("layout") or {}
                                    no_overflow = (layout.get("document", 10**9) <= layout.get("viewport", 0)
                                                   and layout.get("body", 10**9) <= layout.get("viewport", 0))
                                    _add_check(checks, "Mobile layout has no horizontal overflow",
                                               no_overflow, layout)
                                    shot = evidence / "mobile.png"
                                    page.screenshot(path=str(shot), full_page=True,
                                                    animations="disabled", timeout=15_000)
                                    screenshots.append(shot)
                                context.close()
                            finally:
                                browser.close()
                    except Exception as exc:
                        _add_check(checks, "Playwright browser session completes", False,
                                   f"{type(exc).__name__}: {str(exc)[:500]}")

        _add_check(checks, "No uncaught JavaScript exceptions", not page_errors, page_errors)
        _add_check(checks, "No JavaScript console errors", not console_errors, console_errors)
        _add_check(checks, "No failed local network requests",
                   not local_request_failures, local_request_failures)
        _add_check(checks, "No local HTTP 4xx/5xx responses",
                   not local_http_errors, local_http_errors)
        critical_external = [item for item in external_requests_attempted
                             if item.get("resource_type") in
                             ("document", "script", "stylesheet", "xhr", "fetch", "websocket")]
        optional_external = [item for item in external_requests_attempted
                             if item not in critical_external]
        _add_check(checks, "No required external network dependency",
                   not critical_external, critical_external)
        if optional_external or external_request_failures:
            _add_check(checks, "Optional external requests were blocked", True,
                       {"attempted": optional_external, "failed": external_request_failures},
                       severity="warning")

        if visual_review and screenshots:
            try:
                from memory.config_manager import get_coding_provider
                provider = get_coding_provider() or ""
            except Exception:
                provider = ""
            visual = _visual_review(screenshots, provider=provider)

    except Exception as exc:
        _add_check(checks, "Browser QA infrastructure completes", False,
                   f"{type(exc).__name__}: {str(exc)[:700]}")
    finally:
        if static_server is not None:
            try:
                static_server.shutdown()
                static_server.server_close()
            except Exception:
                pass
        _stop_process(process)
        if log_handle is not None:
            try:
                log_handle.close()
            except Exception:
                pass

    major_visual = [i for i in visual.get("issues", [])
                    if i.get("severity") in ("blocker", "major")]
    for index, issue in enumerate(major_visual, 1):
        _add_check(checks, f"Visual review: {issue.get('screen', 'page')} defect {index}",
                   False, f"{issue.get('issue')} Suggested fix: {issue.get('suggested_fix', '')}")

    failed = [c for c in checks if not c["passed"] and c.get("severity") != "warning"]
    warnings = [c for c in checks if not c["passed"] and c.get("severity") == "warning"]
    report = {
        "supported": True, "ok": not failed,
        "framework": spec.get("framework"), "mode": spec.get("kind"), "url": url,
        "evidence_dir": str(evidence), "screenshots": [str(p) for p in screenshots],
        "summary": {"passed": sum(1 for c in checks if c["passed"]),
                    "failed": len(failed), "warnings": len(warnings), "total": len(checks)},
        "checks": checks, "diagnostics": [f"{c['name']}: {c['detail']}" for c in failed],
        "warnings": [f"{c['name']}: {c['detail']}" for c in warnings],
        "console_errors": console_errors, "page_errors": page_errors,
        "local_request_failures": local_request_failures,
        "local_http_errors": local_http_errors,
        "external_request_failures": external_request_failures,
        "external_requests_attempted": external_requests_attempted,
        "page_summary": page_summary, "visual_review": visual,
    }
    try:
        (evidence / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return report


def format_diagnostics(report: dict) -> str:
    """Concise, actionable evidence to give the coding model."""
    if not report.get("supported"):
        return report.get("reason", "No browser QA is available.")
    summary = report.get("summary") or {}
    lines = [f"Playwright browser QA failed for {report.get('framework')} "
             f"({summary.get('failed', 0)} blocking checks).",
             "Fix only defects supported by this evidence; preserve unrelated working behavior."]
    lines.extend("- " + item for item in report.get("diagnostics", [])[:18])
    for issue in (report.get("visual_review") or {}).get("issues", [])[:8]:
        if issue.get("severity") in ("blocker", "major"):
            lines.append(f"- Visual {issue.get('severity')} on {issue.get('screen')}: "
                         f"{issue.get('issue')} Suggested: {issue.get('suggested_fix')}")
    for screen, item in (report.get("page_summary") or {}).items():
        lines.append(f"- {screen}: title={item.get('title')!r}; headings={item.get('headings')}; "
                     f"buttons={item.get('visibleButtons')}")
    lines.append(f"Evidence screenshots and report: {report.get('evidence_dir')}")
    return "\n".join(lines)
