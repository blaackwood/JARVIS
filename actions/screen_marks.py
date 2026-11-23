"""Temporary screen marks positioned on the primary display."""
from __future__ import annotations

from gui.screen_marks import normalize_screen_marks


def show_screen_marks(parameters: dict, player=None, speak=None) -> str:
    if player is None or not callable(getattr(player, "show_screen_marks", None)):
        return "SCREEN_MARKS_UNAVAILABLE: desktop UI is not connected."
    try:
        payload = normalize_screen_marks(parameters or {})
        operation = str((parameters or {}).get("operation") or "append").lower()
        if operation not in {"append", "replace"}:
            operation = "append"
        player.show_screen_marks(payload, operation=operation)
        verb = "appended" if operation == "append" else "replaced"
        return f"SCREEN_MARKS_SHOWN: {len(payload['marks'])} mark(s) {verb} on the primary monitor for {payload['duration']} seconds."
    except (TypeError, ValueError) as exc:
        return f"SCREEN_MARKS_INVALID: {exc}"
    except Exception as exc:
        return f"SCREEN_MARKS_FAILED: {type(exc).__name__}: {str(exc)[:160]}"


def clear_screen_marks(parameters: dict | None = None, player=None, speak=None) -> str:
    if player is None or not callable(getattr(player, "clear_screen_marks", None)):
        return "SCREEN_MARKS_UNAVAILABLE: desktop UI is not connected."
    try:
        player.clear_screen_marks()
        return "SCREEN_MARKS_CLEARED: temporary marks removed."
    except Exception as exc:
        return f"SCREEN_MARKS_FAILED: {type(exc).__name__}: {str(exc)[:160]}"


TOOL = {
    "name": "show_screen_marks",
    "description": (
        "Draw temporary visual pointers, circles, frames, arrows, checks, cross marks, "
        "underlines, highlights, labels or a spotlight over the REAL desktop on the PRIMARY "
        "monitor. Use this after screen_process has provided a fresh screenshot or the user "
        "selected a screen area. Coordinates x,y,w,h and path points use a 0–1000 grid over "
        "the captured primary-screen image (0,0 top-left; 1000,1000 bottom-right). For a box, "
        "x,y are its centre. For line/curve/trace/arrow/connect provide points [[x,y],...]. "
        "Use target/ring/frame/highlight to indicate a control or region; use label/write to "
        "write beside it. These marks are temporary and disappear after duration seconds. "
        "This does not click or alter the target application; it only draws annotations."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "duration": {"type": "INTEGER", "description": "How long marks remain, 2 to 45 seconds; default 12."},
        "operation": {"type": "STRING", "enum": ["append", "replace"], "description": "Append by default; replace only when explicitly clearing and drawing a new mark set."},
            "viewport": {"type": "OBJECT", "description": "Optional crop-to-screen mapping returned by screen_process angle=area: x,y,w,h on the full primary-screen 0-1000 grid.", "properties": {
                "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"},
                "w": {"type": "NUMBER"}, "h": {"type": "NUMBER"}
            }},
            "marks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "kind": {"type": "STRING", "enum": [
                    "point","target","ring","frame","underline","strike","check","cross",
                    "connect","trace","line","curve","arrow","circle","rect","label",
                    "write","highlight","spotlight","num"
                ]},
                "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"},
                "w": {"type": "NUMBER"}, "h": {"type": "NUMBER"}, "r": {"type": "NUMBER"},
                "text": {"type": "STRING"}, "label": {"type": "STRING"},
                "n": {"type": "INTEGER"},
                "tone": {"type": "STRING", "enum": ["cyan","teal","amber","coral","lilac","sky","lime","red","white"]},
                "points": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "NUMBER"}}}
            }}}
        },
        "required": ["marks"]
    },
    "handler": show_screen_marks,
    "tier": "core",
    "brief": "Draw temporary markers and annotations over the real desktop.",
}
