"""Turns a SEMANTIC lesson (what each thing is and where it sits relative to others)
into the cumulative 3D beats that present_visual_lesson already plays.

The text model never writes coordinates: it only says role + relative place.
The code computes every position once, from the FINAL set of parts, so nothing
jumps around between beats; new pieces glow and older ones calm down.
"""
from __future__ import annotations

import math

MAX_PARTS = 7

# role -> visual defaults (shape, size, color, style, motion)
_ROLES = {
    "core":      dict(shape="sphere",   size=15, color="amber",  style="glow",      motion="pulse"),
    "dark":      dict(shape="sphere",   size=15, color="muted",  style="solid",     motion="none"),
    "shell":     dict(shape="sphere",   size=0,  color="cyan",   style="glass",     motion="none"),
    "disk":      dict(shape="ring",     size=0,  color="amber",  style="hologram",  motion="spin"),
    "body":      dict(shape="sphere",   size=10, color="blue",   style="solid",     motion="none"),
    "small":     dict(shape="sphere",   size=7,  color="white",  style="solid",     motion="none"),
    "container": dict(shape="cube",     size=14, color="cyan",   style="glass",     motion="none"),
    "stack":     dict(shape="cylinder", size=11, color="purple", style="hologram",  motion="none"),
    "energy":    dict(shape="cone",     size=9,  color="amber",  style="glow",      motion="bob"),
    "flow":      dict(shape="capsule",  size=8,  color="blue",   style="hologram",  motion="bob"),
    "living":    dict(shape="sphere",   size=11, color="green",  style="solid",     motion="bob"),
    "danger":    dict(shape="pyramid",  size=10, color="red",    style="glow",      motion="pulse"),
}
_COLORS = {"cyan", "green", "amber", "blue", "pink", "purple", "red", "white", "muted"}
_PLACES = {
    "center": (0, 0, 0), "above": (0, 34, 0), "below": (0, -34, 0),
    "left": (-38, 0, 0), "right": (38, 0, 0), "front": (0, 0, 38), "back": (0, 0, -38),
    "inside": (0, 0, 0),
}
_LATERAL = {  # axis used to separate several parts sharing the same place
    "above": (1, 0, 0), "below": (1, 0, 0), "left": (0, 0, 1), "right": (0, 0, 1),
    "front": (1, 0, 0), "back": (1, 0, 0),
}


def _clip(value, low, high):
    return max(low, min(high, value))


def _label(text, limit=22):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "â€¦"


def _collect(beats):
    """Unique parts in order of first appearance, with the beat they appear in."""
    parts, seen = [], {}
    for b_index, beat in enumerate(beats):
        for raw in (beat.get("add") or []):
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or raw.get("label") or "").strip().lower().replace(" ", "_")[:30]
            if not pid or pid in seen or len(parts) >= MAX_PARTS:
                continue
            part = {"id": pid, "beat": b_index, "raw": raw}
            seen[pid] = part
            parts.append(part)
    return parts


