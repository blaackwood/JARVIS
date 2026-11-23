"""Real-time holographic 3D for the JARVIS visual board.

The board used to fake 3D with a CPU triangle rasteriser. This module renders
real scenes on the GPU instead (OpenGL 3.3 core through PyQt6.QtOpenGL, no extra
package): perspective camera, depth buffer, per-pixel lighting, fresnel rims,
holographic grid shading, orbit paths, animated flow particles and bloom.

It renders *offscreen* into a QImage that the existing QPainter overlay simply
draws, so the board keeps its translucent window, focus rules, drag handling and
progressive reveal untouched. Everything here runs on the Qt GUI thread (the
overlay's paintEvent). If OpenGL is unavailable for any reason, ``get_renderer``
returns ``None`` and the caller falls back to the old software renderer.
"""
from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache

import numpy as np

_LOG = logging.getLogger(__name__)

# Same palette as the board (visual_board._COLORS), as 0-255 triples.
PALETTE = {
    "cyan": (87, 224, 255), "blue": (100, 158, 255), "purple": (185, 139, 255),
    "green": (105, 230, 172), "amber": (255, 194, 104), "red": (255, 112, 128),
    "white": (238, 246, 255), "muted": (149, 177, 195), "pink": (255, 143, 203),
}

SHAPES = ("sphere", "cube", "cylinder", "cone", "torus", "capsule",
          "disc", "pyramid", "ring", "plane")

# Lines of the holographic surface grid per shape: (along u, along v).
GRID_LINES = {
    "sphere": (24.0, 12.0), "cube": (4.0, 4.0), "cylinder": (24.0, 4.0),
    "cone": (24.0, 6.0), "torus": (32.0, 10.0), "capsule": (24.0, 10.0),
    "disc": (16.0, 3.0), "pyramid": (4.0, 4.0), "ring": (36.0, 3.0),
    "plane": (10.0, 10.0),
}


def rgb(color) -> tuple[float, float, float]:
    """Palette name or 0-255 triple -> 0-1 floats."""
    if isinstance(color, str):
        color = PALETTE.get(color.strip().lower(), PALETTE["cyan"])
    r, g, b = color[:3]
    return (r / 255.0, g / 255.0, b / 255.0)


# ── mesh generation ──────────────────────────────────────────────────────────
# Interleaved float32 [pos3, normal3, uv2] plus a uint32 triangle index list.
# Every primitive fits in a unit bounding sphere (cube: half-edge 1).

