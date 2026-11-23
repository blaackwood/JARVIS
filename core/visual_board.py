"""Validation and normalization for JARVIS's screen-side visual teaching board.

The model describes a small, declarative set of vector primitives. This module
keeps that payload bounded and safe before it reaches the Qt painter.
"""
from __future__ import annotations

import math

from core.molecule import layout_molecule, parse_smiles

MAX_ELEMENTS = 48
MAX_POINTS = 32
ALLOWED_TYPES = {
    "text", "formula", "line", "arrow", "circle", "rect", "polygon",
    "polyline", "curve", "angle", "dimension", "bar", "grid",
    "card", "list", "table", "timeline", "graph", "mindmap", "model3d", "quiz",
    "photo", "map", "molecule",
}
ALLOWED_COLORS = {
    "cyan", "blue", "purple", "green", "amber", "red", "white",
    "muted", "pink",
}
ALLOWED_LAYOUTS = {
    "diagram", "geometry", "graph", "formula", "steps", "comparison",
    "timeline", "science", "freeform",
}


def _number(value, default: float, low: float, high: float) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            return default
        return max(low, min(high, result))
    except (TypeError, ValueError, OverflowError):
        return default


def _integer(value, default: int, low: int, high: int) -> int:
    return int(round(_number(value, default, low, high)))


def _text(value, default: str = "", limit: int = 240) -> str:
    if value is None:
        value = default
    result = "".join(ch for ch in str(value) if ch in "\n\t" or ord(ch) >= 32)
    return result.strip()[:limit]


_MODEL_SHAPES = {"cube", "sphere", "cylinder", "cone", "torus", "capsule",
                 "disc", "pyramid", "ring", "plane"}
_MODEL_STYLES = {"solid", "wireframe", "glass", "hologram", "glow"}
_MODEL_MOTIONS = {"none", "spin", "orbit", "pulse", "slide", "bob"}
_MODEL_ARRANGE = {"cluster", "ring", "line", "grid", "helix", "shell"}
_MAX_PARTS = 80


def _model_style(value) -> str:
    key = str(value or "").strip().lower()
    return key if key in _MODEL_STYLES else ""


def _model_color(value) -> str:
    key = str(value or "").strip().lower()
    return key if key in ALLOWED_COLORS else ""


def _normalize_parts(raw_parts) -> list:
    """Bounded parts for the 3D engine (holo3d); legacy fields keep working."""
    out = []
    for part in (raw_parts if isinstance(raw_parts, list) else [])[:_MAX_PARTS]:
        if not isinstance(part, dict):
            continue
        shape = str(part.get("shape") or "sphere").strip().lower()
        if shape not in _MODEL_SHAPES:
            shape = "sphere"
        motion = str(part.get("motion") or "none").strip().lower()
        if motion not in _MODEL_MOTIONS:
            motion = "none"
        arrange = str(part.get("arrange") or "cluster").strip().lower()
        if arrange not in _MODEL_ARRANGE:
            arrange = "cluster"
        style = _model_style(part.get("style")) or _model_style(part.get("render_style"))
        out.append({
            "id": _text(part.get("id"), "", 40),
            "parent": _text(part.get("parent"), "", 40),
            "shape": shape,
            "dx": _number(part.get("dx"), 0, -100, 100),
            "dy": _number(part.get("dy"), 0, -100, 100),
            "dz": _number(part.get("dz"), 0, -100, 100),
            "size": _number(part.get("size"), 10, 1, 60),
            "sx": _number(part.get("sx"), 1, 0.05, 8),
            "sy": _number(part.get("sy"), 1, 0.05, 8),
            "sz": _number(part.get("sz"), 1, 0.05, 8),
            "count": _integer(part.get("count"), 1, 1, 60),
            "arrange": arrange,
            "spread": _number(part.get("spread"), 0, 0, 100),
            "motion": motion,
            "speed": _number(part.get("speed"), 1, 0.1, 6),
            "orbit_radius": _number(part.get("orbit_radius"), 0, 0, 150),
            "tilt": _number(part.get("tilt"), 0, -85, 85),
            "node": _number(part.get("node"), 0, -360, 360),
            "color": _model_color(part.get("color")),
            "color2": _model_color(part.get("color2")),
            "opacity": _number(part.get("opacity"), 1, 0.05, 1),
            "glow": _number(part.get("glow"), 0, 0, 1),
            "style": style,
            "render_style": style or "solid",
            "label": _text(part.get("label"), "", 30),
            "show_path": bool(part.get("show_path", motion == "orbit")),
        })
    return out


