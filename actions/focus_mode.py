"""Opt-in focus sessions; only the foreground app/window title is inspected locally."""
from __future__ import annotations

import atexit
import threading

_manager = None
_manager_lock = threading.RLock()


def _front_window() -> dict | None:
    from core import screenview

    view = screenview.look(budget_s=1.2, allow_ocr=False)
    if not view.app:
        return None
    url = ""
    for element in view.elements:
        label = f"{element.name} {element.role}".casefold()
        value = str(element.value or "").strip()
        if value.startswith(("https://", "http://")) and any(
            word in label for word in ("address", "url", "search", "location", "edit")
        ):
            url = value[:500]
            break
    return {"app": view.app, "title": view.title, "url": url}


def _get_manager(player=None, notify=None):
    global _manager
    with _manager_lock:
        if _manager is None:
            from core.focus import FocusManager

            def log(message):
                try:
                    if player is not None and hasattr(player, "write_log"):
                        player.write_log("SYS: " + str(message))
                except Exception:
                    pass

            def send(message):
                log(message)
                if callable(notify):
                    try:
                        notify(
                            "[FOCUS MODE EVENT]\n"
                            f"{message}\n"
                            "Give the user one brief, supportive spoken notification in Brazilian Portuguese. "
                            "Do not call tools or start a new focus session."
                        )
                    except Exception:
                        pass

            _manager = FocusManager(_front_window, send, log)
        return _manager


def focus_mode(parameters: dict, player=None, notify=None) -> str:
    action = str((parameters or {}).get("action") or "status").strip().lower()
    manager = _get_manager(player, notify)
    if action == "start":
        return manager.start((parameters or {}).get("minutes", 25),
                             (parameters or {}).get("task", ""))
    if action == "stop":
        return manager.stop()
    if action == "status":
        status = manager.status()
        if not status:
            return "No focus session is active."
        minutes = (status["remaining_seconds"] + 59) // 60
        task = f" on {status['task']}" if status["task"] else ""
        return f"Focus session active{task}: {minutes} minutes remaining; {status['drifts']} distractions detected."
    return "Unknown focus action. Use start, stop, or status."


def _shutdown():
    global _manager
    with _manager_lock:
        manager, _manager = _manager, None
    if manager is not None:
        manager.stop()


atexit.register(_shutdown)


TOOL = {
    "name": "focus_mode",
    "description": (
        "Manage an explicit focus session. action=start begins a 5–240 minute focus block "
        "(25 minutes by default), optionally with task. While active, JARVIS checks the "
        "foreground app and window title locally every 20 seconds. After two consecutive "
        "checks on a configured distraction (video/social/game apps or sites), it gives "
        "a gentle reminder, no more often than every 3 minutes. It does not capture screenshots, "
        "read page contents, record keystrokes, block apps, or send screen data to a service. "
        "Starting another block replaces the current one. action=stop ends it; action=status "
        "reports remaining time. Use only when the user explicitly asks for focus/accountability."
    ),
    "brief": "Start, stop, or check a local focus session with gentle distraction nudges.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status"]},
            "minutes": {"type": "INTEGER", "minimum": 5, "maximum": 240},
            "task": {"type": "STRING"},
        },
        "required": ["action"],
    },
    "handler": focus_mode,
}