def _place_anatomy(parts):
    """Relative placement around the first part (the subject)."""
    ref_pos, sizes, used = {}, {}, {}
    for part in parts:
        raw = part["raw"]
        role = str(raw.get("role") or "body").lower()
        spec = dict(_ROLES.get(role, _ROLES["body"]))
        place = str(raw.get("place") or ("center" if not ref_pos else "right")).lower()
        if place not in _PLACES and place not in {"around", "ring", "orbit"}:
            place = "right"
        ref_id = str(raw.get("of") or "").strip().lower().replace(" ", "_")
        base_id = ref_id if ref_id in ref_pos else next(iter(ref_pos), None)
        base = ref_pos.get(base_id, (0.0, 0.0, 0.0))
        base_size = sizes.get(base_id, 15)
        index = used.get((base_id, place), 0)
        used[(base_id, place)] = index + 1
        part["motion"], part["parent"], part["orbit_radius"] = spec["motion"], "", 0

        if not ref_pos:                       # the subject: always the center
            pos = (0.0, 0.0, 0.0)
            spec["size"] = spec["size"] or 15
        elif place == "around":               # shell enclosing the base
            pos = base
            spec["size"] = base_size * 1.55 + 3 * index
        elif place == "ring":                 # flat disk around the base
            pos = base
            spec["shape"] = "ring"
            spec["size"] = base_size * 2.7 + 4 * index
        elif place == "orbit":
            radius = base_size * 2.2 + 12 * index + 16
            angle = math.radians(35 + index * 85)
            pos = (base[0] + radius * math.cos(angle), base[1] + 6 * index, base[2] + radius * math.sin(angle))
            part["motion"], part["parent"], part["orbit_radius"] = "orbit", base_id or "", radius
            spec["size"] = min(spec["size"] or 8, 9)
            if spec["motion"] != "orbit":
                spec["motion"] = "orbit"
        else:
            dx, dy, dz = _PLACES[place]
            scale = 0.7 + base_size / 30.0
            lateral = _LATERAL.get(place, (0, 0, 0))
            shift = ((index + 1) // 2) * 24 * (1 if index % 2 else -1) if index else 0
            pos = (base[0] + dx * scale + lateral[0] * shift,
                   base[1] + dy * scale + lateral[1] * shift,
                   base[2] + dz * scale + lateral[2] * shift)
            if place == "inside":
                spec["size"] = min(spec["size"], base_size * 0.45)
        if not spec["size"]:
            spec["size"] = 10
        part["pos"], part["spec"] = pos, spec
        ref_pos[part["id"]], sizes[part["id"]] = pos, spec["size"]


def _place_sequence(parts, kind):
    """chain/timeline: left to right. cycle: on a circle. compare: two columns."""
    count = len(parts)
    for i, part in enumerate(parts):
        role = str(part["raw"].get("role") or "body").lower()
        spec = dict(_ROLES.get(role, _ROLES["body"]))
        spec["size"] = spec["size"] or 11
        if kind == "cycle":
            angle = -math.pi / 2 + 2 * math.pi * i / max(count, 3)
            pos = (46 * math.cos(angle), -4, 46 * math.sin(angle) * 0.8)
        elif kind == "compare":
            side = -1 if str(part["raw"].get("group") or ("a" if i < (count + 1) // 2 else "b")).lower() == "a" else 1
            row = sum(1 for p in parts[:i] if (p.get("side") == side))
            part["side"] = side
            pos = (side * 38, 22 - row * 26, 0)
        else:  # chain
            x = -52 + (104 * i / max(count - 1, 1))
            pos = (x, 9 if i % 2 else -9, 0)
        part["pos"], part["spec"] = pos, spec
        part["motion"], part["parent"], part["orbit_radius"] = spec["motion"], "", 0


def _color(raw, spec):
    color = str(raw.get("color") or "").lower()
    return color if color in _COLORS else spec["color"]


def compile_lesson(data: dict) -> dict | None:
    """Semantic lesson -> {"title", "beats":[{"say","elements":[model3d]}]}. None if unusable."""
    beats_in = [b for b in (data.get("beats") or []) if isinstance(b, dict)]
    if not beats_in:
        return None
    if any("elements" in b for b in beats_in):
        # Accept the already-compiled format only when every beat still obeys
        # the current 3D-only contract. Legacy flat drawings are rejected here
        # so the director can retry with semantic parts/links rather than
        # handing a 2D board to the strict visual renderer.
        from core.visual_board import enforce_3d, normalize_visual_payload
        normalized_beats = []
        for beat in beats_in:
            raw_elements = beat.get("elements")
            if not isinstance(raw_elements, list) or not raw_elements:
                return None
            try:
                payload = normalize_visual_payload({
                    "title": data.get("title") or "Aula",
                    "elements": raw_elements,
                })
                models = [e for e in payload["elements"] if e.get("type") == "model3d"]
                if len(models) != 1:
                    return None
                if any(e.get("type") not in {"model3d", "text", "formula", "quiz"}
                       for e in payload["elements"]):
                    return None
                enforce_3d(payload["elements"], require_model=True)
            except (TypeError, ValueError):
                return None
            normalized = dict(beat)
            normalized["elements"] = payload["elements"]
            normalized_beats.append(normalized)
        result = dict(data)
        result["beats"] = normalized_beats
        return result
    kind = str(data.get("archetype") or "anatomy").lower()
    parts = _collect(beats_in)
    if len(parts) < 3:
        return None
    if kind in {"chain", "timeline", "process", "cycle", "compare"}:
        _place_sequence(parts, "chain" if kind in {"timeline", "process"} else kind)
    else:
        _place_anatomy(parts)

    ids = {p["id"] for p in parts}
    out_beats = []
    for b_index, beat in enumerate(beats_in):
        shown = [p for p in parts if p["beat"] <= b_index]
        link_ids = {str(x.get(k) or "").lower() for x in (beat.get("links") or []) if isinstance(x, dict) for k in ("from", "to")}
        focus_id = str(beat.get("focus") or "").strip().lower().replace(" ", "_")
        if not shown:
            continue
        model_parts = []
        for p in shown:
            raw, spec, new = p["raw"], p["spec"], p["beat"] == b_index
            model_parts.append({
                "id": p["id"], "shape": spec["shape"],
                "size": round(_clip(float(spec["size"]), 4, 44), 1),
                "color": _color(raw, spec), "render_style": spec["style"],
                "label": _label(raw.get("label") or p["id"].replace("_", " ").title()),
                "dx": round(_clip(p["pos"][0], -80, 80), 1),
                "dy": round(_clip(p["pos"][1], -80, 80), 1),
                "dz": round(_clip(p["pos"][2], -80, 80), 1),
                "motion": p["motion"], "parent": p["parent"], "orbit_radius": round(p["orbit_radius"], 1),
                "glow": 0.95 if (new or p["id"] == focus_id) else (0.7 if p["id"] in link_ids else 0.15),
                "opacity": 1.0 if new else 0.8,
            })
        # Invisible anchors where the NEXT parts will appear, so the 3D camera frames the
        # final picture from the first beat instead of re-zooming every time a part is added.
        shown_ids = {p["id"] for p in shown}
        for g in parts:
            if g["id"] in shown_ids:
                continue
            gparent = g["parent"] if g["parent"] in shown_ids else ""
            model_parts.append({
                "id": "_ghost_" + g["id"], "shape": "sphere", "size": 1.2, "color": "muted",
                "render_style": "solid", "label": "",
                "dx": round(_clip(g["pos"][0], -80, 80), 1),
                "dy": round(_clip(g["pos"][1], -80, 80), 1),
                "dz": round(_clip(g["pos"][2], -80, 80), 1),
                "motion": g["motion"] if gparent or g["motion"] != "orbit" else "none",
                "parent": gparent, "orbit_radius": round(g["orbit_radius"], 1) if gparent else 0,
                "glow": 0.0, "opacity": 0.05,
            })
        links, seen_links = [], set()
        for b in beats_in[: b_index + 1]:
            for ln in (b.get("links") or []):
                if not isinstance(ln, dict):
                    continue
                src, dst = str(ln.get("from") or "").lower(), str(ln.get("to") or "").lower()
                key = (src, dst)
                if src in ids and dst in ids and src != dst and key not in seen_links \
                        and src in {p["id"] for p in shown} and dst in {p["id"] for p in shown}:
                    seen_links.add(key)
                    links.append({"from": src, "to": dst, "color": "white", "flow": True,
                                  "label": _label(ln.get("label"), 20)})
        if kind in {"chain", "timeline", "process", "cycle"} and not links:
            order = [p["id"] for p in shown]
            pairs = list(zip(order, order[1:])) + ([(order[-1], order[0])] if kind == "cycle" and len(order) > 2 else [])
            links = [{"from": a, "to": b, "color": "white", "flow": True, "label": ""} for a, b in pairs]
        out_beats.append({
            "say": " ".join(str(beat.get("say") or "").split())[:178],
            "elements": [{"type": "model3d", "shape": "none", "x": 2, "y": 3, "width": 62, "height": 88,
                          "parts": model_parts, "links": links}],
        })
    if len(out_beats) < 3 or not all(b["say"] for b in out_beats):
        return None
    return {"title": str(data.get("title") or "Aula")[:72], "beats": out_beats}