def _normalize_links(raw_links) -> list:
    out = []
    for link in (raw_links if isinstance(raw_links, list) else [])[:80]:
        if not isinstance(link, dict):
            continue
        src, dst = _text(link.get("from"), "", 40), _text(link.get("to"), "", 40)
        if not src or not dst:
            continue
        out.append({
            "from": src, "to": dst,
            "color": _model_color(link.get("color")),
            "arrow": bool(link.get("arrow", True)),
            "flow": bool(link.get("flow", True)),
            "speed": _number(link.get("speed"), 1, 0.1, 5),
            "label": _text(link.get("label"), "", 30),
        })
    return out


_ATOM_COLOR = {"H": "white", "C": "muted", "N": "blue", "O": "red", "S": "amber",
               "P": "purple", "F": "green", "Cl": "green", "Br": "pink", "I": "purple"}


def _molecule_to_model(item: dict) -> None:
    """Turn a parsed molecule into a 3D ball-and-stick model3d (no flat molecules)."""
    parts, links = [], []
    for index, atom in enumerate(item.get("atoms", [])[:80]):
        symbol = str(atom.get("element") or "C")[:2].capitalize()
        parts.append({
            "id": f"a{index}", "shape": "sphere",
            "dx": (_number(atom.get("x"), 50, 0, 100) - 50) * 1.2,
            "dy": (_number(atom.get("y"), 50, 0, 100) - 50) * 1.2,
            "dz": 9.0 * math.sin(index * 1.9),
            "size": 3.8 if symbol == "H" else 5.5,
            "color": _ATOM_COLOR.get(symbol, "cyan"),
            "label": symbol, "render_style": "solid",
        })
    for bond in item.get("bonds", [])[:80]:
        links.append({"from": f"a{bond['a']}", "to": f"a{bond['b']}", "color": "white",
                      "arrow": False, "flow": False})
    item["type"] = "model3d"
    item["shape"] = "none"
    item["parts"] = _normalize_parts(parts)
    item["links"] = _normalize_links(links)


