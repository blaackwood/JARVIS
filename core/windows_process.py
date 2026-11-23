"""Windows process-launch policy for JARVIS GUI and background workers.

Console applications launched by JARVIS must never flash or leave a terminal
window. GUI applications still open normally; CREATE_NO_WINDOW only suppresses
console windows.
"""
from __future__ import annotations

import os
import subprocess


_CREATE_NEW_CONSOLE = 0x00000010
_CREATE_NO_WINDOW = 0x08000000


def hidden_creationflags(existing_flags: int = 0) -> int:
    """Merge Windows creation flags while forbidding a newly-created console."""
    flags = int(existing_flags or 0)
    flags &= ~_CREATE_NEW_CONSOLE
    return flags | _CREATE_NO_WINDOW


def install_no_console_policy() -> bool:
    """Ensure every subsequent subprocess.Popen call from this process is hidden."""
    if os.name != "nt":
        return False

    current = subprocess.Popen
    if getattr(current, "_jarvis_no_console_policy", False):
        return True

    class _JarvisNoConsolePopen(current):
        _jarvis_no_console_policy = True

        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = hidden_creationflags(
                kwargs.get("creationflags", 0)
            )
            super().__init__(*args, **kwargs)

    _JarvisNoConsolePopen.__name__ = "JarvisNoConsolePopen"
    _JarvisNoConsolePopen.__qualname__ = "JarvisNoConsolePopen"
    subprocess.Popen = _JarvisNoConsolePopen
    return True
