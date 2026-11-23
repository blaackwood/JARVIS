"""Inspect current desktop mark IDs and normalized geometry."""
from __future__ import annotations
import json

def inspect_screen_marks(parameters: dict | None = None, player=None, speak=None) -> str:
    if player is None or not callable(getattr(player, "inspect_screen_marks", None)):
        return "SCREEN_MARKS_UNAVAILABLE: desktop UI is not connected."
    try:
        state = player.inspect_screen_marks()
        return "SCREEN_MARKS: " + json.dumps(state, ensure_ascii=False)
    except Exception as exc:
        return f"SCREEN_MARKS_INSPECT_FAILED: {type(exc).__name__}: {str(exc)[:160]}"

TOOL = {
    "name": "inspect_screen_marks",
    "description": (
        "Inspect the current temporary desktop annotations. Returns stable element_id "
        "values and each mark's kind, text, normalized position, size and tone. ALWAYS "
        "call this before editing a mark if you do not already know its exact ID. "
        "Does not change the screen."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": inspect_screen_marks,
    "tier": "core",
    "brief": "Inspect the current desktop marks and their IDs.",
}