def normalize_visual_payload(payload: dict) -> dict:
    """Return a bounded, display-ready payload; reject malformed requests."""
    if not isinstance(payload, dict):
        raise ValueError("O quadro visual precisa ser um objeto.")

    title = _text(payload.get("title"), "Explicação visual", 72) or "Explicação visual"
    subtitle = _text(payload.get("subtitle"), "", 150)
    layout = str(payload.get("layout") or "diagram").strip().lower()
    if layout not in ALLOWED_LAYOUTS:
        layout = "diagram"

    raw_elements = payload.get("elements")
    if not isinstance(raw_elements, list) or not raw_elements:
        raise ValueError("Informe pelo menos um elemento para desenhar.")
    if len(raw_elements) > MAX_ELEMENTS:
        raw_elements = raw_elements[:MAX_ELEMENTS]

    elements = []
    for raw in raw_elements:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or "").strip().lower()
        # Gemini occasionally omits `type` on a plain text annotation even
        # though the schema exposes it. Infer only the safe text primitive when
        # a text/label is present; all non-text shapes still require an explicit type.
        if not kind and (raw.get("text") is not None or raw.get("label") is not None):
            kind = "text"
        if kind not in ALLOWED_TYPES:
            continue

        rich = kind in {"card", "list", "table", "timeline", "graph", "mindmap",
                        "model3d", "quiz", "photo", "map", "molecule"}
        item = {
            "id": _text(raw.get("id"), "", 64),
            "type": kind,
            "x": _number(raw.get("x"), 50, 0, 100),
            "y": _number(raw.get("y"), 50, 0, 100),
            "x2": _number(raw.get("x2"), 75, 0, 100),
            "y2": _number(raw.get("y2"), 50, 0, 100),
            "color": str(raw.get("color") or "cyan").strip().lower(),
            "stroke_width": _number(raw.get("stroke_width"), 2, 0.7, 6),
            "text": _text(raw.get("text"), "", 240),
            "label": _text(raw.get("label"), "", 100),
            "anchor": str(raw.get("anchor") or "").strip().lower(),
            "offset_x": _number(raw.get("offset_x"), 0, -500, 500),
            "offset_y": _number(raw.get("offset_y"), 0, -500, 500),
            "font_size": _integer(raw.get("font_size"), 15, 8, 32),
            "width": _number(raw.get("width"), 36 if rich else 20, 0.5, 100),
            "height": _number(raw.get("height"), 32 if rich else 12, 0.5, 100),
            "radius": _number(raw.get("radius"), 8, 0.5, 35),
            "fill": bool(raw.get("fill", False)),
            "value": _number(raw.get("value"), 65, 0, 100),
            "divisions": _integer(raw.get("divisions"), 8, 2, 20),
        }
        if item["color"] not in ALLOWED_COLORS:
            item["color"] = "cyan"
        item["x3"] = _number(raw.get("x3"), 50, 0, 100)
        item["y3"] = _number(raw.get("y3"), 25, 0, 100)

        points = raw.get("points")
        safe_points = []
        if isinstance(points, list):
            for point in points[:MAX_POINTS]:
                if isinstance(point, dict):
                    safe_points.append({
                        "x": _number(point.get("x"), 50, 0, 100),
                        "y": _number(point.get("y"), 50, 0, 100),
                    })
        item["points"] = safe_points
        if kind == "curve":
            item["closed"] = bool(raw.get("closed", False))
            item["fill"] = item["fill"] and item["closed"]
            if len(safe_points) < (3 if item["closed"] else 2):
                continue
        item["title"] = _text(raw.get("title"), "", 80)
        item["heading"] = _text(raw.get("heading"), "", 100)
        item["items"] = [
            _text(value, "", 120) for value in (raw.get("items") or [])[:12]
            if _text(value, "", 120)
        ]
        item["columns"] = [
            _text(value, "", 30) for value in (raw.get("columns") or [])[:6]
        ]
        item["rows"] = [
            [_text(value, "", 80) for value in row[:6]]
            for row in (raw.get("rows") or [])[:12] if isinstance(row, list)
        ]
        item["events"] = [
            {"when": _text(event.get("when"), "", 16),
             "text": _text(event.get("text"), "", 80)}
            for event in (raw.get("events") or [])[:10]
            if isinstance(event, dict)
        ]
        item["branches"] = [
            {"text": _text(branch.get("text"), "", 60),
             "items": [_text(value, "", 60) for value in (branch.get("items") or [])[:6]]}
            for branch in (raw.get("branches") or [])[:8]
            if isinstance(branch, dict)
        ]
        item["plots"] = [
            {"label": _text(series.get("label"), "", 30),
             "points": [
                 {"x": _number(point[0], 50, 0, 100),
                  "y": _number(point[1], 50, 0, 100)}
                 for point in (series.get("points") or [])[:MAX_POINTS]
                 if isinstance(point, (list, tuple)) and len(point) >= 2
             ]}
            for series in (raw.get("plots") or [])[:4]
            if isinstance(series, dict)
        ]
        item["dots"] = [
            {"x": _number(dot.get("x"), 50, 0, 100),
             "y": _number(dot.get("y"), 50, 0, 100),
             "label": _text(dot.get("label"), "", 30)}
            for dot in (raw.get("dots") or [])[:12] if isinstance(dot, dict)
        ]
        # Photo cards contain bytes fetched by the action handler, never a
        # remote URL handed to Qt. The normalizer only preserves bounded inputs.
        item["photo_query"] = _text(raw.get("query") or raw.get("photo_query"), "", 100)
        item["photo_url"] = _text(raw.get("url") or raw.get("photo_url"), "", 2000)
        item["caption"] = _text(raw.get("caption"), "", 140)
        item["credit"] = _text(raw.get("credit"), "", 80)
        item["photo_data"] = b""
        item["photo_mime"] = ""

        item["pins"] = [
            {"name": _text(pin.get("name"), "", 40),
             "lat": _number(pin.get("lat"), 0, -90, 90),
             "lon": _number(pin.get("lon"), 0, -180, 180)}
            for pin in (raw.get("pins") or [])[:12] if isinstance(pin, dict)
            and _text(pin.get("name"), "", 40)
        ]
        item["routes"] = [
            {"from": _text(route.get("from"), "", 40),
             "to": _text(route.get("to"), "", 40),
             "label": _text(route.get("label"), "", 40)}
            for route in (raw.get("routes") or [])[:8] if isinstance(route, dict)
        ]
        item["map_region"] = _text(raw.get("region") or raw.get("map_region"), "", 80)

        item["atoms"] = []
        item["bonds"] = []
        if kind == "molecule":
            smiles = _text(raw.get("smiles"), "", 200)
            if smiles:
                atoms, bonds = parse_smiles(smiles)
                item["atoms"] = layout_molecule(atoms, bonds)
                item["bonds"] = bonds
                item["smiles"] = smiles
            else:
                atoms_raw = raw.get("atoms") or []
                bonds_raw = raw.get("bonds") or []
                atoms = []
                for atom in atoms_raw[:80]:
                    if not isinstance(atom, dict):
                        continue
                    element = _text(atom.get("element"), "", 2)
                    if not element or not element.isalpha():
                        continue
                    has_xy = atom.get("x") is not None and atom.get("y") is not None
                    atoms.append({
                        "element": element[:2],
                        "charge": _integer(atom.get("charge"), 0, -3, 3),
                        "x": _number(atom.get("x"), 50, 0, 100) if has_xy else None,
                        "y": _number(atom.get("y"), 50, 0, 100) if has_xy else None,
                    })
                bonds = []
                for bond in bonds_raw[:160]:
                    if not isinstance(bond, dict):
                        continue
                    a = _integer(bond.get("a"), -1, -1, 79)
                    b = _integer(bond.get("b"), -1, -1, 79)
                    order = _number(bond.get("order"), 1, 1, 3)
                    if a >= 0 and b >= 0 and a < len(atoms) and b < len(atoms) and a != b:
                        bonds.append({"a":a,"b":b,"order":order})
                if atoms and any(a.get("x") is None or a.get("y") is None for a in atoms):
                    atoms = layout_molecule(atoms,bonds)
                item["atoms"] = atoms
                item["bonds"] = bonds
        item["shape"] = str(raw.get("shape") or "cube").strip().lower()
        if item["shape"] not in (_MODEL_SHAPES | {"none"}):
            item["shape"] = "cube"
        item["render_style"] = (
            str(raw.get("render_style") or "solid").strip().lower()
            if str(raw.get("render_style") or "solid").strip().lower() in _MODEL_STYLES
            else "solid"
        )
        item["rotation_speed"] = _number(raw.get("rotation_speed"), 0.8, 0, 4)
        item["parts"] = [
            {"shape": str(part.get("shape") or "sphere").lower()
                        if str(part.get("shape") or "sphere").lower() in {"cube","sphere","cylinder","cone","torus"} else "sphere",
             "dx": _number(part.get("dx"), 0, -40, 40),
             "dy": _number(part.get("dy"), 0, -40, 40),
             "size": _number(part.get("size"), 10, 2, 30),
             "motion": str(part.get("motion") or "none").lower()
                       if str(part.get("motion") or "none").lower() in {"none","spin","orbit","pulse","slide"} else "none",
             "speed": _number(part.get("speed"), 1, 0.1, 4),
             "label": _text(part.get("label"), "", 30),
             "render_style": str(part.get("render_style") or "solid").strip().lower()
                             if str(part.get("render_style") or "solid").strip().lower() in _MODEL_STYLES else "solid"}
            for part in (raw.get("parts") or [])[:12] if isinstance(part, dict)
        ]
        item["parts"] = _normalize_parts(raw.get("parts"))
        item["style"] = _model_style(raw.get("style"))
        item["links"] = _normalize_links(raw.get("links"))
        item["floor"] = bool(raw.get("floor", True))
        camera = str(raw.get("camera") or "").strip().lower()
        item["camera"] = {"motion": "none" if camera in {"static", "none", "fixed"} else "sway"}
        if kind == "model3d" and item["shape"] == "none" and not item["parts"]:
            item["shape"] = "cube"
        item["options"] = [
            _text(value, "", 100) for value in (raw.get("options") or [])[:4]
        ]
        item["answer"] = _text(raw.get("answer"), "", 100)
        item["explanation"] = _text(raw.get("explanation"), "", 240)
        if kind in {"text", "formula"} and not item["text"]:
            item["text"] = item["label"]
        if kind in {"polygon", "polyline"} and len(safe_points) < (3 if kind == "polygon" else 2):
            continue
        if kind in {"text", "formula"} and not item["text"]:
            continue
        if kind in {"card", "list"} and not (item["text"] or item["heading"] or item["title"] or item["items"]):
            continue
        if kind == "table":
            if len(item["columns"]) < 2 or not item["rows"]:
                continue
            item["rows"] = [
                row[:len(item["columns"])] + [""] * max(0, len(item["columns"])-len(row))
                for row in item["rows"]
            ]
        if kind == "timeline" and len(item["events"]) < 2:
            continue
        if kind == "graph" and not (item["plots"] or item["dots"]):
            continue
        if kind == "mindmap" and len(item["branches"]) < 2:
            continue
        if kind == "quiz" and len(item["options"]) < 2:
            continue
        if kind == "photo" and not (item["photo_query"] or item["photo_url"]):
            continue
        if kind == "map":
            pin_names = {pin["name"] for pin in item["pins"]}
            item["routes"] = [
                route for route in item["routes"]
                if route["from"] in pin_names and route["to"] in pin_names
                and route["from"] != route["to"]
            ]
            if not item["pins"]:
                continue
        if kind == "molecule":
            if not item["atoms"]:
                continue
            _molecule_to_model(item)
        elements.append(item)

    if not elements:
        raise ValueError("Não encontrei elementos válidos para desenhar.")

    result = {
        "title": title,
        "subtitle": subtitle,
        "layout": layout,
        "elements": elements,
    }
    raw_interactive = payload.get("interactive")
    if isinstance(raw_interactive, dict):
        kind = str(raw_interactive.get("kind") or "").strip().lower()
        if kind == "right_triangle":
            result["interactive"] = {
                "kind": "right_triangle",
                "a": _number(raw_interactive.get("a"), 3.0, 0.5, 10.0),
                "b": _number(raw_interactive.get("b"), 4.0, 0.5, 10.0),
            }
    return result


