"""Return stable IDs and geometry for the current visual scene."""
def inspect_visual(parameters: dict, player=None, speak=None) -> str:
    if player is None or not callable(getattr(player, "inspect_visual_board", None)):
        return "VISUAL_UNAVAILABLE: the visual board is not connected."
    try:
        scene = player.inspect_visual_board()
        import json
        return "VISUAL_SCENE: " + json.dumps(scene, ensure_ascii=False)
    except Exception as exc:
        return f"VISUAL_INSPECT_FAILED: {type(exc).__name__}: {str(exc)[:160]}"

TOOL = {
    "name": "inspect_visual",
    "description": (
        "Inspect the currently open teaching board and return every element's stable "
        "element_id, type, text and coordinates. ALWAYS call this before edit_visual "
        "when you do not already know the exact ID. This reads the board without changing it."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": inspect_visual,
    "tier": "core",
    "brief": "Inspect current visual-board elements and their IDs.",
}
