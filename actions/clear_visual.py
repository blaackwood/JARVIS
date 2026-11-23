"""Separate discoverable clear command for the JARVIS visual teaching board."""
from actions.visual_board import clear_visual

TOOL = {
    "name": "clear_visual",
    "description": (
        "Clear the current on-screen visual diagram when the user asks to erase, "
        "close, remove or start over with the drawing. Does not close JARVIS or end the conversation."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": clear_visual,
    "tier": "core",
    "brief": "Clear the on-screen visual teaching board.",
}