def build_right_triangle_payload() -> dict:
    """A guided, interactive right-triangle lesson with a visible worked example."""
    payload = normalize_visual_payload({
        "title": "Triângulo retângulo",
        "subtitle": "Observe os lados: a posição de cada um define seu nome",
        "layout": "geometry",
        "interactive": {"kind": "right_triangle", "a": 3.0, "b": 4.0},
        "elements": [
            {"type": "polygon", "points": [
                {"x": 14, "y": 82}, {"x": 14, "y": 18}, {"x": 65, "y": 82},
            ], "color": "cyan", "stroke_width": 2.8, "fill": True},
            {"type": "angle", "x": 14, "y": 82, "x2": 14, "y2": 18,
             "x3": 65, "y3": 82, "label": "90°", "color": "amber",
             "radius": 7, "stroke_width": 2.2},
            {"type": "formula", "x": 69, "y": 24, "width": 27, "height": 15,
             "font_size": 17, "text": "a² + b² = c²", "color": "cyan"},
        ],
    })
    # Keep the teaching script separate from arbitrary model coordinates. The
    # board renders it in a dedicated, responsive column beside the diagram.
    payload["_teaching_example"] = {
        "heading": "EXEMPLO RESOLVIDO • 3–4–5",
        "question": (
            "Um triângulo retângulo tem catetos de 3 cm e 4 cm. "
            "Quanto mede a hipotenusa?"
        ),
        "steps": [
            {
                "title": "1  Identifique os lados",
                "equation": "a = 3 cm     b = 4 cm     c = ?",
                "detail": "Os catetos são os lados que formam o ângulo de 90°.",
                "triggers": ["vamos ao exemplo", "vamos a um exemplo", "agora um exemplo", "vamos resolver um exemplo", "agora vamos resolver", "considere um triângulo", "para exemplificar"],
            },
            {
                "title": "2  Use o teorema",
                "equation": "a² + b² = c²",
                "detail": "A soma dos quadrados dos catetos é igual ao quadrado da hipotenusa.",
                "triggers": ["fórmula", "formula", "teorema de pitágoras", "teorema de pitagoras"],
            },
            {
                "title": "3  Substitua as medidas",
                "equation": "3² + 4² = c²",
                "detail": "Colocamos 3 e 4 no lugar de a e b.",
                "triggers": ["substituímos", "substituimos", "substituindo", "no lugar de", "três ao quadrado", "3 ao quadrado"],
            },
            {
                "title": "4  Calcule os quadrados",
                "equation": "9 + 16 = 25     →     c² = 25",
                "detail": "3² vale 9; 4² vale 16. Somando, obtemos 25.",
                "triggers": ["somamos", "nove mais dezesseis", "nove mais 16", "vinte e cinco"],
            },
            {
                "title": "5  Encontre a raiz",
                "equation": "c = √25 = 5 cm",
                "detail": "A raiz quadrada de 25 é 5. Essa é a hipotenusa.",
                "triggers": ["raiz quadrada", "raiz de 25", "cinco centímetros", "5 centímetros", "resultado final"],
            },
        ],
    }
    return payload