def _orient(verts: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Flip every triangle whose winding disagrees with its vertex normals."""
    p = verts[:, 0:3]
    n = verts[:, 3:6]
    a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
    geometric = np.cross(b - a, c - a)
    wanted = n[tri[:, 0]] + n[tri[:, 1]] + n[tri[:, 2]]
    flip = np.einsum("ij,ij->i", geometric, wanted) < 0
    out = tri.copy()
    out[flip, 1], out[flip, 2] = tri[flip, 2], tri[flip, 1]
    return out


def _surface(nu: int, nv: int, fn):
    """Sample a parametric surface on a (nu+1)x(nv+1) grid."""
    us = np.linspace(0.0, 1.0, nu + 1)
    vs = np.linspace(0.0, 1.0, nv + 1)
    u, v = np.meshgrid(us, vs, indexing="ij")
    pos, nrm = fn(u, v)
    uv = np.stack([u, v], -1)
    verts = np.concatenate([pos, nrm, uv], -1).reshape(-1, 8).astype(np.float32)
    i, j = np.meshgrid(np.arange(nu), np.arange(nv), indexing="ij")
    a = (i * (nv + 1) + j).ravel()
    b = ((i + 1) * (nv + 1) + j).ravel()
    c = ((i + 1) * (nv + 1) + j + 1).ravel()
    d = (i * (nv + 1) + j + 1).ravel()
    tri = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    return verts, tri.astype(np.uint32)


def _merge(parts):
    verts, tris, base = [], [], 0
    for v, t in parts:
        verts.append(v)
        tris.append(t + base)
        base += len(v)
    verts = np.concatenate(verts)
    tri = np.concatenate(tris).astype(np.uint32)
    return verts, _orient(verts, tri)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def _sphere(nu=64, nv=40):
    def fn(u, v):
        th, ph = u * 2 * np.pi, v * np.pi
        n = np.stack([np.sin(ph) * np.cos(th), np.cos(ph), np.sin(ph) * np.sin(th)], -1)
        return n, n
    return _merge([_surface(nu, nv, fn)])


def _torus(minor=0.34, nu=64, nv=28):
    def fn(u, v):
        th, ph = u * 2 * np.pi, v * 2 * np.pi
        c = np.stack([np.cos(th), np.zeros_like(th), np.sin(th)], -1)
        n = np.stack([np.cos(ph) * np.cos(th), np.sin(ph), np.cos(ph) * np.sin(th)], -1)
        return c + n * minor, n
    return _merge([_surface(nu, nv, fn)])


def _cap(y, up, radius=1.0, nu=48):
    def fn(u, v):
        th = u * 2 * np.pi
        pos = np.stack([v * radius * np.cos(th), np.full_like(th, y), v * radius * np.sin(th)], -1)
        nrm = np.zeros_like(pos)
        nrm[..., 1] = 1.0 if up else -1.0
        return pos, nrm
    return _surface(nu, 2, fn)


def _cylinder(half=1.0, nu=48):
    def side(u, v):
        th = u * 2 * np.pi
        pos = np.stack([np.cos(th), half * (1 - 2 * v), np.sin(th)], -1)
        nrm = np.stack([np.cos(th), np.zeros_like(th), np.sin(th)], -1)
        return pos, nrm
    return _merge([_surface(nu, 4, side), _cap(half, True, nu=nu), _cap(-half, False, nu=nu)])


def _cone(nu=48):
    def side(u, v):
        th = u * 2 * np.pi
        pos = np.stack([v * np.cos(th), 1 - 2 * v, v * np.sin(th)], -1)
        nrm = _unit(np.stack([2 * np.cos(th), np.ones_like(th), 2 * np.sin(th)], -1))
        return pos, nrm
    return _merge([_surface(nu, 8, side), _cap(-1.0, False, nu=nu)])


def _capsule(nu=48, nv=32):
    """Radius 0.5, straight section 1.0 -> total length 2 (fits the unit sphere)."""
    def fn(u, v):
        th = u * 2 * np.pi
        top = v < 0.25
        bot = v > 0.75
        ph_top = (v / 0.25) * (np.pi / 2)
        ph_bot = np.pi / 2 + ((v - 0.75) / 0.25) * (np.pi / 2)
        ph = np.where(top, ph_top, ph_bot)
        sph = np.stack([np.sin(ph) * np.cos(th), np.cos(ph), np.sin(ph) * np.sin(th)], -1)
        cyl_n = np.stack([np.cos(th), np.zeros_like(th), np.sin(th)], -1)
        t = np.clip((v - 0.25) / 0.5, 0, 1)
        cyl_p = np.stack([0.5 * np.cos(th), 0.5 - t, 0.5 * np.sin(th)], -1)
        centre = np.where(top[..., None], np.array([0, 0.5, 0.0]), np.array([0, -0.5, 0.0]))
        pos = np.where((top | bot)[..., None], 0.5 * sph + centre, cyl_p)
        nrm = np.where((top | bot)[..., None], sph, cyl_n)
        return pos, nrm
    return _merge([_surface(nu, nv, fn)])


def _cube():
    faces = [
        ((1, 0, 0), (0, 0, -1), (0, 1, 0)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        ((0, 1, 0), (1, 0, 0), (0, 0, -1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    ]
    parts = []
    for normal, su, sv in faces:
        n, su, sv = np.array(normal, float), np.array(su, float), np.array(sv, float)

        def fn(u, v, n=n, su=su, sv=sv):
            pos = n + su * (2 * u[..., None] - 1) + sv * (2 * v[..., None] - 1)
            return pos, np.broadcast_to(n, pos.shape)
        parts.append(_surface(1, 1, fn))
    return _merge(parts)


def _pyramid():
    apex = np.array([0, 1.0, 0])
    corners = [np.array(c, float) for c in ((1, -1, 1), (1, -1, -1), (-1, -1, -1), (-1, -1, 1))]
    parts = []
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        n = _unit(np.cross(b - a, apex - a))
        verts = np.array([[*a, *n, 0, 0], [*b, *n, 1, 0], [*apex, *n, 0.5, 1]], np.float32)
        parts.append((verts, np.array([[0, 1, 2]], np.uint32)))

    def base(u, v):
        pos = np.stack([2 * u - 1, np.full_like(u, -1.0), 2 * v - 1], -1)
        nrm = np.zeros_like(pos)
        nrm[..., 1] = -1.0
        return pos, nrm
    parts.append(_surface(1, 1, base))
    return _merge(parts)


def _ring(inner=0.62, nu=96):
    def make(sign):
        def fn(u, v):
            th = u * 2 * np.pi
            r = inner + v * (1 - inner)
            pos = np.stack([r * np.cos(th), np.zeros_like(th), r * np.sin(th)], -1)
            nrm = np.zeros_like(pos)
            nrm[..., 1] = sign
            return pos, nrm
        return _surface(nu, 3, fn)
    return _merge([make(1.0), make(-1.0)])


def _plane():
    def make(sign):
        def fn(u, v):
            pos = np.stack([2 * u - 1, np.zeros_like(u), 2 * v - 1], -1)
            nrm = np.zeros_like(pos)
            nrm[..., 1] = sign
            return pos, nrm
        return _surface(8, 8, fn)
    return _merge([make(1.0), make(-1.0)])


@lru_cache(maxsize=None)
def mesh(name: str):
    """(vertices float32 Nx8, indices uint32 M*3) for a named primitive."""
    if name == "sphere":
        return _sphere()
    if name == "cube":
        return _cube()
    if name == "cylinder":
        return _cylinder(1.0)
    if name == "disc":
        return _cylinder(0.07)
    if name == "cone":
        return _cone()
    if name == "torus":
        return _torus()
    if name == "capsule":
        return _capsule()
    if name == "pyramid":
        return _pyramid()
    if name == "ring":
        return _ring()
    if name == "plane":
        return _plane()
    if name.startswith("orbit:"):
        # Thin torus whose tube/major ratio was chosen to keep a constant line weight.
        return _torus(minor=float(name.split(":", 1)[1]), nu=160, nv=6)
    raise KeyError(name)


# Orbit-line thickness classes (tube radius / orbit radius).
ORBIT_RATIOS = (0.004, 0.006, 0.009, 0.013, 0.019, 0.028, 0.042)


def orbit_mesh_name(radius: float, thickness: float) -> str:
    ratio = thickness / max(radius, 1e-6)
    best = min(ORBIT_RATIOS, key=lambda r: abs(r - ratio))
    return f"orbit:{best}"


# ── scene model ──────────────────────────────────────────────────────────────
_U = 22.0                       # board "percent offsets" -> world units
MAX_OBJECTS = 140
STYLE_IDS = {"solid": 0, "glass": 1, "hologram": 1, "wireframe": 2, "glow": 3}
_AUTO_COLORS = ("cyan", "amber", "green", "pink", "purple", "blue", "red", "white")
_BODY_RADIUS = {"cube": 1.45, "pyramid": 1.4, "torus": 1.34, "ring": 1.0}


def _num(value, default=0.0):
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _style_id(*names) -> int:
    for name in names:
        key = str(name or "").strip().lower()
        if key in STYLE_IDS:
            return STYLE_IDS[key]
    return 0


def _fib_sphere(k: int, n: int):
    golden = math.pi * (3.0 - math.sqrt(5.0))
    y = 1.0 - 2.0 * (k + 0.5) / max(1, n)
    r = math.sqrt(max(0.0, 1.0 - y * y))
    a = golden * k
    return (math.cos(a) * r, y, math.sin(a) * r)


def _arrangement(kind: str, n: int, spread: float):
    """Local (x, y, z) offsets, in world units, for `count` identical parts."""
    pts = []
    for k in range(n):
        if kind == "ring":
            a = math.tau * k / n
            pts.append((spread * math.cos(a), 0.0, spread * math.sin(a)))
        elif kind == "line":
            pts.append((spread * (2.0 * k / max(1, n - 1) - 1.0), 0.0, 0.0))
        elif kind == "grid":
            side = max(1, math.ceil(math.sqrt(n)))
            gx, gz = k % side, k // side
            step = 2.0 * spread / max(1, side - 1)
            pts.append((-spread + gx * step, 0.0, -spread + gz * step))
        elif kind == "helix":
            a = k * 0.62
            pts.append((spread * math.cos(a), spread * 2.4 * (k / max(1, n - 1) - 0.5) * 2.0,
                        spread * math.sin(a)))
        elif kind == "shell":
            x, y, z = _fib_sphere(k, n)
            pts.append((x * spread, y * spread, z * spread))
        else:  # cluster: packed ball
            x, y, z = _fib_sphere(k, n)
            rho = ((k + 1) / n) ** (1.0 / 3.0)
            pts.append((x * spread * rho, y * spread * rho, z * spread * rho))
    return pts


class Scene:
    """Compiled, animation-ready description of one stage of 3D content."""
    __slots__ = ("objs", "links", "floor", "center", "radius", "floor_y", "extent",
                 "order", "sway", "has_parts", "signature", "labels_on", "sp", "sr")

    def __init__(self):
        self.objs, self.links, self.order = [], [], []
        self.floor, self.sway, self.has_parts, self.labels_on = False, True, False, True
        self.center = np.zeros(3)
        self.radius, self.floor_y, self.extent = 2.0, -1.2, 2.0
        self.signature = ""


_SIG_KEYS = ("shape", "parts", "links", "color", "style", "render_style", "rotation_speed",
             "floor", "camera", "stage", "title")


def signature(items) -> str:
    raw = repr([[it.get(k) for k in _SIG_KEYS] for it in items])
    return hashlib.blake2s(raw.encode("utf-8", "ignore"), digest_size=10).hexdigest()


def compile_scene(items: list[dict]) -> Scene:
    scene = Scene()
    scene.signature = signature(items)
    by_ref: dict[str, int] = {}
    pending_parent: list[tuple[int, str]] = []
    zero_orbit_count: dict[str, int] = {}
    auto_color = 0

    for it_index, it in enumerate(items):
        if it.get("floor") is False:
            scene.floor = False
        cam = it.get("camera") or {}
        if isinstance(cam, dict) and str(cam.get("motion", "")).lower() == "none":
            scene.sway = False
        base_color = it.get("color") or "cyan"
        item_style = _style_id(it.get("style"), it.get("render_style"))
        main = str(it.get("shape") or "none").lower()
        if main in SHAPES:
            scene.objs.append({
                "id": f"{it.get('id') or 'model'}:main", "shape": main, "parent": None,
                "off": (0.0, 0.0, 0.0), "size": 1.0, "stretch": (1.0, 1.0, 1.0),
                "color": rgb(base_color), "opacity": 1.0, "glow": 0.0, "style": item_style,
                "motion": "spin", "speed": _num(it.get("rotation_speed"), 0.8),
                "label": "", "item": it_index, "main": True, "path": False,
                "tilt": 0.0, "node": 0.0, "orbit_r": 0.0, "phase0": 0.0, "level": 0.0,
            })
        parts = it.get("parts") or []
        for part in parts:
            if not isinstance(part, dict) or len(scene.objs) >= MAX_OBJECTS:
                continue
            shape = str(part.get("shape") or "sphere").lower()
            shape = shape if shape in SHAPES else "sphere"
            color = part.get("color")
            if not color:
                color = _AUTO_COLORS[auto_color % len(_AUTO_COLORS)]
                auto_color += 1
            color2 = part.get("color2")
            count = int(_clamp(_num(part.get("count"), 1), 1, 60))
            size = _clamp(_num(part.get("size"), 10), 1.0, 60.0) / 20.0
            stretch = (_clamp(_num(part.get("sx"), 1.0), 0.05, 8.0),
                       _clamp(_num(part.get("sy"), 1.0), 0.05, 8.0),
                       _clamp(_num(part.get("sz"), 1.0), 0.05, 8.0))
            off = (_num(part.get("dx")) / _U, -_num(part.get("dy")) / _U, _num(part.get("dz")) / _U)
            motion = str(part.get("motion") or "none").lower()
            motion = motion if motion in {"none", "spin", "orbit", "pulse", "slide", "bob"} else "none"
            offsets = [(0.0, 0.0, 0.0)]
            if count > 1:
                spread = _num(part.get("spread"), 0.0) / _U
                if spread <= 0:
                    spread = size * (count ** (1.0 / 3.0)) * 1.1
                offsets = _arrangement(str(part.get("arrange") or "cluster").lower(), count, spread)
            parent_ref = str(part.get("parent") or "").strip()
            pid = str(part.get("id") or f"p{it_index}_{len(scene.objs)}")
            for k, extra in enumerate(offsets):
                if len(scene.objs) >= MAX_OBJECTS:
                    break
                use_color = color2 if (color2 and k % 2 == 1) else color
                o_off = (off[0] + extra[0], off[1] + extra[1], off[2] + extra[2])
                orbit_r = 0.0
                if motion == "orbit":
                    orbit_r = _num(part.get("orbit_radius")) / _U
                    if orbit_r <= 0:
                        orbit_r = math.hypot(o_off[0], o_off[2])
                phase0 = math.atan2(o_off[2], o_off[0]) if orbit_r > 0.05 else 0.0
                obj = {
                    "id": pid if count == 1 else f"{pid}#{k}", "shape": shape, "parent": None,
                    "off": o_off, "size": size, "stretch": stretch, "color": rgb(use_color),
                    "opacity": _clamp(_num(part.get("opacity"), 1.0), 0.05, 1.0),
                    "glow": _clamp(_num(part.get("glow"), 0.0), 0.0, 1.0),
                    "style": _style_id(part.get("style")) if part.get("style") else item_style,
                    "motion": motion, "speed": _clamp(_num(part.get("speed"), 1.0), 0.05, 6.0),
                    "label": str(part.get("label") or "") if k == 0 else "",
                    "item": it_index, "main": False, "path": bool(part.get("show_path", motion == "orbit")),
                    "tilt": math.radians(_clamp(_num(part.get("tilt")), -85, 85)),
                    "node": math.radians(_num(part.get("node"))),
                    "orbit_r": orbit_r, "phase0": phase0, "level": o_off[1],
                    "_group": parent_ref or "~root",
                }
                idx = len(scene.objs)
                scene.objs.append(obj)
                for ref in (obj["id"], pid, str(part.get("label") or "").strip().lower()):
                    if ref and ref not in by_ref:
                        by_ref[ref] = idx
                if parent_ref:
                    pending_parent.append((idx, parent_ref))
        for link in (it.get("links") or [])[:80]:
            if isinstance(link, dict):
                scene.links.append(dict(link, _item=it_index))

    # resolve parents (no cycles; a missing parent just means "scene origin")
    for idx, ref in pending_parent:
        target = by_ref.get(ref) if ref in by_ref else by_ref.get(ref.lower())
        if target is None or target == idx:
            continue
        seen, cur, ok = {idx}, target, True
        while cur is not None:
            if cur in seen:
                ok = False
                break
            seen.add(cur)
            cur = scene.objs[cur]["parent"]
        if ok:
            scene.objs[idx]["parent"] = target

    # orbiters with no explicit offset get their own lane around the parent
    for idx, o in enumerate(scene.objs):
        if o["motion"] == "orbit" and o["orbit_r"] <= 0.05:
            key = str(o["parent"])
            lane = zero_orbit_count.get(key, 0)
            zero_orbit_count[key] = lane + 1
            o["orbit_r"] = 1.7 + 0.85 * lane
            o["phase0"] = lane * 2.399
    scene.has_parts = any(not o["main"] for o in scene.objs)
    if scene.has_parts and not any(o["main"] for o in scene.objs):
        scene.sway = scene.sway
    depth = []
    for o in scene.objs:
        d, cur = 0, o["parent"]
        while cur is not None and d < 12:
            d += 1
            cur = scene.objs[cur]["parent"]
        depth.append(d)
    scene.order = sorted(range(len(scene.objs)), key=lambda i: depth[i])
    _fit_bounds(scene)
    return scene


def _rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _state(o, parent_pos, t):
    """World position, own spin about Y, and size multiplier at time t."""
    off = np.array(o["off"], float)
    spin, mul = 0.0, 1.0
    motion, speed = o["motion"], o["speed"]
    if motion == "orbit":
        r = o["orbit_r"]
        w = 1.05 * speed / max(r, 0.5) ** 0.65
        a = o["phase0"] + w * t
        local = np.array([r * math.cos(a), o["level"], r * math.sin(a)])
        if o["tilt"]:
            local = _rot_x(o["tilt"]) @ local
        if o["node"]:
            local = _rot_y(o["node"]) @ local
        off = local
        spin = t * 0.9 * speed
    elif motion == "spin":
        spin = t * (speed if o["main"] else 1.4 * speed)
    elif motion == "pulse":
        mul = 1.0 + 0.14 * math.sin(t * 2.2 * speed)
    elif motion == "slide":
        off = off + np.array([0.42 * math.sin(t * 1.3 * speed), 0.0, 0.0])
    elif motion == "bob":
        off = off + np.array([0.0, 0.2 * math.sin(t * 1.6 * speed), 0.0])
    return parent_pos + off, spin, mul


def _positions(scene: Scene, t: float):
    pos = [None] * len(scene.objs)
    spin = [0.0] * len(scene.objs)
    mul = [1.0] * len(scene.objs)
    for i in scene.order:
        o = scene.objs[i]
        parent = np.zeros(3) if o["parent"] is None else pos[o["parent"]]
        pos[i], spin[i], mul[i] = _state(o, parent, t)
    return pos, spin, mul


def _fit_bounds(scene: Scene) -> None:
    """Tight bounding sphere over a sweep of the animation so the camera never clips."""
    if not scene.objs:
        return
    samples = []
    lo = np.full(3, 1e9)
    hi = np.full(3, -1e9)
    for step in range(0, 30):
        pos, _s, mul = _positions(scene, step * 0.83)
        for i, o in enumerate(scene.objs):
            r = o["size"] * max(o["stretch"]) * _BODY_RADIUS.get(o["shape"], 1.0) * mul[i]
            samples.append((pos[i], r))
            lo = np.minimum(lo, pos[i] - r)
            hi = np.maximum(hi, pos[i] + r)
    centre = (lo + hi) / 2.0
    half = (hi - lo) / 2.0
    scene.center = centre
    scene.sp = np.array([q[0] for q in samples])
    scene.sr = np.array([q[1] for q in samples])
    scene.radius = max(0.6, max(float(np.linalg.norm(p - centre)) + r for p, r in samples))
    scene.floor_y = float(lo[1]) - 0.07 * scene.radius
    scene.extent = max(1.0, float(max(half[0], half[2])) * 1.35)


def ease_out_back(x: float) -> float:
    x = _clamp(x, 0.0, 1.0)
    c1, c3 = 1.2, 2.2
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ── matrices ─────────────────────────────────────────────────────────────────

def _perspective(fov_y: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(fov_y / 2.0)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def _look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye, target, up = np.array(eye, float), np.array(target, float), np.array(up, float)
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= max(np.linalg.norm(s), 1e-9)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def _model(pos, spin, scale3, tilt=0.0) -> np.ndarray:
    r = _rot_y(spin)
    if tilt:
        r = r @ _rot_x(tilt)
    m = np.eye(4)
    m[:3, :3] = r * np.array(scale3)[None, :]
    m[:3, 3] = pos
    return m


def _align_y(direction) -> np.ndarray:
    """Rotation taking +Y to ``direction`` (unit)."""
    d = np.array(direction, float)
    d /= max(np.linalg.norm(d), 1e-9)
    y = np.array([0.0, 1.0, 0.0])
    v = np.cross(y, d)
    c = float(np.dot(y, d))
    if c < -0.9999:
        return np.diag([1.0, -1.0, -1.0])
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def segment_model(p0, p1, radius) -> np.ndarray:
    p0, p1 = np.array(p0, float), np.array(p1, float)
    d = p1 - p0
    length = max(float(np.linalg.norm(d)), 1e-6)
    m = np.eye(4)
    m[:3, :3] = _align_y(d) * np.array([radius, length / 2.0, radius])[None, :]
    m[:3, 3] = (p0 + p1) / 2.0
    return m


# ── GPU renderer ─────────────────────────────────────────────────────────────
_GL_TRIANGLES, _GL_POINTS = 4, 0
_GL_FLOAT, _GL_UNSIGNED_INT = 0x1406, 0x1405
_GL_DEPTH_TEST, _GL_BLEND, _GL_CULL_FACE = 0x0B71, 0x0BE2, 0x0B44
_GL_LEQUAL, _GL_ONE, _GL_ONE_MINUS_SRC_ALPHA = 0x0203, 1, 0x0303
_GL_FRONT, _GL_BACK = 0x0404, 0x0405
_GL_COLOR_BIT, _GL_DEPTH_BIT = 0x4000, 0x0100
_GL_TEXTURE_2D, _GL_TEXTURE0 = 0x0DE1, 0x84C0
_GL_PROGRAM_POINT_SIZE = 0x8642

_OBJ_VS = """#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNrm;
layout(location=2) in vec2 aUv;
uniform mat4 uModel;
uniform mat4 uViewProj;
out vec3 vN; out vec3 vW; out vec2 vUv;
void main(){
    vec4 w = uModel * vec4(aPos, 1.0);
    vW = w.xyz;
    vN = transpose(inverse(mat3(uModel))) * aNrm;
    vUv = aUv;
    gl_Position = uViewProj * w;
}
"""

_OBJ_FS = """#version 330 core
in vec3 vN; in vec3 vW; in vec2 vUv;
uniform vec3 uColor;
uniform float uOpacity;
uniform float uGlow;
uniform int uStyle;
uniform vec3 uCam;
uniform float uTime;
uniform vec2 uGrid;
out vec4 fragColor;
float gridLine(vec2 uv, vec2 n){
    vec2 g = uv * n;
    vec2 d = abs(fract(g - 0.5) - 0.5) / max(fwidth(g), vec2(1e-4));
    return 1.0 - clamp(min(d.x, d.y), 0.0, 1.0);
}
void main(){
    vec3 N = normalize(vN);
    if(!gl_FrontFacing) N = -N;
    vec3 V = normalize(uCam - vW);
    float ndv = clamp(dot(N, V), 0.0, 1.0);
    float fres = pow(1.0 - ndv, 2.4);
    vec3 L1 = normalize(vec3(-0.5, 0.9, 0.7));
    vec3 L2 = normalize(vec3(0.8, 0.1, -0.6));
    float d1 = max(dot(N, L1), 0.0);
    float d2 = max(dot(N, L2), 0.0);
    vec3 H = normalize(L1 + V);
    float spec = pow(max(dot(N, H), 0.0), 70.0);
    float hemi = 0.5 + 0.5 * N.y;
    float grid = gridLine(vUv, uGrid);
    float s = fract(vW.y * 0.22 - uTime * 0.16);
    float band = smoothstep(0.0, 0.012, s) * smoothstep(0.05, 0.02, s);
    vec3 col; float alpha;
    if(uStyle == 0){
        col = uColor * (0.10 + 0.30 * hemi + 0.85 * d1 + 0.30 * d2) + vec3(spec * 0.6);
        col += uColor * fres * 0.9;
        col = mix(col, uColor * 1.25, grid * 0.20);
        col += uColor * band * 0.35;
        col += uColor * uGlow * 0.6;
        alpha = uOpacity;
    } else if(uStyle == 1){
        col = uColor * (0.35 + 0.5 * d1) + uColor * fres * 1.2 + uColor * grid * 0.9
              + vec3(spec * 0.5) + uColor * band * 0.8;
        alpha = uOpacity * clamp(0.16 + 0.60 * fres + 0.55 * grid + 0.35 * band + 0.15 * d1, 0.0, 1.0);
    } else if(uStyle == 2){
        col = uColor * (0.55 + 0.9 * grid) + uColor * fres * 0.6;
        alpha = uOpacity * clamp(grid * 0.95 + fres * 0.55 + 0.04, 0.0, 1.0);
    } else {
        float core = pow(ndv, 1.4);
        col = mix(uColor, vec3(1.0), core * 0.30) * (1.15 + uGlow) + uColor * fres * 0.8;
        col += uColor * grid * 0.12;
        alpha = uOpacity;
    }
    col *= 0.96 + 0.04 * sin(gl_FragCoord.y * 1.7);
    col = vec3(1.0) - exp(-col * 1.25);
    fragColor = vec4(col * alpha, alpha);
}
"""

_FLOOR_FS = """#version 330 core
in vec3 vN; in vec3 vW; in vec2 vUv;
uniform vec3 uColor;
uniform float uTime;
uniform float uExtent;
uniform vec2 uCentre;
out vec4 fragColor;
float lines(vec2 g){
    vec2 d = abs(fract(g - 0.5) - 0.5) / max(fwidth(g), vec2(1e-4));
    return 1.0 - clamp(min(d.x, d.y), 0.0, 1.0);
}
void main(){
    vec2 p = vW.xz - uCentre;
    float r = length(p) / uExtent;
    float fade = smoothstep(1.0, 0.12, r);
    float minor = lines(p / (uExtent * 0.12));
    float major = lines(p / (uExtent * 0.36));
    float rr = r * 3.0;
    float ring = 1.0 - clamp(abs(fract(rr - 0.5) - 0.5) / max(fwidth(rr), 1e-4), 0.0, 1.0);
    float ang = atan(p.y, p.x) / 6.2831853;
    float sweep = fract(ang - uTime * 0.12);
    float wedge = pow(sweep, 7.0);
    float a = fade * (0.04 + 0.16 * minor + 0.30 * major + 0.26 * ring + 0.20 * wedge);
    vec3 col = uColor * (0.9 + 0.5 * major + 0.9 * wedge);
    fragColor = vec4(col * a, a);
}
"""

_PART_VS = """#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec4 aCol;
layout(location=2) in float aSize;
uniform mat4 uViewProj;
uniform float uPx;
out vec4 vCol;
void main(){
    vec4 p = uViewProj * vec4(aPos, 1.0);
    gl_Position = p;
    gl_PointSize = max(1.5, aSize * uPx / max(p.w, 0.01));
    vCol = aCol;
}
"""

_PART_FS = """#version 330 core
in vec4 vCol;
out vec4 fragColor;
void main(){
    float r = length(gl_PointCoord - vec2(0.5)) * 2.0;
    float a = pow(clamp(1.0 - r, 0.0, 1.0), 1.6) * vCol.a;
    fragColor = vec4(vCol.rgb * a, a);
}
"""

_FS_VS = """#version 330 core
out vec2 vUv;
void main(){
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    vUv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

_BLUR_FS = """#version 330 core
in vec2 vUv;
uniform sampler2D uTex;
uniform vec2 uStep;
uniform float uThresh;
uniform int uBright;
out vec4 fragColor;
void main(){
    float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
    vec3 acc = vec3(0.0);
    float sum = 0.0;
    for(int i = -4; i <= 4; i++){
        vec3 c = texture(uTex, vUv + uStep * float(i)).rgb;
        if(uBright == 1){
            float l = max(c.r, max(c.g, c.b));
            c *= smoothstep(uThresh, uThresh + 0.25, l);
        }
        float wi = w[abs(i)];
        acc += c * wi;
        sum += wi;
    }
    fragColor = vec4(acc / sum, 1.0);
}
"""

_COMP_FS = """#version 330 core
in vec2 vUv;
uniform sampler2D uScene;
uniform sampler2D uB1;
uniform sampler2D uB2;
uniform float uGain;
out vec4 fragColor;
void main(){
    vec4 s = texture(uScene, vUv);
    vec3 g = texture(uB1, vUv).rgb * 0.7 + texture(uB2, vUv).rgb * 1.0;
    vec3 rgb = s.rgb + g * uGain;
    float a = max(s.a, max(rgb.r, max(rgb.g, rgb.b)));
    fragColor = vec4(rgb, min(a, 1.0));
}
"""

FOV_Y = math.radians(32.0)
BASE_PITCH = 0.40
MAX_PIXELS = 1_700_000


class HoloRenderer:
    """Owns the offscreen OpenGL context and renders scenes into QImages."""

    def __init__(self):
        from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
        from PyQt6.QtOpenGL import (QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile)
        fmt = QSurfaceFormat()
        fmt.setVersion(4, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        self.ctx = QOpenGLContext()
        self.ctx.setFormat(fmt)
        if not self.ctx.create():
            raise RuntimeError("OpenGL 4.1 core context unavailable")
        self.surface = QOffscreenSurface()
        self.surface.setFormat(self.ctx.format())
        self.surface.create()
        if not self.surface.isValid():
            raise RuntimeError("offscreen surface invalid")
        if not self.ctx.makeCurrent(self.surface):
            raise RuntimeError("makeCurrent failed")
        self.f = QOpenGLVersionFunctionsFactory.get(QOpenGLVersionProfile(self.ctx.format()), self.ctx)
        self.f.initializeOpenGLFunctions()
        self.gpu = str(self.f.glGetString(0x1F01))
        self._locs: dict = {}
        self._meshes: dict = {}
        self._targets = None
        self._particle = None
        self._empty_vao = None
        self.obj = self._program(_OBJ_VS, _OBJ_FS)
        self.floor = self._program(_OBJ_VS, _FLOOR_FS)
        self.part = self._program(_PART_VS, _PART_FS)
        self.blur = self._program(_FS_VS, _BLUR_FS)
        self.comp = self._program(_FS_VS, _COMP_FS)
        self.last_ms = 0.0
        self.ctx.doneCurrent()

    # helpers ---------------------------------------------------------------
    def _program(self, vs, fs):
        from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram
        prog = QOpenGLShaderProgram()
        ok = (prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vs)
              and prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fs)
              and prog.link())
        if not ok:
            raise RuntimeError("shader error: " + prog.log())
        return prog

    def _loc(self, prog, name):
        key = (id(prog), name)
        loc = self._locs.get(key)
        if loc is None:
            loc = prog.uniformLocation(name)
            self._locs[key] = loc
        return loc

    def _set(self, prog, name, value):
        from PyQt6.QtGui import QMatrix4x4, QVector2D, QVector3D
        loc = self._loc(prog, name)
        if loc < 0:
            return
        if isinstance(value, np.ndarray) and value.shape == (4, 4):
            prog.setUniformValue(loc, QMatrix4x4(*[float(x) for x in value.flatten()]))
        elif isinstance(value, (tuple, list)) and len(value) == 3:
            prog.setUniformValue(loc, QVector3D(*[float(x) for x in value]))
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            prog.setUniformValue(loc, QVector2D(*[float(x) for x in value]))
        elif isinstance(value, (int, np.integer)) and not isinstance(value, bool):
            prog.setUniformValue(loc, int(value))
        else:
            prog.setUniformValue(loc, float(value))

    def _mesh_vao(self, name):
        entry = self._meshes.get(name)
        if entry is not None:
            return entry
        from PyQt6.QtOpenGL import QOpenGLBuffer, QOpenGLVertexArrayObject
        verts, tri = mesh(name)
        vao = QOpenGLVertexArrayObject()
        vao.create()
        vao.bind()
        vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vbo.create()
        vbo.bind()
        vbo.allocate(verts.tobytes(), verts.nbytes)
        ibo = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
        ibo.create()
        ibo.bind()
        flat = tri.astype(np.uint32).ravel()
        ibo.allocate(flat.tobytes(), flat.nbytes)
        for loc, size, offset in ((0, 3, 0), (1, 3, 12), (2, 2, 24)):
            self.obj.enableAttributeArray(loc)
            self.obj.setAttributeBuffer(loc, _GL_FLOAT, offset, size, 32)
        vao.release()
        entry = (vao, int(flat.size), vbo, ibo)
        if len(self._meshes) > 80:       # orbit-ratio meshes are few; this is only a guard
            self._meshes.clear()
        self._meshes[name] = entry
        return entry

    def _draw_mesh(self, name):
        vao, count, _vbo, _ibo = self._mesh_vao(name)
        vao.bind()
        self.f.glDrawElements(_GL_TRIANGLES, count, _GL_UNSIGNED_INT, None)
        vao.release()

    def _ensure_targets(self, w, h):
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        if self._targets and self._targets["size"] == (w, h):
            return self._targets
        f = self.f

        def linear(fbo):
            f.glBindTexture(_GL_TEXTURE_2D, fbo.texture())
            f.glTexParameteri(_GL_TEXTURE_2D, 0x2801, 0x2601)
            f.glTexParameteri(_GL_TEXTURE_2D, 0x2800, 0x2601)
            f.glTexParameteri(_GL_TEXTURE_2D, 0x2802, 0x812F)
            f.glTexParameteri(_GL_TEXTURE_2D, 0x2803, 0x812F)
            return fbo
        mfmt = QOpenGLFramebufferObjectFormat()
        mfmt.setAttachment(QOpenGLFramebufferObject.Attachment.Depth)
        mfmt.setSamples(4)
        hw, hh = max(1, w // 2), max(1, h // 2)
        qw, qh = max(1, w // 4), max(1, h // 4)
        self._targets = {
            "size": (w, h),
            "msaa": QOpenGLFramebufferObject(w, h, mfmt),
            "scene": linear(QOpenGLFramebufferObject(w, h)),
            "h1": linear(QOpenGLFramebufferObject(hw, hh)),
            "h2": linear(QOpenGLFramebufferObject(hw, hh)),
            "q1": linear(QOpenGLFramebufferObject(qw, qh)),
            "q2": linear(QOpenGLFramebufferObject(qw, qh)),
            "out": QOpenGLFramebufferObject(w, h),
        }
        return self._targets

    def _stream_particles(self, data: np.ndarray):
        from PyQt6.QtOpenGL import QOpenGLBuffer, QOpenGLVertexArrayObject
        if self._particle is None:
            vao = QOpenGLVertexArrayObject()
            vao.create()
            vao.bind()
            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            vbo.create()
            vbo.bind()
            vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.StreamDraw)
            vbo.allocate(32 * 4)
            for loc, size, offset in ((0, 3, 0), (1, 4, 12), (2, 1, 28)):
                self.part.enableAttributeArray(loc)
                self.part.setAttributeBuffer(loc, _GL_FLOAT, offset, size, 32)
            vao.release()
            self._particle = (vao, vbo)
        vao, vbo = self._particle
        vbo.bind()
        vbo.allocate(data.tobytes(), data.nbytes)
        vao.bind()
        self.f.glDrawArrays(_GL_POINTS, 0, len(data))
        vao.release()

    def _fullscreen(self, prog, fbo, w, h):
        from PyQt6.QtOpenGL import QOpenGLVertexArrayObject
        f = self.f
        if self._empty_vao is None:
            self._empty_vao = QOpenGLVertexArrayObject()
            self._empty_vao.create()
        fbo.bind()
        f.glViewport(0, 0, w, h)
        prog.bind()
        self._empty_vao.bind()
        f.glDrawArrays(_GL_TRIANGLES, 0, 3)
        self._empty_vao.release()
        prog.release()

    def _bind_tex(self, unit, fbo):
        self.f.glActiveTexture(_GL_TEXTURE0 + unit)
        self.f.glBindTexture(_GL_TEXTURE_2D, fbo.texture())

    # scene cache -----------------------------------------------------------
    _scene = None
    _scene_sig = ""

    _scenes = None

    def _scene_for(self, items):
        sig = signature(items)
        if self._scenes is None:
            self._scenes = {}
        scene = self._scenes.get(sig)
        if scene is None:
            if len(self._scenes) >= 8:
                self._scenes.pop(next(iter(self._scenes)))
            scene = self._scenes[sig] = compile_scene(items)
        return scene

    def _obj_uniforms(self, o, appear):
        p = self.obj
        self._set(p, "uColor", o["color"])
        self._set(p, "uOpacity", o["opacity"] * min(1.0, appear * 1.6))
        self._set(p, "uGlow", o["glow"])
        self._set(p, "uStyle", int(o["style"]))
        self._set(p, "uGrid", GRID_LINES.get(o["shape"], (12.0, 12.0)))

    def _draw_object(self, o, p, sp, mu, appear):
        sc = o["size"] * mu * max(appear, 1e-3)
        s3 = (sc * o["stretch"][0], sc * o["stretch"][1], sc * o["stretch"][2])
        self._set(self.obj, "uModel", _model(p, sp, s3))
        self._obj_uniforms(o, appear)
        self._draw_mesh(o["shape"])

    # public entry ----------------------------------------------------------
    def render(self, items, w, h, t, view=(0.0, 0.0), reveal=None, zoom=1.0):
        """Render model3d items -> (QImage premultiplied ARGB, label list).

        ``view`` is the user's drag (yaw, pitch) in radians; ``reveal`` maps an
        item index to its 0..1 appearance progress. Labels are returned in 0..1
        image fractions so the caller can paint crisp QPainter text on top.
        """
        w, h = max(64, int(w)), max(64, int(h))
        if w * h > MAX_PIXELS:
            k = math.sqrt(MAX_PIXELS / float(w * h))
            w, h = max(64, int(w * k)), max(64, int(h * k))
        scene = self._scene_for(items)
        if not scene.objs:
            return None, []
        if not self.ctx.makeCurrent(self.surface):
            raise RuntimeError("makeCurrent failed")
        try:
            return self._render(scene, w, h, float(t), view, reveal or {}, float(zoom))
        finally:
            self.ctx.doneCurrent()

    def _render(self, scene, w, h, t, view, reveal, zoom):
        import time as _time
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject
        t0 = _time.perf_counter()
        f = self.f
        tg = self._ensure_targets(w, h)

        yaw = float(view[0]) + (0.30 * math.sin(t * 0.22) if scene.sway else 0.0)
        pitch = _clamp(BASE_PITCH + float(view[1]), -1.3, 1.3)
        aspect = w / float(h)
        ctr = scene.center
        dirv = np.array([math.cos(pitch) * math.sin(yaw), math.sin(pitch),
                         math.cos(pitch) * math.cos(yaw)])
        s_ax = np.cross(np.array([0.0, 1.0, 0.0]), dirv)
        s_ax /= max(float(np.linalg.norm(s_ax)), 1e-9)
        u_ax = np.cross(dirv, s_ax)
        rel = scene.sp - ctr
        tan_y = math.tan(FOV_Y / 2.0)
        tan_x = tan_y * aspect
        need = np.maximum(rel @ dirv + (np.abs(rel @ s_ax) + scene.sr) / tan_x,
                          rel @ dirv + (np.abs(rel @ u_ax) + scene.sr) / tan_y)
        dist = max(float(need.max()) * 1.12, scene.radius * 1.15) / _clamp(zoom, 0.3, 4.0)
        eye = ctr + dist * dirv
        vp = _perspective(FOV_Y, aspect, dist * 0.04, dist * 8.0) @ _look_at(eye, ctr)
        pos, spin, mul = _positions(scene, t)
        appear = [ease_out_back(reveal.get(o["item"], 1.0)) if reveal else 1.0
                  for o in scene.objs]

        msaa = tg["msaa"]
        msaa.bind()
        f.glViewport(0, 0, w, h)
        f.glClearColor(0.0, 0.0, 0.0, 0.0)
        f.glClear(_GL_COLOR_BIT | _GL_DEPTH_BIT)
        f.glEnable(_GL_DEPTH_TEST)
        f.glDepthFunc(_GL_LEQUAL)
        f.glEnable(_GL_BLEND)
        f.glBlendFunc(_GL_ONE, _GL_ONE_MINUS_SRC_ALPHA)
        f.glDisable(_GL_CULL_FACE)
        f.glEnable(_GL_PROGRAM_POINT_SIZE)

        main = next((o for o in scene.objs if o["main"]), scene.objs[0])
        accent = main["color"]

        # 1) holographic floor (no depth writes)
        if scene.floor:
            f.glDepthMask(False)
            fl = self.floor
            fl.bind()
            ext = min(scene.extent * 1.25, scene.radius * 0.95)
            self._set(fl, "uViewProj", vp)
            self._set(fl, "uModel", _model((ctr[0], scene.floor_y, ctr[2]), 0.0, (ext, 1.0, ext)))
            self._set(fl, "uColor", accent)
            self._set(fl, "uTime", t)
            self._set(fl, "uExtent", ext)
            self._set(fl, "uCentre", (float(ctr[0]), float(ctr[2])))
            self._draw_mesh("plane")
            fl.release()

        ob = self.obj
        ob.bind()
        self._set(ob, "uViewProj", vp)
        self._set(ob, "uCam", tuple(eye))
        self._set(ob, "uTime", t)

        # 2) orbit paths
        f.glDepthMask(False)
        for i, o in enumerate(scene.objs):
            if o["motion"] != "orbit" or not o["path"] or o["orbit_r"] <= 0.05:
                continue
            parent = np.zeros(3) if o["parent"] is None else pos[o["parent"]]
            rot = _rot_y(o["node"]) @ _rot_x(o["tilt"])
            centre = parent + rot @ np.array([0.0, o["level"], 0.0])
            r = o["orbit_r"]
            m = np.eye(4)
            m[:3, :3] = rot * r
            m[:3, 3] = centre
            self._set(ob, "uModel", m)
            self._set(ob, "uColor", o["color"])
            self._set(ob, "uOpacity", 0.55 * min(1.0, appear[i] * 1.6))
            self._set(ob, "uGlow", 0.0)
            self._set(ob, "uStyle", 3)
            self._set(ob, "uGrid", (1.0, 1.0))
            self._draw_mesh(orbit_mesh_name(r, 0.022 * max(1.0, dist / 8.0)))

        # 3) opaque bodies, then transparent ones back-to-front
        opaque, glassy = [], []
        for i, o in enumerate(scene.objs):
            if appear[i] <= 0.001:
                continue
            (opaque if o["style"] in (0, 3) and o["opacity"] >= 0.99 else glassy).append(i)
        f.glDepthMask(True)
        for i in opaque:
            self._draw_object(scene.objs[i], pos[i], spin[i], mul[i], appear[i])
        f.glDepthMask(False)
        glassy.sort(key=lambda i: -float(np.linalg.norm(pos[i] - eye)))
        for i in glassy:
            self._draw_object(scene.objs[i], pos[i], spin[i], mul[i], appear[i])

        # 4) links: glowing bars, arrow heads and flowing particles
        lookup: dict[str, int] = {}
        for i, o in enumerate(scene.objs):
            lookup.setdefault(o["id"].split("#")[0].lower(), i)
            lookup.setdefault(o["id"].lower(), i)
            if o["label"]:
                lookup.setdefault(o["label"].strip().lower(), i)
        particles = []
        for link in scene.links:
            a = lookup.get(str(link.get("from", "")).strip().lower())
            b = lookup.get(str(link.get("to", "")).strip().lower())
            if a is None or b is None or a == b:
                continue
            ap = min(appear[a], appear[b])
            if ap <= 0.05:
                continue
            p0, p1 = np.array(pos[a], float), np.array(pos[b], float)
            d = p1 - p0
            length = float(np.linalg.norm(d))
            if length < 1e-3:
                continue
            u = d / length
            ra = scene.objs[a]["size"] * max(scene.objs[a]["stretch"])
            rb = scene.objs[b]["size"] * max(scene.objs[b]["stretch"])
            p0s, p1s = p0 + u * ra * 0.9, p1 - u * rb * 0.9
            if float(np.dot(p1s - p0s, u)) <= 0.05:
                continue
            col = rgb(link.get("color") or "white")
            self._set(ob, "uColor", col)
            self._set(ob, "uOpacity", 0.8 * min(1.0, ap * 1.5))
            self._set(ob, "uGlow", 0.3)
            self._set(ob, "uStyle", 3)
            self._set(ob, "uGrid", (1.0, 1.0))
            self._set(ob, "uModel", segment_model(p0s, p1s, 0.010 * max(1.0, dist / 9.0)))
            self._draw_mesh("cylinder")
            if link.get("arrow", True):
                head = 0.075 * max(1.0, dist / 9.0)
                m = np.eye(4)
                m[:3, :3] = _align_y(u) * head
                m[:3, 3] = p1s - u * head
                self._set(ob, "uModel", m)
                self._draw_mesh("cone")
            if link.get("flow", True):
                speed = _clamp(_num(link.get("speed"), 1.0), 0.1, 5.0)
                for k in range(7):
                    s = (k / 7.0 + t * 0.32 * speed) % 1.0
                    q = p0s + (p1s - p0s) * s
                    fade = math.sin(math.pi * s)
                    particles.append([*q, *col, 0.95 * fade * ap, 0.10 * max(1.0, dist / 9.0)])
        ob.release()
        if particles:
            f.glBlendFunc(_GL_ONE, _GL_ONE)
            pr = self.part
            pr.bind()
            self._set(pr, "uViewProj", vp)
            self._set(pr, "uPx", h / (2.0 * math.tan(FOV_Y / 2.0)))
            self._stream_particles(np.asarray(particles, np.float32))
            pr.release()
            f.glBlendFunc(_GL_ONE, _GL_ONE_MINUS_SRC_ALPHA)
        f.glDepthMask(True)

        # 5) resolve MSAA, bloom, composite
        QOpenGLFramebufferObject.blitFramebuffer(tg["scene"], msaa)
        f.glDisable(_GL_DEPTH_TEST)
        f.glDisable(_GL_BLEND)
        bl = self.blur
        hw, hh = max(1, w // 2), max(1, h // 2)
        qw, qh = max(1, w // 4), max(1, h // 4)
        for src, dst, sw, sh, step, bright in (
                ("scene", "h1", hw, hh, (1.0 / hw, 0.0), 1),
                ("h1", "h2", hw, hh, (0.0, 1.0 / hh), 0),
                ("h2", "q1", qw, qh, (1.0 / qw, 0.0), 0),
                ("q1", "q2", qw, qh, (0.0, 1.0 / qh), 0)):
            bl.bind()
            self._bind_tex(0, tg[src])
            self._set(bl, "uTex", 0)
            self._set(bl, "uStep", step)
            self._set(bl, "uThresh", 0.70)
            self._set(bl, "uBright", bright)
            self._fullscreen(bl, tg[dst], sw, sh)
        cp = self.comp
        cp.bind()
        self._bind_tex(0, tg["scene"])
        self._bind_tex(1, tg["h2"])
        self._bind_tex(2, tg["q2"])
        self._set(cp, "uScene", 0)
        self._set(cp, "uB1", 1)
        self._set(cp, "uB2", 2)
        self._set(cp, "uGain", 0.75)
        self._fullscreen(cp, tg["out"], w, h)
        image = tg["out"].toImage().copy()
        QOpenGLFramebufferObject.bindDefault()

        # 6) label anchors in 0..1 image fractions (caller paints the text)
        labels = []
        if scene.labels_on:
            for i, o in enumerate(scene.objs):
                if not o["label"] or appear[i] < 0.6:
                    continue
                top = np.array([pos[i][0], pos[i][1] + o["size"] * max(o["stretch"][1], 1.0) * 1.18 + 0.12,
                                pos[i][2], 1.0])
                clip = vp @ top
                if clip[3] <= 1e-6:
                    continue
                labels.append({"text": o["label"], "x": float(clip[0] / clip[3] * 0.5 + 0.5),
                               "y": float(1.0 - (clip[1] / clip[3] * 0.5 + 0.5)),
                               "color": o["color"]})
        self.last_ms = (_time.perf_counter() - t0) * 1000.0
        return image, labels


# ── singleton with graceful failure ──────────────────────────────────────────
_RENDERER = None
_RENDERER_FAILED = False


def get_renderer():
    """Shared HoloRenderer, or None when OpenGL is unavailable (software fallback)."""
    global _RENDERER, _RENDERER_FAILED
    import os
    if _RENDERER is not None:
        return _RENDERER
    if _RENDERER_FAILED or os.environ.get("JARVIS_NO_GL") == "1":
        return None
    try:
        _RENDERER = HoloRenderer()
        _LOG.info("holo3d: GPU renderer ready on %s", _RENDERER.gpu)
    except Exception:
        _RENDERER_FAILED = True
        _LOG.exception("holo3d: OpenGL unavailable, using software 3D")
        return None
    return _RENDERER
