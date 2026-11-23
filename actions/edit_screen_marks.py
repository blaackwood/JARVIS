"""In-place edits to individual desktop screen marks."""
from __future__ import annotations

_ALLOWED = {"add", "update", "move", "recolor", "delete", "clear"}

def edit_screen_marks(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    if player is None or not callable(getattr(player, "edit_screen_marks", None)):
        return "SCREEN_MARKS_UNAVAILABLE: desktop UI is not connected."
    operation = str(params.get("operation") or "").strip().lower()
    if operation not in _ALLOWED:
        return "INVALID_OPERATION: use add, update, move, recolor, delete or clear."
    element_id = str(params.get("element_id") or "").strip()
    patch = params.get("mark") or {}
    if not isinstance(patch, dict):
        return "INVALID_MARK: mark must be an object."
    if operation in {"update", "move", "recolor", "delete"} and not element_id:
        return "ELEMENT_ID_REQUIRED: inspect_screen_marks first and use its element_id."
    if operation == "add" and not patch.get("kind"):
        return "MARK_KIND_REQUIRED: specify the kind for the new mark."
    try:
        result = player.edit_screen_marks(
            operation, element_id, patch,
            float(params.get("dx", 0) or 0), float(params.get("dy", 0) or 0)
        )
    except Exception as exc:
        return f"SCREEN_MARK_EDIT_FAILED: {type(exc).__name__}: {str(exc)[:160]}"
    return f"SCREEN_MARK_EDITED: {result}. Unrelated marks were preserved."


_MARK_PROPERTIES = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": [
            "point","target","ring","frame","underline","strike","check","cross",
            "connect","trace","line","curve","arrow","circle","rect","label",
            "write","highlight","spotlight","num"
        ]},
        "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"},
        "w": {"type": "NUMBER"}, "h": {"type": "NUMBER"},
        "r": {"type": "NUMBER"}, "text": {"type": "STRING"},
        "tone": {"type": "STRING", "enum": ["cyan","teal","amber","coral","lilac","sky","lime","red","white"]},
        "points": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "NUMBER"}}},
    },
}

TOOL = {
    "name": "edit_screen_marks",
    "description": (
        "Edit one temporary annotation on the actual desktop without rebuilding the others. "
        "Use add to create a mark, update to change its properties, move to translate by dx/dy, "
        "recolor to change tone, delete to remove only one mark, or clear to remove all marks. "
        "For update/move/recolor/delete use the exact element_id from inspect_screen_marks. "
        "dx/dy are normalized whole-primary-screen units (0–1000). The operation only changes "
        "the annotation overlay; it never clicks or edits the underlying application."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "enum": sorted(_ALLOWED)},
            "element_id": {"type": "STRING"},
            "mark": _MARK_PROPERTIES,
            "dx": {"type": "NUMBER"}, "dy": {"type": "NUMBER"},
        },
        "required": ["operation"],
    },
    "handler": edit_screen_marks,
    "tier": "core",
    "brief": "Move, recolor, update or delete one temporary desktop mark.",
}
