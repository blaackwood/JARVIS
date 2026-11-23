"""Command-line entry point for JARVIS's built-in local browser QA."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _check_environment() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "playwright": False,
            "error": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2))
        return 2
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        print(json.dumps({
            "ok": True,
            "python": sys.executable,
            "browser": "Playwright Chromium",
            "headless_launch": True,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "python": sys.executable,
            "playwright": True,
            "error": f"{type(exc).__name__}: {exc}",
            "next_step": "Install the Playwright browser from the JARVIS setup instructions; this command never downloads dependencies.",
        }, ensure_ascii=False, indent=2))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the JARVIS local Playwright browser QA workflow."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check whether Playwright and its Chromium browser can launch",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="web project folder to inspect (default: current directory)",
    )
    parser.add_argument(
        "--no-visual-review",
        action="store_true",
        help="skip optional AI visual review; keep browser and responsive checks",
    )
    args = parser.parse_args()

    if args.check:
        return _check_environment()

    project = Path(args.project_dir).expanduser().resolve()
    if not project.is_dir():
        parser.error(f"project directory does not exist: {project}")

    try:
        from core.browser_qa import audit_web_project, format_diagnostics
        report = audit_web_project(
            project,
            visual_review=not args.no_visual_review,
        )
    except Exception as exc:
        print(json.dumps({
            "supported": False,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2))
        return 2

    public_report = dict(report)
    public_report["project"] = str(project)
    print(json.dumps(public_report, ensure_ascii=False, indent=2, default=str))
    if not report.get("supported"):
        print(report.get("reason") or "JARVIS browser QA does not support this project entry point.")
        return 2
    if not report.get("ok"):
        print(format_diagnostics(report), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