def fallback_visual_for_request(user_text: str) -> dict | None:
    """Ensure an ordinary Pythagoras lesson gets its interactive visual, not just prose."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(user_text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    words = set(text.split())

    # A biographical question about the mathematician is not a geometry lesson.
    biography_request = bool(re.search(
        r"\b(quem foi|biografia|vida de|historia de)\b.*\bpitagoras\b", text
    ))
    if biography_request:
        return None

    teaching_intent = any(phrase in text for phrase in (
        "explica", "explique", "explicar", "ensina", "ensine", "me mostra",
        "como funciona", "como calcular", "como calcula", "como achar",
        "o que e", "qual e", "entender", "aprende", "resolver", "calcular",
        "demonstra", "demonstrar", "formula",
    ))
    pythagoras_topic = (
        "teorema de pitagoras" in text
        or (
            "pitagoras" in words
            and bool(words & {"triangulo", "retangulo", "hipotenusa", "cateto",
                              "catetos", "geometria", "formula", "matematica"})
        )
        or (
            bool(words & {"hipotenusa", "cateto", "catetos"})
            and bool(words & {"triangulo", "retangulo", "calcular", "calcula",
                              "calculo", "formula", "teorema"})
        )
        or (
            "triangulo" in words and "retangulo" in words and teaching_intent
        )
    )
    if pythagoras_topic and (teaching_intent or "teorema de pitagoras" in text):
        return build_right_triangle_payload()
    return None


ENFORCE_3D = True  # unit tests of the lesson plumbing switch this off

FLAT_2D_TYPES = {
    "line", "arrow", "circle", "rect", "polygon", "polyline", "curve", "angle",
    "dimension", "bar", "grid", "card", "list", "table", "timeline", "mindmap",
    "graph", "map", "molecule",
}


def _scene_quality_problems(elements: list) -> list:
    """Repair a 3D scene in place (ids, spread, links); reject only unusable ones."""
    import math as _m
    import re as _re
    problems = []
    models = [e for e in elements if e.get("type") == "model3d"]
    # Lessons hold one cumulative model per beat: only the last one is judged.
    for e in models[-1:]:
        parts = e.get("parts") or []
        if len(parts) < 3:
            problems.append(f"only {len(parts)} parts; use at least 5 distinct labelled bodies")
            continue
        used = set()
        for i, p in enumerate(parts):
            pid = p.get("id") or _re.sub(r"[^a-z0-9]+", "-", str(p.get("label") or "").lower()).strip("-") or f"p{i}"
            base, n = pid[:36], 2
            while pid in used:
                pid = f"{base}-{n}"
                n += 1
            p["id"] = pid
            used.add(pid)
        free = [p for p in parts if not p.get("parent")]
        if len(free) >= 2 and all(
            abs(p.get("dx", 0)) < 1 and abs(p.get("dy", 0)) < 1 and abs(p.get("dz", 0)) < 1
            for p in free
        ):
            for i, p in enumerate(free):
                ang = 2 * _m.pi * i / len(free)
                p["dx"] = round(45 * _m.cos(ang), 1)
                p["dy"] = round(30 * _m.sin(ang), 1)
                p["dz"] = round(14 * _m.sin(i * 1.7), 1)
        by_label = {str(p.get("label") or "").strip().lower(): p["id"] for p in parts if p.get("label")}
        fixed = []
        for l in e.get("links") or []:
            for k in ("from", "to"):
                v = str(l.get(k) or "")
                if v not in used:
                    l[k] = by_label.get(v.strip().lower(), v)
            if l.get("from") in used and l.get("to") in used and l["from"] != l["to"]:
                fixed.append(l)
        e["links"] = fixed
    return problems


def enforce_3d(elements: list, require_model: bool = True) -> None:
    """JARVIS shows every explanation as a 3D hologram: reject flat 2D drawings."""
    if not ENFORCE_3D:
        return
    flat = sorted({str(e.get("type")) for e in elements if e.get("type") in FLAT_2D_TYPES})
    if flat:
        raise ValueError(
            "2D elements are not allowed (" + ", ".join(flat) + "). Rebuild the scene as ONE "
            "model3d element with parts (shape, size, color, label, motion, parent, "
            "orbit_radius, count+arrange) and links [{from,to,flow}]; use text/formula only "
            "as short captions beside it. Abstract topics become a spatial 3D metaphor."
        )
    if require_model and not any(e.get("type") == "model3d" for e in elements):
        raise ValueError(
            "Every visual must be a 3D scene: include a model3d element with parts and links "
            "(x=2, y=3, width=62, height=88)."
        )
    if require_model:
        problems = _scene_quality_problems(elements)
        if problems:
            raise ValueError(
                "The 3D scene is too poor to teach: " + "; ".join(problems) + ". Rebuild it like a "
                "labelled diagram in space: id + short label on each body, sensible sizes, "
                "positions spread out, parent/orbit for orbiting things, and animated links."
            )
