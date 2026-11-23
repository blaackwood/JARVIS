"""Clear temporary desktop annotations."""
def clear_screen_marks(parameters: dict | None = None, player=None, speak=None) -> str:
    if player is None or not callable(getattr(player, "clear_screen_marks", None)):
        return "SCREEN_MARKS_UNAVAILABLE: desktop UI is not connected."
    try:
        player.clear_screen_marks()
        return "SCREEN_MARKS_CLEARED: temporary marks removed."
    except Exception as exc:
        return f"SCREEN_MARKS_FAILED: {type(exc).__name__}: {str(exc)[:160]}"

TOOL = {
    "name": "clear_screen_marks",
    "description": (
        "Remove temporary arrows, rings, frames, labels, highlights and spotlight "
        "annotations from the desktop without closing the teaching board or JARVIS."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": clear_screen_marks,
    "tier": "core",
    "brief": "Clear temporary visual marks from the desktop.",
}
