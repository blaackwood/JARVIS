"""Edit one existing JARVIS visual-board element without rebuilding the scene."""
from __future__ import annotations

from core.visual_board import normalize_visual_payload
from actions.visual_board import _ELEMENT_SCHEMA


def edit_visual(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    if player is None or not callable(getattr(player, "edit_visual_board", None)):
        return "VISUAL_UNAVAILABLE: the editable visual board is not connected."
    operation = str(params.get("operation") or "").strip().lower()
    if operation not in {"add", "update", "delete", "move"}:
        return "INVALID_OPERATION: use add, update, delete or move."
    element_id = str(params.get("element_id") or "").strip()
    patch = {}
    if operation in {"add", "update"}:
        raw = params.get("element") or {}
        if not isinstance(raw, dict):
            return "INVALID_ELEMENT: element must be an object."
        try:
            normalized = normalize_visual_payload({
                "title": "Element edit", "elements": [raw]
            })
            patch = normalized["elements"][0]
            from core.visual_board import enforce_3d
            enforce_3d([patch], require_model=False)
            if patch.get("type") == "photo":
                from core.visual_assets import enrich_photo_item
                enrich_photo_item(patch)
        except (TypeError, ValueError) as exc:
            return f"INVALID_ELEMENT: {exc}"
    if operation in {"update", "delete", "move"} and not element_id:
        return "ELEMENT_ID_REQUIRED: inspect the current board and specify its element_id."
    try:
        result = player.edit_visual_board(
            operation, element_id, patch,
            float(params.get("dx", 0) or 0), float(params.get("dy", 0) or 0)
        )
    except Exception as exc:
        return f"VISUAL_EDIT_FAILED: {type(exc).__name__}: {str(exc)[:160]}"
    return f"VISUAL_EDITED: {result}. Unrelated drawing elements were preserved."


TOOL = {
    "name": "edit_visual",
    "description": (
        "Edit the existing on-screen teaching board at element level. Use add to insert "
        "one element, update to change one element's properties, delete to remove only "
        "one element, and move to translate one element by dx/dy percentages. Every "
        "element has a stable element_id; use IDs from the current scene, never guess. "
        "Do not call show_visual with replace for a local edit. For a complete new scene, "
        "use show_visual operation=replace. The board remains on the primary monitor."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "enum": ["add", "update", "delete", "move"]},
            "element_id": {"type": "STRING", "description": "Stable ID of the element to update, move or delete."},
            "element": _ELEMENT_SCHEMA,
            "dx": {"type": "NUMBER", "description": "Horizontal translation in percentage points for move."},
            "dy": {"type": "NUMBER", "description": "Vertical translation in percentage points for move."},
        },
        "required": ["operation"],
    },
    "handler": edit_visual,
    "tier": "core",
    "brief": "Add, update, move or delete one element on the current visual board.",
}
