"""Launch the full JARVIS app from the base Python runtime with project dependencies.

The native wake daemon starts pythonw.exe, so stdout/stderr would otherwise be
lost. Keep a quiet, file-backed startup trace to make silent startup failures
diagnosable without ever opening a console window.
"""
from __future__ import annotations

import datetime
import os
import runpy
import site
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
MEMORY = BASE / "memory"
MEMORY.mkdir(parents=True, exist_ok=True)
LOG_PATH = MEMORY / "wake_main_bootstrap.log"
_LOG = LOG_PATH.open("a", encoding="utf-8", buffering=1)


def _log(message: str) -> None:
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    _LOG.write(f"[{stamp}] {message}\n")
    _LOG.flush()


def _exception_hook(exc_type, exc_value, exc_tb) -> None:
    _log("UNCAUGHT PYTHON EXCEPTION")
    traceback.print_exception(exc_type, exc_value, exc_tb, file=_LOG)
    _LOG.flush()


sys.stdout = _LOG
sys.stderr = _LOG
sys.excepthook = _exception_hook

_log(f"bootstrap started pid={os.getpid()} argv={sys.argv!r} cwd={os.getcwd()!r}")
try:
    SITE_PACKAGES = BASE / ".venv" / "Lib" / "site-packages"
    if not SITE_PACKAGES.is_dir():
        raise RuntimeError(f"JARVIS virtual environment not found: {SITE_PACKAGES}")

    site.addsitedir(str(SITE_PACKAGES))
    sys.argv = [str(BASE / "main.py"), *sys.argv[1:]]
    _log(f"launching main.py argv={sys.argv!r}")
    runpy.run_path(str(BASE / "main.py"), run_name="__main__")
    _log("main.py returned normally")
except BaseException:
    _log("BOOTSTRAP FAILED")
    traceback.print_exc(file=_LOG)
    _LOG.flush()
    raise
finally:
    _log("bootstrap exiting")
    _LOG.flush()
