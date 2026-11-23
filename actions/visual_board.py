"""Gemini tools for building and clearing JARVIS's on-screen visual board."""
from __future__ import annotations

from core.visual_board import normalize_visual_payload


_ELEMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "id": {"type": "STRING", "description": "Optional stable identifier. Preserve it when editing this element later."},
        "type": {"type": "STRING", "enum": [
            "text", "formula", "line", "arrow", "circle", "rect",
            "polygon", "polyline", "curve", "angle", "dimension", "bar", "grid",
            "card", "list", "table", "timeline", "graph", "mindmap", "model3d", "quiz",
            "photo", "map", "molecule",
        ]},
        "x": {"type": "NUMBER", "description": "Horizontal position from 0 to 100."},
        "y": {"type": "NUMBER", "description": "Vertical position from 0 to 100."},
        "x2": {"type": "NUMBER", "description": "Second point horizontal position from 0 to 100."},
        "y2": {"type": "NUMBER", "description": "Second point vertical position from 0 to 100."},
        "x3": {"type": "NUMBER", "description": "Third point horizontal position, used by angle."},
        "y3": {"type": "NUMBER", "description": "Third point vertical position, used by angle."},
        "width": {"type": "NUMBER", "description": "Width as percent of drawing area."},
        "height": {"type": "NUMBER", "description": "Height as percent of drawing area."},
        "radius": {"type": "NUMBER", "description": "Radius as percent of the shorter drawing dimension."},
        "text": {"type": "STRING", "description": "Text or formula to display."},
        "label": {"type": "STRING", "description": "Optional short label for a line, angle, or dimension."},
        "anchor": {"type": "STRING", "enum": ["triangle_equation", "triangle_a_label", "triangle_b_label", "triangle_hypotenuse_label"], "description": "Semantic position on the current interactive right triangle. Use this instead of guessing x/y when placing an annotation relative to an existing triangle element."},
        "offset_x": {"type": "NUMBER", "description": "Fine horizontal offset in screen-independent pixels from the semantic anchor."},
        "offset_y": {"type": "NUMBER", "description": "Fine vertical offset in screen-independent pixels from the semantic anchor."},
        "font_size": {"type": "INTEGER", "description": "Text size from 8 to 32."},
        "color": {"type": "STRING", "enum": [
            "cyan", "blue", "purple", "green", "amber", "red", "white", "muted", "pink",
        ]},
        "stroke_width": {"type": "NUMBER", "description": "Line thickness from 0.7 to 6."},
        "fill": {"type": "BOOLEAN", "description": "Fill circles, rectangles, polygons or closed curves with a translucent color."},
        "closed": {"type": "BOOLEAN", "description": "For curve: join the last point to the first for an organic silhouette. At least 3 points; default false for an open smooth stroke."},
        "value": {"type": "NUMBER", "description": "Bar fill from 0 to 100."},
        "divisions": {"type": "INTEGER", "description": "Grid divisions, from 2 to 20."},
        "title": {"type": "STRING", "description": "Title for a card, table, timeline, mind map, quiz or model."},
        "heading": {"type": "STRING", "description": "Heading for a card or list."},
        "items": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Bulleted list items."},
        "columns": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Table column headings."},
        "rows": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "STRING"}}, "description": "Table rows."},
        "events": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "when": {"type": "STRING"}, "text": {"type": "STRING"}
        }}, "description": "Timeline events."},
        "branches": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "text": {"type": "STRING"},
            "items": {"type": "ARRAY", "items": {"type": "STRING"}}
        }}, "description": "Mind map branches."},
        "plots": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "label": {"type": "STRING"},
            "points": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "NUMBER"}}}
        }}, "description": "Graph series; each point is [x,y] normalized from 0 to 100."},
        "dots": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"}, "label": {"type": "STRING"}
        }}},
        "shape": {"type": "STRING", "enum": ["sphere", "cube", "cylinder", "cone", "torus", "capsule", "disc", "pyramid", "ring", "plane", "none"], "description": "Main body of a model3d. Use none when the scene is built only from parts (solar system, molecule...)."},
        "render_style": {"type": "STRING", "enum": ["solid", "glass", "hologram", "wireframe", "glow"], "description": "Surface look: solid = lit and shaded (default); hologram/glass = translucent with scan grid, for layers you must see through; glow = emissive; wireframe only when requested."},
        "rotation_speed": {"type": "NUMBER", "description": "Main body spin speed, 0 to 4."},
        "floor": {"type": "BOOLEAN", "description": "Holographic floor under a model3d (default true)."},
        "camera": {"type": "STRING", "enum": ["sway", "static"], "description": "sway = gentle automatic camera drift (default)."},
        "links": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "from": {"type": "STRING", "description": "id or label of a part."},
            "to": {"type": "STRING", "description": "id or label of a part."},
            "color": {"type": "STRING", "enum": ["cyan", "blue", "purple", "green", "amber", "red", "white", "muted", "pink"]},
            "arrow": {"type": "BOOLEAN"}, "flow": {"type": "BOOLEAN"}, "speed": {"type": "NUMBER"}
        }}, "description": "3D flow connectors between parts, with animated particles (energy, blood, electrons, data)."},
        "parts": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "id": {"type": "STRING", "description": "Stable name so other parts/links can refer to it."},
            "parent": {"type": "STRING", "description": "id/label of the part this one is attached to or orbits."},
            "shape": {"type": "STRING", "enum": ["sphere", "cube", "cylinder", "cone", "torus", "capsule", "disc", "pyramid", "ring", "plane"]},
            "dx": {"type": "NUMBER"}, "dy": {"type": "NUMBER"}, "dz": {"type": "NUMBER", "description": "Offset from the parent; dy positive = up, dz = depth."},
            "size": {"type": "NUMBER", "description": "1 to 60; 20 = same size as the main body."},
            "sx": {"type": "NUMBER"}, "sy": {"type": "NUMBER"}, "sz": {"type": "NUMBER", "description": "Axis stretch 0.05-8 (flat disc, long rod...)."},
            "count": {"type": "INTEGER", "description": "Repeat identical parts 1-60."},
            "arrange": {"type": "STRING", "enum": ["cluster", "ring", "line", "grid", "helix", "shell"]},
            "spread": {"type": "NUMBER"},
            "motion": {"type": "STRING", "enum": ["none", "spin", "orbit", "pulse", "slide", "bob"]},
            "speed": {"type": "NUMBER"},
            "orbit_radius": {"type": "NUMBER"}, "tilt": {"type": "NUMBER", "description": "Orbit plane tilt, degrees."}, "node": {"type": "NUMBER", "description": "Orbit plane rotation, degrees."},
            "color": {"type": "STRING", "enum": ["cyan", "blue", "purple", "green", "amber", "red", "white", "muted", "pink"]},
            "color2": {"type": "STRING", "enum": ["cyan", "blue", "purple", "green", "amber", "red", "white", "muted", "pink"]},
            "opacity": {"type": "NUMBER"}, "glow": {"type": "NUMBER"},
            "render_style": {"type": "STRING", "enum": ["solid", "glass", "hologram", "wireframe", "glow"]},
            "show_path": {"type": "BOOLEAN"}, "label": {"type": "STRING"}
        }}, "description": "Separate parts of a 3D scene, positioned and animated in true 3D."},
        "options": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Clickable quiz options."},
        "answer": {"type": "STRING", "description": "Correct quiz option."},
        "explanation": {"type": "STRING", "description": "Feedback after quiz selection."},
        "query": {"type": "STRING", "description": "For a photo card, a named subject with a Wikipedia article."},
        "url": {"type": "STRING", "description": "For a photo card, a public HTTPS image URL. Private/local addresses are refused."},
        "caption": {"type": "STRING", "description": "Photo caption."},
        "region": {"type": "STRING", "description": "Map region title or geographic context."},
        "pins": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING"}, "lat": {"type": "NUMBER"}, "lon": {"type": "NUMBER"}
        }}, "description": "Map locations using real latitude and longitude."},
        "routes": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "from": {"type": "STRING"}, "to": {"type": "STRING"}, "label": {"type": "STRING"}
        }}, "description": "Routes connecting pin names."},
        "smiles": {"type": "STRING", "description": "SMILES structural notation for a molecule. Supports common atoms, bond orders, branches and ring closures; unsupported stereochemistry is rejected."},
        "atoms": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "element": {"type": "STRING"}, "charge": {"type": "INTEGER"},
            "x": {"type": "NUMBER"}, "y": {"type": "NUMBER"}
        }}, "description": "Explicit atom nodes for a molecule; coordinates are optional percentages."},
        "bonds": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "a": {"type": "INTEGER"}, "b": {"type": "INTEGER"}, "order": {"type": "NUMBER"}
        }}, "description": "Explicit bonds between atom indices, with order 1, 2, 3 or 1.5."},
        "points": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "x": {"type": "NUMBER"},
                    "y": {"type": "NUMBER"},
                },
            },
            "description": "Up to 32 normalized points for polygon/polyline or a smooth curve. Use 4-12 ordered contour points for a recognizable organic shape; closed=true and fill=true for a silhouette.",
        },
    },
    "required": ["type"],
}


