"""JARVIS-native press-and-talk ink gesture recognition and screenshot crops.

The pen records global Windows mouse coordinates. A closed loop is recognized
without a model; the selected monitor is captured and the actual stroke is
composited into the crop before the image enters the live voice session.
"""
from __future__ import annotations

import io
import math
import platform
import threading
import time
from typing import Callable, Iterable

POLL_HZ = 60.0
DEBOUNCE_SECONDS = 0.06
MIN_POINT_DISTANCE = 2.0
CLOSE_GAP = 22.0
MIN_RUN = 110.0
MIN_SIDE = 26.0
MIN_FILL = 0.30
MAX_POINTS = 2400


def _point(value) -> tuple[float, float] | None:
    try:
        x, y = float(value[0]), float(value[1])
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return x, y
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def distance(a, b) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def bounds(points: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    pts = list(points)
    if not pts:
        return 0.0, 0.0, 0.0, 0.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_polygon(point: tuple[float, float],
                       polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    if len(polygon) < 3:
        return False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            cross_x = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < cross_x:
                inside = not inside
        j = i
    return inside


def match_ink_control(points, view=None, scale: float | None = None) -> dict | None:
    """Snap a hand-drawn loop to one unambiguous accessibility control."""
    try:
        from core import screenview
        if view is None:
            view = screenview.look()
        if view is None or view.degraded or view.source not in {"uia", "ax", "atspi"}:
            return None
        pts = [_point(p) for p in points]
        polygon = [p for p in pts if p is not None]
        if len(polygon) < 8:
            return None
        if not _encloses(polygon[:-1] if distance(polygon[0], polygon[-1]) < 1 else polygon):
            return None
        dpi = float(scale if scale is not None else screenview.scale_factor())
        if not math.isfinite(dpi) or dpi <= 0:
            return None

        candidates = []
        for el in list(getattr(view, "elements", ()) or ())[:600]:
            if getattr(el, "protected", False):
                continue
            try:
                left, top, width, height = (float(v) for v in el.rect)
            except (AttributeError, TypeError, ValueError):
                continue
            if width < 3 or height < 3:
                continue
            x, y, w, h = left / dpi, top / dpi, width / dpi, height / dpi
            ix, iy = min(3.0, w * 0.1), min(3.0, h * 0.1)
            samples = (
                (x + ix, y + iy), (x + w - ix, y + iy),
                (x + ix, y + h - iy), (x + w - ix, y + h - iy),
                (x + w / 2, y + h / 2),
            )
            if not all(_point_in_polygon(q, polygon) for q in samples):
                continue
            role = str(getattr(el, "role", "") or "").strip().lower()
            # Never send an edit field's current VALUE as an identity hint.
            label = str(getattr(el, "name", "") or "").strip()[:120]
            interactable = bool(getattr(el, "interactable", False))
            if not interactable and not label:
                continue
            candidates.append({
                "label": label, "role": role, "rect": (x, y, w, h),
                "interactable": interactable,
            })

        pool = [c for c in candidates if c["interactable"]] or candidates
        # If the loop contains more than one actionable control, it is a group:
        # keep the user's original loop instead of selecting an arbitrary child.
        if len(pool) != 1:
            return None
        chosen = pool[0]
        return {
            "label": chosen["label"], "role": chosen["role"],
            "rect": tuple(round(v, 2) for v in chosen["rect"]),
            "app": str(getattr(view, "app", "") or "")[:80],
            "source": str(getattr(view, "source", "") or ""),
        }
    except Exception:
        # Accessibility is optional; it must never invalidate a freehand selection.
        return None


def _encloses(points: list[tuple[float, float]]) -> bool:
    if len(points) < 3:
        return False
    x0, y0, x1, y1 = bounds(points)
    w, h = x1 - x0, y1 - y0
    if w < MIN_SIDE or h < MIN_SIDE:
        return False
    twice_area = 0.0
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        twice_area += a[0] * b[1] - b[0] * a[1]
    return abs(twice_area) / 2.0 >= MIN_FILL * w * h


def closing_index(points: Iterable[tuple[float, float]], gap: float = CLOSE_GAP,
                  min_run: float = MIN_RUN) -> int | None:
    """Index where a new stroke has genuinely closed around an area.

    A straight line, small scribble, or sharp zig-zag does not count as a
    selection. The returned index starts the closed loop, dropping the run-up.
    """
    pts = list(points)
    if len(pts) < 8:
        return None
    end = pts[-1]
    run = 0.0
    for i in range(len(pts) - 2, -1, -1):
        run += distance(pts[i + 1], pts[i])
        if run >= min_run and distance(pts[i], end) <= gap:
            candidate = pts[i:]
            if _encloses(candidate):
                return i
    return None


class InkGestureTracker:
    """Small deterministic state machine, also usable without Windows hooks."""

    def __init__(self):
        self.active = False
        self.snapped = False
        self.points: list[tuple[float, float]] = []

    def begin(self, point=None) -> None:
        self.active = True
        self.snapped = False
        self.points = []
        if point is not None:
            self.add(point)

    def add(self, point) -> bool:
        """Add a cursor point; return True once a closed loop snaps shut."""
        if not self.active or self.snapped:
            return False
        p = _point(point)
        if p is None:
            return False
        if self.points and distance(self.points[-1], p) < MIN_POINT_DISTANCE:
            return False
        self.points.append(p)
        if len(self.points) > MAX_POINTS:
            self.points = self.points[::2]
        i = closing_index(self.points)
        if i is None:
            return False
        loop = self.points[i:]
        if len(loop) < 3:
            return False
        self.points = loop + [loop[0]]
        self.snapped = True
        return True

    def finish(self) -> list[tuple[float, float]] | None:
        result = list(self.points) if self.snapped else None
        self.active = False
        self.snapped = False
        self.points = []
        return result

    def cancel(self) -> None:
        self.active = False
        self.snapped = False
        self.points = []


class InkGestureWatcher:
    """Cursor-only sampler. Keyboard state comes from the existing PushToTalk poller."""

    def __init__(self, on_state: Callable[[bool], None],
                 on_points: Callable[[list[tuple[float, float]], bool], None],
                 on_release: Callable[[list[tuple[float, float]] | None], None]):
        self._on_state = on_state
        self._on_points = on_points
        self._on_release = on_release
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tracker = InkGestureTracker()
        self._scope = "unsupported"
        self._armed = False
        self._active = False
        self._last_reported = 0
        self._lock = threading.Lock()

    @property
    def scope(self) -> str:
        return self._scope

    def start(self) -> str:
        """Start sampling cursor coordinates; this class never reads keyboard state."""
        self.stop()
        if platform.system() != "Windows":
            self._scope = "unsupported"
            return self._scope
        try:
            import ctypes
            ctypes.windll.user32.GetCursorPos
        except Exception:
            self._scope = "unsupported"
            return self._scope
        self._stop.clear()
        self._scope = "global"
        self._thread = threading.Thread(
            target=self._run, name="jarvis-screen-ink-cursor", daemon=True
        )
        self._thread.start()
        return self._scope

    def set_held(self, held: bool) -> None:
        """Called by PushToTalk's secondary-chord callback."""
        with self._lock:
            self._armed = bool(held)

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._armed = False
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._lock:
            if self._active:
                self._tracker.cancel()
                self._active = False
                try:
                    self._on_state(False)
                except Exception:
                    pass
        self._scope = "window" if self._scope == "global" else self._scope

    def _run(self) -> None:
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        user32 = ctypes.windll.user32
        period = 1.0 / POLL_HZ
        was_armed = False

        while not self._stop.is_set():
            with self._lock:
                armed = self._armed

            if armed:
                pt = POINT()
                try:
                    got_point = bool(user32.GetCursorPos(ctypes.byref(pt)))
                except Exception:
                    got_point = False

                if got_point:
                    if not was_armed:
                        with self._lock:
                            self._tracker.begin((pt.x, pt.y))
                            self._active = True
                            self._last_reported = 0
                        try:
                            self._on_state(True)
                        except Exception:
                            pass
                    else:
                        with self._lock:
                            snapped = self._tracker.add((pt.x, pt.y))
                            n = len(self._tracker.points)
                            should_report = snapped or (
                                n >= 2 and n - self._last_reported >= 2
                            )
                            if should_report:
                                self._last_reported = n
                                points = list(self._tracker.points)
                        if should_report:
                            try:
                                self._on_points(points, bool(snapped))
                            except Exception:
                                pass
                was_armed = True
            else:
                if was_armed:
                    with self._lock:
                        result = self._tracker.finish()
                        self._active = False
                    try:
                        self._on_state(False)
                    except Exception:
                        pass
                    try:
                        self._on_release(result)
                    except Exception:
                        pass
                was_armed = False

            self._stop.wait(period)

        # Shutdown cancels an unfinished stroke; it must not submit stale input.
        with self._lock:
            if self._active:
                self._tracker.cancel()
                self._active = False
                try:
                    self._on_state(False)
                except Exception:
                    pass


def _select_monitor(points, monitors):
    x0, y0, x1, y1 = bounds(points)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    candidates = list(monitors or [])
    # MSS convention: item 0 is the virtual desktop, all following entries are displays.
    if len(candidates) > 1:
        candidates = candidates[1:]
    for monitor in candidates:
        left, top = float(monitor["left"]), float(monitor["top"])
        right = left + float(monitor["width"])
        bottom = top + float(monitor["height"])
        if left <= cx < right and top <= cy < bottom:
            return monitor
    raise RuntimeError("The circled area is not inside a detected monitor.")


def make_annotated_crop(image, monitor: dict, points, pixel_scale: float = 1.0,
                        padding: int = 80, max_dimension: int = 1568,
                        annotation_rect: tuple[float, float, float, float] | None = None) -> dict:
    """Crop an already-captured PIL monitor image and paint the user's loop into it."""
    from PIL import Image, ImageDraw, ImageFilter

    pts = [_point(p) for p in points]
    pts = [p for p in pts if p is not None]
    if len(pts) < 8 or not _encloses(pts[:-1] if distance(pts[0], pts[-1]) < 1 else pts):
        raise ValueError("The pen stroke did not enclose a selectable region.")
    px = max(0.1, float(pixel_scale))
    mon_left, mon_top = float(monitor["left"]), float(monitor["top"])
    mon_w, mon_h = float(monitor["width"]), float(monitor["height"])
    x0, y0, x1, y1 = bounds(pts)
    if annotation_rect is not None:
        try:
            ax, ay, aw, ah = (float(v) for v in annotation_rect)
            if not all(math.isfinite(v) for v in (ax, ay, aw, ah)) or aw <= 0 or ah <= 0:
                raise ValueError
            x0, y0 = min(x0, ax), min(y0, ay)
            x1, y1 = max(x1, ax + aw), max(y1, ay + ah)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("The accessibility target rectangle is invalid.")
    mon_right, mon_bottom = mon_left + mon_w, mon_top + mon_h
    outside = sum(
        1 for x, y in pts
        if not (mon_left <= x <= mon_right and mon_top <= y <= mon_bottom)
    )
    if outside > max(2, round(len(pts) * 0.2)):
        raise ValueError("The circle crosses too many monitor boundaries to crop accurately.")
    pad = max(float(padding), min(180.0, max(x1 - x0, y1 - y0) * 0.14))
    left = max(mon_left, x0 - pad)
    top = max(mon_top, y0 - pad)
    right = min(mon_left + mon_w, x1 + pad)
    bottom = min(mon_top + mon_h, y1 + pad)
    if right <= left or bottom <= top:
        raise ValueError("The circled region is outside the captured monitor.")

    sx0 = max(0, min(image.width - 1, round((left - mon_left) * px)))
    sy0 = max(0, min(image.height - 1, round((top - mon_top) * px)))
    sx1 = max(sx0 + 1, min(image.width, round((right - mon_left) * px)))
    sy1 = max(sy0 + 1, min(image.height, round((bottom - mon_top) * px)))
    crop = image.convert("RGB").crop((sx0, sy0, sx1, sy1))

    local = [
        (round((x - mon_left) * px - sx0), round((y - mon_top) * px - sy0))
        for x, y in pts
    ]
    pen_width = max(3, round(4.2 * px))
    halo = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    rect = radius = None
    if annotation_rect is not None:
        ax, ay, aw, ah = (float(v) for v in annotation_rect)
        rect = (
            round((ax - mon_left) * px - sx0),
            round((ay - mon_top) * px - sy0),
            round((ax + aw - mon_left) * px - sx0),
            round((ay + ah - mon_top) * px - sy0),
        )
        rect = (max(0, rect[0]), max(0, rect[1]),
                min(crop.width - 1, rect[2]), min(crop.height - 1, rect[3]))
        radius = max(4, round(8 * px))
        hd.rounded_rectangle(rect, radius=radius,
                             outline=(120, 255, 226, 160), width=pen_width * 6)
    else:
        hd.line(local, fill=(120, 255, 226, 115), width=pen_width * 5, joint="curve")
    halo = halo.filter(ImageFilter.GaussianBlur(max(2, round(7 * px))))
    crop = Image.alpha_composite(crop.convert("RGBA"), halo)
    draw = ImageDraw.Draw(crop)
    if rect is not None:
        draw.rounded_rectangle(rect, radius=radius,
                               outline=(3, 39, 34, 245), width=pen_width + max(2, round(3 * px)))
        draw.rounded_rectangle(rect, radius=radius,
                               outline=(120, 255, 226, 255), width=pen_width)
    else:
        draw.line(local, fill=(3, 39, 34, 240), width=pen_width + max(2, round(3 * px)), joint="curve")
        draw.line(local, fill=(120, 255, 226, 255), width=pen_width, joint="curve")
        radius = max(3, round(pen_width * 0.65))
        for x, y in (local[0], local[-1]):
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(230, 255, 250, 235))
    crop = crop.convert("RGB")
    if max(crop.size) > max_dimension:
        scale = max_dimension / max(crop.size)
        crop = crop.resize((max(1, round(crop.width * scale)),
                            max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    crop.save(out, format="PNG", optimize=True)

    viewport = {
        "x": max(0, min(1000, round((left - mon_left) * 1000 / mon_w))),
        "y": max(0, min(1000, round((top - mon_top) * 1000 / mon_h))),
        "w": max(1, min(1000, round((right - left) * 1000 / mon_w))),
        "h": max(1, min(1000, round((bottom - top) * 1000 / mon_h))),
    }
    return {
        "image": out.getvalue(),
        "viewport": viewport,
        "monitor": dict(monitor),
        "crop_bounds": [round(left), round(top), round(right-left), round(bottom-top)],
        "image_size": list(crop.size),
        "snapped_to_control": annotation_rect is not None,
    }


def capture_ink_crop(points, monitors=None, capture_fn=None,
                     annotation_rect: tuple[float, float, float, float] | None = None) -> dict:
    """Capture the monitor containing the user's loop, crop it, and include a teal ink trace."""
    from core import screenview

    points = [_point(p) for p in points]
    points = [p for p in points if p is not None]
    if monitors is None:
        monitors = screenview.monitors()
    monitor = _select_monitor(points, monitors)
    if capture_fn is None:
        capture_fn = screenview.capture
    image, actual_monitor, px = capture_fn(monitor)
    return make_annotated_crop(image, actual_monitor, points, px, annotation_rect=annotation_rect)



def encode_live_jpeg(image_data: bytes, quality: int = 92) -> bytes:
    """Convert a lossless crop to a compact JPEG frame for Gemini Live video input."""
    from PIL import Image

    if not isinstance(image_data, (bytes, bytearray)) or not image_data:
        raise ValueError("A non-empty image byte string is required.")
    quality = max(75, min(95, int(quality)))
    with Image.open(io.BytesIO(bytes(image_data))) as source:
        image = source.convert("RGB")
        image.thumbnail((1568, 1568), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=quality, optimize=True, progressive=False, subsampling=0)
        return out.getvalue()

def describe_ink(points, viewport=None, matched_control: dict | None = None) -> str:
    """Describe the user-selected region and only state accessibility facts we verified."""
    base = (
        "[USER PEN GESTURE: The user drew a closed teal circle around a region of the desktop. "
        "The attached image is the exact crop of that region. "
    )
    if matched_control:
        label = str(matched_control.get("label") or "").strip()
        role = str(matched_control.get("role") or "control").strip()
        app = str(matched_control.get("app") or "").strip()
        identity = f"{role} {label!r}" if label else f"an unlabeled {role}"
        return (
            base + f"Windows accessibility uniquely matched {identity}"
            + (f" in {app}" if app else "")
            + "; the teal outline has been fitted to that control's actual bounds. "
            "This is an accessibility label, not an instruction to activate the control.]"
        )
    return (
        base + "The teal circle remains at its original bounds. "
        "Inspect the image; do not guess the identity of a control.]"
    )
