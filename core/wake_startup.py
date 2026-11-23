"""Small startup helpers for the Windows wake-word daemon."""
from __future__ import annotations

from pathlib import Path


def clear_stale_stop_marker(path: str | Path) -> bool:
    """Clear a stop marker left by a previous Windows login/session.

    The daemon is started at user logon with no parent PID. A marker from a
    previous "exit completely" must not disable auto-start on the next login.
    Hibernation launches pass a parent PID and do not call this helper.
    """
    try:
        Path(path).unlink(missing_ok=True)
        return True
    except OSError:
        return False
def sleep_on_command(
    wake_enabled,
    ensure_detector,
    sleep_callback,
) -> tuple[bool, str]:
    """Return JARVIS to wake-word standby without shutting down the app."""
    if not wake_enabled:
        return False, "Wake-word mode is disabled; enable Hey Jarvis before using sleep mode."
    if not ensure_detector():
        return False, "The Hey Jarvis detector could not be started; staying awake."
    sleep_callback(reason="user asked me to rest")
    return True, "JARVIS is asleep; the Hey Jarvis detector remains active."