def show_visual(parameters: dict, player=None, speak=None) -> str:
    """Draw a declarative diagram on an interactive desktop overlay."""
    if player is None or not callable(getattr(player, "show_visual_board", None)):
        return "VISUAL_UNAVAILABLE: the visual board is not connected to the desktop UI."
    try:
        payload = normalize_visual_payload(parameters or {})
        from core.visual_board import enforce_3d
        _op = str((parameters or {}).get("operation") or "append").strip().lower()
        _notes = all(e.get("type") in {"text", "formula", "quiz"} for e in payload["elements"])
        enforce_3d(payload["elements"], require_model=not (_op == "append" and _notes))
        # Image retrieval runs in this tool's worker thread, never on Qt's painter.
        # A single missing image degrades to a captioned fallback rather than
        # preventing the rest of the teaching scene from appearing.
        for item in payload["elements"]:
            if item.get("type") == "photo":
                from core.visual_assets import enrich_photo_item
                enrich_photo_item(item)
        operation = str((parameters or {}).get("operation") or "append").strip().lower()
        if operation not in {"append", "replace"}:
            operation = "append"
        player.show_visual_board(payload, operation=operation)
    except (TypeError, ValueError) as exc:
        return f"VISUAL_INVALID: {exc}"
    except Exception as exc:
        return f"VISUAL_FAILED: {type(exc).__name__}: {str(exc)[:180]}"
    return (
        f"VISUAL_SHOWN: displayed '{payload['title']}' with "
        f"{len(payload['elements'])} visual elements. "
        "You can modify the diagram with another show_visual call or clear it."
    )


