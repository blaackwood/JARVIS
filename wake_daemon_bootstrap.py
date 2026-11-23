"""Launch the hibernated listener directly in the base interpreter.

The venv's Windows pythonw.exe is a redirector that creates an extra process.
This bootstrap adds the venv packages to the base interpreter and runs the
listener in that same process.
"""
from __future__ import annotations

import runpy
import site
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SITE_PACKAGES = BASE / ".venv" / "Lib" / "site-packages"
if not SITE_PACKAGES.is_dir():
    raise RuntimeError(f"JARVIS virtual environment not found: {SITE_PACKAGES}")
site.addsitedir(str(SITE_PACKAGES))
sys.argv = [str(BASE / "wake_daemon.py"), *sys.argv[1:]]
runpy.run_path(str(BASE / "wake_daemon.py"), run_name="__main__")