def clear_visual(parameters: dict | None = None, player=None) -> str:
    """Remove the current visual board without affecting the Gemini session."""
    if player is None or not callable(getattr(player, "clear_visual_board", None)):
        return "VISUAL_UNAVAILABLE: the visual board is not connected to the desktop UI."
    player.clear_visual_board()
    return "VISUAL_CLEARED: the on-screen drawing was removed."


TOOL = {
    "name": "show_visual",
    "description": (
        "Show ONE real-time holographic 3D scene on the primary monitor. Every explanation is 3D; flat 2D elements "
        "(line, arrow, circle, rect, polygon, curve, table, graph, timeline, mindmap, map, molecule) are rejected. "
        "Provide a title and one model3d element (x=2, y=3, width=62, height=88) that holds the whole scene: shape "
        "(none or a main body), parts[] (shape sphere/cube/cylinder/cone/torus/capsule/disc/pyramid/ring/plane, size, "
        "color, short label, dx/dy/dz, motion orbit/spin/pulse/bob/slide, parent, orbit_radius, tilt, node, "
        "count+arrange, opacity, glow, render_style solid/glass/hologram/glow) and links [{from,to,color,flow}] for "
        "animated flows. Abstract subjects become spatial 3D metaphors of labelled bodies. Optional short text/formula "
        "captions or a quiz go in the right column (x 67-98), never over the model. DEFAULT operation is append: it "
        "keeps the current board; use replace only when the user asks to start over. For follow-up edits use "
        "inspect_visual then edit_visual. The user can drag the model to rotate it. For a multi-stage explanation use "
        "present_visual_lesson. "
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "enum": ["append", "replace"], "description": "append by default to preserve the current drawing; replace only for an explicit new/start-over request."},
            "title": {"type": "STRING", "description": "Short title shown at the top of the board."},
            "subtitle": {"type": "STRING", "description": "One concise context line."},
            "interactive": {
                "type": "OBJECT",
                "properties": {
                    "kind": {"type": "STRING", "enum": ["right_triangle"]},
                    "a": {"type": "NUMBER", "description": "Initial vertical cathetus length, 0.5 to 10."},
                    "b": {"type": "NUMBER", "description": "Initial horizontal cathetus length, 0.5 to 10."},
                },
                "description": "Use right_triangle for a draggable, live-updating Pythagoras lesson.",
            },
            "layout": {
                "type": "STRING",
                "enum": ["diagram", "geometry", "graph", "formula", "steps",
                         "comparison", "timeline", "science", "freeform"],
            },
            "elements": {
                "type": "ARRAY",
                "items": _ELEMENT_SCHEMA,
                "description": "Ordered vector drawing instructions; usually 3-18 elements.",
            },
        },
        "required": ["title", "elements"],
    },
    "handler": show_visual,
    "tier": "core",
    "brief": "Draw a visual explanation or teaching diagram on screen.",
}


CLEAR_TOOL = {
    "name": "clear_visual",
    "description": (
        "Clear the current on-screen visual diagram when the user asks to erase, close, "
        "remove or start over with the drawing. Does not close JARVIS or end the conversation."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": clear_visual,
    "tier": "core",
    "brief": "Clear the on-screen visual teaching board.",
}
