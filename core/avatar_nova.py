"""
NovaAvatar - the original holographic face of Jarvis.

A woman made of light: scan-line skin, hair as flowing ribbons of light, a
forehead circlet with a pulsing gem, rotating halo rings and a small reactor
core on her chest. Everything is drawn from scratch with QPainter, using plain
geometry (no scanned mesh, no external model), so the look is ours.

It is a drop-in replacement for core.avatar.HoloAvatar and keeps the same API:

    av = NovaAvatar()
    av.step(dt, amp, speaking=..., muted=..., state=..., v_open=..., ...)
    av.paint(painter, cx, cy, r, primary, accent, bg)
    av.glance(dx, dy, hold)

Unit space while painting: x is -1..1 across the head, y runs from -1 (top of
the head) down to SPAN - 1 (bottom of the bust). `r` is the head half-height.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)


def _rate(dt: float, tau: float) -> float:
    """Frame-rate independent smoothing factor."""
    return 1.0 - math.exp(-max(0.0, dt) / max(1e-4, tau))


def _c(col: QColor, a: float) -> QColor:
    c = QColor(col)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _pen(col, w: float) -> QPen:
    pen = QPen(col) if not isinstance(col, QBrush) else QPen(col, w)
    pen.setWidthF(w)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _arc_to(path: QPainterPath, p2: QPointF, mid: QPointF) -> None:
    """Quadratic curve to p2 that passes exactly through `mid` at t = 0.5."""
    p0 = path.currentPosition()
    ctrl = QPointF(2.0 * mid.x() - 0.5 * (p0.x() + p2.x()),
                   2.0 * mid.y() - 0.5 * (p0.y() + p2.y()))
    path.quadTo(ctrl, p2)


def _face_w(y: float) -> float:
    """Half-width of the face oval at height y (unit space)."""
    if y <= -0.97 or y >= 1.0:
        return 0.0
    k = (y + 0.10) / (0.87 if y < -0.10 else 0.90)
    w = 0.68 * math.sqrt(max(0.0, 1.0 - k * k))
    if y > 0.30:
        f = (y - 0.30) / 0.70
        w *= 1.0 - 0.50 * (f ** 1.5)
    return w


def _face_path() -> QPainterPath:
    path = QPainterPath()
    ys = [-0.97 + i * (1.97 / 64.0) for i in range(65)]
    path.moveTo(0.0, -0.97)
    for y in ys[1:]:
        path.lineTo(_face_w(y), y)
    for y in reversed(ys[:-1]):
        path.lineTo(-_face_w(y), y)
    path.closeSubpath()
    return path


class NovaAvatar:
    # total height of the figure in head-half-heights (top = -1, bottom = SPAN-1)
    SPAN = 2.75
    shaded = True

    def __init__(self) -> None:
        rnd = random.Random(11)
        self.t = 0.0
        self.mouth = 0.0
        self.wide = 0.0
        self.glow = 0.0
        self.think = 0.0
        self.listen = 0.0
        self.eye_open = 1.0
        self.eye_x = 0.0
        self.eye_y = 0.0
        self.brow = 0.0
        self.sway = 0.0
        self.ring_rot = 0.0
        self.speaking = False
        self.muted = False
        self.state = ""
        self._blink_timer = 2.5
        self._blink_phase = -1.0
        self._blink_v = 0.0
        self._ghold = 0.0
        self._gx = 0.0
        self._gy = 0.0
        self._wander_t = 2.0
        self._wx = 0.0
        self._wy = 0.0
        self._face = _face_path()
        n = 24
        self._strands = []
        for i in range(n):
            u = i / (n - 1)
            self._strands.append({
                "u": u,
                "h": 0.99 + 0.08 * u + 0.01 * rnd.random(),
                "x": 0.72 + 0.34 * u + 0.02 * rnd.random(),
                "r1": rnd.random(), "r2": rnd.random(), "ph": rnd.random() * 6.28,
            })
        self._motes = [
            {"x": rnd.uniform(-1.25, 1.25), "y": rnd.uniform(0.0, 3.2),
             "s": rnd.uniform(0.04, 0.12), "ph": rnd.uniform(0, 6.28),
             "z": rnd.uniform(0.008, 0.018)}
            for _ in range(22)
        ]

    # ------------------------------------------------------------ animation
    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        self._gx = _clamp(float(dx), -1.0, 1.0)
        self._gy = _clamp(float(dy), -1.0, 1.0)
        self._ghold = max(0.0, float(hold))

    def step(self, dt: float, amp: float, speaking: bool = False,
             muted: bool = False, state: str = "", v_open=None,
             v_wide: float = 0.0, v_level=None, v_seq=None,
             v_hop: float = 0.02) -> None:
        dt = _clamp(float(dt), 0.0, 0.25)
        self.t += dt
        self.speaking = bool(speaking)
        self.muted = bool(muted)
        self.state = str(state or "").upper()
        amp = _clamp(float(amp or 0.0), 0.0, 1.0)
        thinking = self.state in ("THINKING", "PROCESSING")
        listening = self.state == "LISTENING"

        self.think += ((1.0 if thinking else 0.0) - self.think) * _rate(dt, 0.35)
        self.listen += ((1.0 if listening else 0.0) - self.listen) * _rate(dt, 0.30)

        tg = amp if speaking else (0.5 * amp if listening else 0.0)
        tg = _clamp(tg, 0.0, 1.0)
        self.glow += (tg - self.glow) * _rate(dt, 0.06 if tg > self.glow else 0.25)

        # mouth: follows the viseme schedule if present, else the loudness
        if speaking and not muted:
            tgt = float(v_open) if v_open is not None else amp * 1.15
        else:
            tgt = 0.0
        tgt = _clamp(tgt, 0.0, 1.0)
        self.mouth += (tgt - self.mouth) * _rate(dt, 0.035 if tgt > self.mouth else 0.07)
        wt = _clamp(float(v_wide or 0.0), -1.0, 1.0) if speaking else 0.0
        self.wide += (wt - self.wide) * _rate(dt, 0.06)

        # blink
        self._blink_timer -= dt
        if self._blink_phase < 0.0 and self._blink_timer <= 0.0:
            self._blink_phase = 0.0
        if self._blink_phase >= 0.0:
            self._blink_phase += dt / 0.17
            self._blink_v = math.sin(math.pi * min(1.0, self._blink_phase))
            if self._blink_phase >= 1.0:
                self._blink_phase = -1.0
                self._blink_v = 0.0
                self._blink_timer = random.uniform(2.2, 5.5)
                if random.random() < 0.18:
                    self._blink_timer = 0.12

        # eyes
        tgt_open = 0.12 if muted else (0.86 if thinking else (1.12 if listening else 1.0))
        self.eye_open += (tgt_open - self.eye_open) * _rate(dt, 0.12)
        if self._ghold > 0.0:
            self._ghold -= dt
            ex, ey = self._gx, self._gy
        elif thinking:
            ex = -0.55 + 0.20 * math.sin(self.t * 0.9)
            ey = -0.55
        else:
            self._wander_t -= dt
            if self._wander_t <= 0.0:
                self._wander_t = random.uniform(2.5, 5.0)
                if random.random() < 0.4:
                    self._wx = self._wy = 0.0
                else:
                    self._wx = random.uniform(-0.35, 0.35)
                    self._wy = random.uniform(-0.15, 0.15)
            ex, ey = self._wx, self._wy
        k = _rate(dt, 0.09)
        self.eye_x += (ex - self.eye_x) * k
        self.eye_y += (ey - self.eye_y) * k

        bt = 0.02 + 0.035 * self.listen - 0.012 * self.think + 0.02 * self.glow
        self.brow += (bt - self.brow) * _rate(dt, 0.15)

        self.sway = (1.7 * math.sin(self.t * 0.45) + 3.2 * self.eye_x
                     + (1.4 * math.sin(self.t * 3.1) * self.glow if speaking else 0.0))
        self.ring_rot = (self.ring_rot + dt * (6.0 + 34.0 * self.think + 12.0 * self.glow)) % 360.0

    # ----------------------------------------------------------- rendering
    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              primary: QColor, accent: QColor, bg: QColor | None = None) -> None:
        if bg is None:
            bg = QColor(0, 0, 0)
        k = 0.55 if self.muted else 1.0
        u = max(0.9, r / 170.0)
        amp = self.glow
        p.save()
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # aura, in screen space
            ac = QPointF(cx, cy + r * 0.2)
            ar = r * 2.0
            g = QRadialGradient(ac, ar)
            g.setColorAt(0.0, _c(primary, (0.10 + 0.24 * amp) * k))
            g.setColorAt(0.55, _c(primary, 0.04 * k))
            g.setColorAt(1.0, _c(primary, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(ac, ar, ar)

            p.translate(cx, cy)
            p.scale(r, r)
            # shrink a touch around the middle of the figure so hair and halo
            # stay inside the band the HUD reserves for the avatar
            p.translate(0.0, 0.375)
            p.scale(0.92, 0.92)
            p.translate(0.0, -0.375)
            p.setBrush(Qt.BrushStyle.NoBrush)
            self._halo(p, primary, accent, u, k)
            self._motes_paint(p, accent, k)

            p.save()
            try:
                p.translate(0.0, 0.012 * math.sin(self.t * 0.9))
                p.rotate(self.sway)
                self._hair(p, primary, accent, u, k)
                self._bust(p, primary, accent, u, k)
                self._face_paint(p, primary, accent, bg, u, k)
            finally:
                p.restore()
        finally:
            p.restore()

    # -- halo rings behind her
    def _halo(self, p, primary, accent, u, k):
        cy0 = -0.05
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(primary, 0.10 * k), u))
        p.drawEllipse(QPointF(0.0, cy0), 1.06, 1.06)

        p.save()
        p.translate(0.0, cy0)
        p.rotate(self.ring_rot)
        ticks = QPainterPath()
        for i in range(72):
            a = math.radians(i * 5.0)
            r0 = 1.12
            r1 = 1.16 if i % 6 else 1.21
            ticks.moveTo(r0 * math.cos(a), r0 * math.sin(a))
            ticks.lineTo(r1 * math.cos(a), r1 * math.sin(a))
        p.setPen(_pen(_c(primary, 0.32 * k), u))
        p.drawPath(ticks)
        p.restore()

        p.save()
        p.translate(0.0, cy0)
        p.rotate(-self.ring_rot * 1.4)
        p.setPen(_pen(_c(accent, (0.40 + 0.3 * self.glow) * k), 1.7 * u))
        rect = QRectF(-1.27, -1.27, 2.54, 2.54)
        for j in range(3):
            p.drawArc(rect, int((j * 120 + 10) * 16), int(55 * 16))
        if self.think > 0.05:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(accent, 0.9 * self.think * k)))
            for j in range(2):
                a = math.radians(j * 180.0 + self.t * 140.0)
                p.drawEllipse(QPointF(1.27 * math.cos(a), 1.27 * math.sin(a)), 0.022, 0.022)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)

    # -- drifting light motes
    def _motes_paint(self, p, accent, k):
        p.setPen(Qt.PenStyle.NoPen)
        for m in self._motes:
            y = ((m["y"] - self.t * m["s"]) % 3.2) - 1.3
            tw = 0.5 + 0.5 * math.sin(self.t * 1.7 + m["ph"])
            p.setBrush(QBrush(_c(accent, (0.10 + 0.45 * tw) * k)))
            p.drawEllipse(QPointF(m["x"] + 0.03 * math.sin(self.t * 0.6 + m["ph"]), y), m["z"], m["z"])
        p.setBrush(Qt.BrushStyle.NoBrush)

    # -- hair: ribbons of light
    def _hair(self, p, primary, accent, u, k):
        t = self.t
        amp = self.glow
        inner = QPainterPath()
        outer = QPainterPath()
        sparks = []
        for e in (-1.0, 1.0):
            for i, s in enumerate(self._strands):
                uu = s["u"]
                sw = math.sin(t * 0.8 + s["ph"] + i * 0.35)
                sw2 = math.sin(t * 1.3 + s["ph"] * 1.7)
                x = s["x"]
                y_end = 1.30 + 0.42 * uu + 0.05 * s["r1"]
                path = QPainterPath()
                path.moveTo(e * 0.03, -s["h"])
                path.cubicTo(
                    QPointF(e * x * 1.05, -s["h"] + 0.02),
                    QPointF(e * (x + 0.10 + 0.10 * s["r1"] + 0.02 * sw * (1 + amp * 2)), 0.15 + 0.5 * uu),
                    QPointF(e * (x + 0.02 + 0.30 * s["r2"] + 0.04 * sw2 * (1 + amp * 2)),
                            min(1.72, y_end)),
                )
                (inner if uu < 0.55 else outer).addPath(path)
                if i % 5 == 2:
                    sparks.append((path, (t * 0.18 + s["ph"]) % 1.0))
        g1 = QLinearGradient(0.0, -1.25, 0.0, 1.75)
        g1.setColorAt(0.0, _c(primary, 0.55 * k))
        g1.setColorAt(0.55, _c(primary, 0.28 * k))
        g1.setColorAt(1.0, _c(primary, 0.03 * k))
        g2 = QLinearGradient(0.0, -1.25, 0.0, 1.75)
        g2.setColorAt(0.0, _c(accent, 0.38 * k))
        g2.setColorAt(0.6, _c(accent, 0.16 * k))
        g2.setColorAt(1.0, _c(accent, 0.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(QBrush(g2), 0.9 * u))
        p.drawPath(outer)
        p.setPen(_pen(QBrush(g1), 1.0 * u))
        p.drawPath(inner)
        p.setPen(Qt.PenStyle.NoPen)
        for path, ph in sparks:
            pt = path.pointAtPercent(ph)
            p.setBrush(QBrush(_c(accent, 0.85 * k * math.sin(math.pi * ph))))
            p.drawEllipse(pt, 0.014, 0.014)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # -- neck, shoulders and the chest reactor
    def _bust(self, p, primary, accent, u, k):
        t = self.t
        line = _pen(_c(primary, 0.55 * k), 1.3 * u)
        faint = _pen(_c(primary, 0.16 * k), u)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for e in (-1.0, 1.0):
            pa = QPainterPath()
            pa.moveTo(e * 0.21, 0.80)
            pa.lineTo(e * 0.20, 1.20)
            _arc_to(pa, QPointF(e * 0.85, 1.50), QPointF(e * 0.46, 1.40))
            _arc_to(pa, QPointF(e * 1.25, 1.75), QPointF(e * 1.10, 1.58))
            p.setPen(line)
            p.drawPath(pa)
            pb = QPainterPath()
            pb.moveTo(e * 0.62, 1.50)
            _arc_to(pb, QPointF(e * 0.04, 1.76), QPointF(e * 0.30, 1.68))
            p.setPen(faint)
            p.drawPath(pb)
        # scan lines across the neck and the chest, fading downward
        for i in range(7):
            y = 0.90 + i * 0.045
            p.setPen(_pen(_c(primary, 0.13 * k), u))
            p.drawLine(QPointF(-0.19, y), QPointF(0.19, y))
        for i in range(5):
            y = 1.55 + i * 0.05
            xw = 0.75 + (y - 1.5) * 1.3
            p.setPen(_pen(_c(primary, (0.16 - i * 0.026) * k), u))
            p.drawLine(QPointF(-xw, y), QPointF(xw, y))
        # reactor pendant
        rc = QPointF(0.0, 1.38)
        pulse = 0.5 + 0.5 * math.sin(t * 2.4)
        gl = QRadialGradient(rc, 0.22)
        gl.setColorAt(0.0, _c(accent, (0.45 + 0.4 * self.glow + 0.15 * pulse) * k))
        gl.setColorAt(1.0, _c(accent, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gl))
        p.drawEllipse(rc, 0.22, 0.22)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(accent, 0.85 * k), 1.5 * u))
        p.drawEllipse(rc, 0.07, 0.07)
        p.setPen(_pen(_c(primary, 0.6 * k), u))
        for i in range(3):
            a = math.radians(i * 120.0 + t * 40.0)
            p.drawLine(QPointF(rc.x() + 0.085 * math.cos(a), rc.y() + 0.085 * math.sin(a)),
                       QPointF(rc.x() + 0.12 * math.cos(a), rc.y() + 0.12 * math.sin(a)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(QColor(255, 255, 255), 0.85 * k)))
        p.drawEllipse(rc, 0.02, 0.02)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # -- the face
    def _face_paint(self, p, primary, accent, bg, u, k):
        t = self.t
        face = self._face
        p.setPen(Qt.PenStyle.NoPen)
        g = QLinearGradient(0.0, -1.0, 0.0, 1.0)
        g.setColorAt(0.0, _c(primary, 0.05 * k))
        g.setColorAt(0.45, _c(primary, 0.15 * k))
        g.setColorAt(1.0, _c(primary, 0.05 * k))
        p.setBrush(QBrush(g))
        p.drawPath(face)

        # skin: cheek glow + scan lines, clipped to the face
        p.save()
        p.setClipPath(face)
        p.setPen(Qt.PenStyle.NoPen)
        for e in (-1.0, 1.0):
            c = QPointF(e * 0.36, 0.22)
            rg = QRadialGradient(c, 0.30)
            rg.setColorAt(0.0, _c(accent, (0.11 + 0.10 * self.glow) * k))
            rg.setColorAt(1.0, _c(accent, 0.0))
            p.setBrush(QBrush(rg))
            p.drawEllipse(c, 0.30, 0.30)
        p.setBrush(Qt.BrushStyle.NoBrush)
        scan_y = -1.0 + 2.1 * ((t * 0.22) % 1.0)
        for i in range(57):
            y = -0.95 + i * 0.034
            w = _face_w(y)
            if w <= 0.01:
                continue
            bow = 0.05 * w / 0.68
            boost = math.exp(-((y - scan_y) ** 2) / 0.012)
            a = 0.10 + (0.07 if i % 4 == 0 else 0.0)
            ln = QPainterPath()
            ln.moveTo(-w - 0.02, y)
            ln.quadTo(QPointF(0.0, y + 2.0 * bow), QPointF(w + 0.02, y))
            p.setPen(_pen(_c(primary, a * k), u))
            p.drawPath(ln)
            if boost > 0.12:
                p.setPen(_pen(_c(accent, 0.65 * boost * k), 1.4 * u))
                p.drawPath(ln)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(primary, 0.14 * k), 5.0 * u))
        p.drawPath(face)
        p.setPen(_pen(_c(primary, 0.85 * k), 1.5 * u))
        p.drawPath(face)

        self._circlet(p, primary, accent, u, k)
        self._cheek_marks(p, primary, accent, u, k)
        for e in (-1.0, 1.0):
            self._brow(p, e, primary, accent, u, k)
        for e in (-1.0, 1.0):
            self._eye(p, e, primary, accent, bg, u, k)
        self._nose(p, primary, u, k)
        self._mouth(p, primary, accent, bg, u, k)

    def _circlet(self, p, primary, accent, u, k):
        t = self.t
        c = QPainterPath()
        c.moveTo(-0.60, -0.46)
        _arc_to(c, QPointF(0.60, -0.46), QPointF(0.0, -0.66))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(primary, 0.55 * k), 1.5 * u))
        p.drawPath(c)
        pulse = 0.5 + 0.5 * math.sin(t * 2.0)
        gem = QPointF(0.0, -0.66)
        gl = QRadialGradient(gem, 0.16)
        gl.setColorAt(0.0, _c(accent, (0.55 + 0.35 * pulse) * k))
        gl.setColorAt(1.0, _c(accent, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gl))
        p.drawEllipse(gem, 0.16, 0.16)
        d = QPolygonF([QPointF(gem.x(), gem.y() - 0.05), QPointF(gem.x() + 0.032, gem.y()),
                       QPointF(gem.x(), gem.y() + 0.05), QPointF(gem.x() - 0.032, gem.y())])
        p.setBrush(QBrush(_c(accent, 0.95 * k)))
        p.drawPolygon(d)
        p.setBrush(QBrush(_c(primary, 0.8 * k)))
        for e in (-1.0, 1.0):
            p.drawEllipse(QPointF(e * 0.60, -0.46), 0.016, 0.016)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # a data pulse running along the circlet
        pt = c.pointAtPercent((t * 0.35) % 1.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(accent, 0.8 * k)))
        p.drawEllipse(pt, 0.012, 0.012)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _cheek_marks(self, p, primary, accent, u, k):
        t = self.t
        p.setBrush(Qt.BrushStyle.NoBrush)
        for e in (-1.0, 1.0):
            for j, (x0, y0) in enumerate(((0.53, -0.08), (0.59, 0.12))):
                m = QPainterPath()
                m.moveTo(e * x0, y0)
                m.lineTo(e * x0, y0 + 0.12)
                m.lineTo(e * (x0 - 0.08), y0 + 0.20)
                m.lineTo(e * (x0 - 0.08), y0 + 0.28)
                pulse = 0.5 + 0.5 * math.sin(t * 2.2 + j * 1.3 + e)
                p.setPen(_pen(_c(primary, (0.22 + 0.30 * pulse) * k), 1.2 * u))
                p.drawPath(m)
                end = m.pointAtPercent(1.0)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_c(accent, (0.35 + 0.5 * pulse) * k)))
                p.drawEllipse(end, 0.012, 0.012)
                p.drawEllipse(m.pointAtPercent((t * 0.4 + j * 0.5) % 1.0), 0.009, 0.009)
                p.setBrush(Qt.BrushStyle.NoBrush)

    def _brow(self, p, e, primary, accent, u, k):
        lift = self.brow
        b = QPainterPath()
        b.moveTo(e * 0.09, -0.275 - lift * 0.6)
        _arc_to(b, QPointF(e * 0.47, -0.262 - lift * 0.3), QPointF(e * 0.28, -0.345 - lift))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(primary, 0.16 * k), 5.0 * u))
        p.drawPath(b)
        p.setPen(_pen(_c(primary, 0.80 * k), 2.0 * u))
        p.drawPath(b)
        b2 = QPainterPath(b)
        b2.translate(0.0, -0.022)
        p.setPen(_pen(_c(accent, 0.30 * k), 1.0 * u))
        p.drawPath(b2)

    def _eye(self, p, e, primary, accent, bg, u, k):
        t = self.t
        cxe, cye = e * 0.27, -0.10
        rx = 0.165
        op = max(0.02, self.eye_open * (1.0 - self._blink_v))
        hu = 0.072 * op
        hl = 0.040 * op
        inner = QPointF(cxe - e * rx, cye + 0.012)
        outer = QPointF(cxe + e * rx, cye - 0.026)

        up = QPainterPath()
        up.moveTo(inner)
        _arc_to(up, outer, QPointF(cxe, cye - hu))
        almond = QPainterPath(up)
        _arc_to(almond, inner, QPointF(cxe, cye + hl))
        almond.closeSubpath()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(bg, 0.85)))
        p.drawPath(almond)

        # iris, clipped to the eye opening
        p.save()
        p.setClipPath(almond)
        ix = cxe + self.eye_x * 0.05
        iy = cye - 0.004 + self.eye_y * 0.028
        ir = 0.070
        ic = QPointF(ix, iy)
        ig = QRadialGradient(ic, ir)
        ig.setColorAt(0.0, _c(accent, 1.0 * k))
        ig.setColorAt(0.65, _c(primary, 0.85 * k))
        ig.setColorAt(1.0, _c(primary, 0.55 * k))
        p.setBrush(QBrush(ig))
        p.drawEllipse(ic, ir, ir)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(accent, 0.9 * k), 1.2 * u))
        p.drawEllipse(ic, ir, ir)
        p.setPen(_pen(_c(bg, 0.55), u))
        for i in range(10):
            a = math.radians(i * 36.0 + t * 25.0 * e)
            p.drawLine(QPointF(ix + 0.040 * math.cos(a), iy + 0.040 * math.sin(a)),
                       QPointF(ix + 0.058 * math.cos(a), iy + 0.058 * math.sin(a)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(bg, 0.92)))
        pr = 0.026 * (1.0 + 0.25 * self.glow + 0.2 * self.listen)
        p.drawEllipse(ic, pr, pr)
        p.setBrush(QBrush(QColor(255, 255, 255, int(235 * k))))
        p.drawEllipse(QPointF(ix - 0.022, iy - 0.024), 0.011, 0.011)
        p.drawEllipse(QPointF(ix + 0.026, iy + 0.020), 0.006, 0.006)
        p.restore()

        # lids and a little wing at the outer corner
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(primary, 0.14 * k), 5.5 * u))
        p.drawPath(up)
        p.setPen(_pen(_c(primary, 0.95 * k), 2.4 * u))
        p.drawPath(up)
        lo = QPainterPath()
        lo.moveTo(inner)
        _arc_to(lo, outer, QPointF(cxe, cye + hl))
        p.setPen(_pen(_c(primary, 0.45 * k), 1.1 * u))
        p.drawPath(lo)
        p.setPen(_pen(_c(primary, 0.9 * k), 1.8 * u))
        p.drawLine(outer, QPointF(outer.x() + e * 0.075, outer.y() - 0.042))

    def _nose(self, p, primary, u, k):
        p.setBrush(Qt.BrushStyle.NoBrush)
        br = QPainterPath()
        br.moveTo(0.0, -0.10)
        br.lineTo(0.0, 0.17)
        p.setPen(_pen(_c(primary, 0.14 * k), u))
        p.drawPath(br)
        n = QPainterPath()
        n.moveTo(-0.095, 0.215)
        _arc_to(n, QPointF(0.095, 0.215), QPointF(0.0, 0.275))
        p.setPen(_pen(_c(primary, 0.55 * k), 1.4 * u))
        p.drawPath(n)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(primary, 0.55 * k)))
        for e in (-1.0, 1.0):
            p.drawEllipse(QPointF(e * 0.045, 0.235), 0.011, 0.007)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _mouth(self, p, primary, accent, bg, u, k):
        m = _clamp(self.mouth, 0.0, 1.0)
        my = 0.50
        wm = 0.150 + 0.035 * self.wide - 0.02 * m
        lift = 0.014 * (1.0 - m)
        gap = 0.004 + 0.092 * m
        L = QPointF(-wm, my - lift)
        R = QPointF(wm, my - lift)

        up_out = QPainterPath()
        up_out.moveTo(L)
        up_out.quadTo(QPointF(-wm * 0.45, my - 0.058 - lift), QPointF(0.0, my - 0.032))
        up_out.quadTo(QPointF(wm * 0.45, my - 0.058 - lift), R)

        lo_out = QPainterPath()
        lo_out.moveTo(L)
        _arc_to(lo_out, R, QPointF(0.0, my + gap + 0.056))

        inner_up = QPainterPath()
        inner_up.moveTo(L)
        _arc_to(inner_up, R, QPointF(0.0, my - 0.006))
        mouth = QPainterPath(inner_up)
        _arc_to(mouth, L, QPointF(0.0, my + gap))
        mouth.closeSubpath()

        lips = QPainterPath(up_out)
        lips.lineTo(R)
        lips.addPath(lo_out)
        p.setPen(Qt.PenStyle.NoPen)
        lg = QLinearGradient(0.0, my - 0.06, 0.0, my + 0.12)
        lg.setColorAt(0.0, _c(accent, 0.22 * k))
        lg.setColorAt(1.0, _c(primary, 0.14 * k))
        p.setBrush(QBrush(lg))
        p.drawPath(up_out)
        p.drawPath(lo_out)
        if m > 0.06:
            p.setBrush(QBrush(_c(bg, 0.92)))
            p.drawPath(mouth)
            ig = QLinearGradient(0.0, my, 0.0, my + gap)
            ig.setColorAt(0.0, _c(accent, 0.05))
            ig.setColorAt(1.0, _c(accent, 0.38 * m * k))
            p.setBrush(QBrush(ig))
            p.drawPath(mouth)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_c(primary, 0.15 * k), 4.5 * u))
        p.drawPath(lo_out)
        p.setPen(_pen(_c(primary, 0.9 * k), 1.8 * u))
        p.drawPath(up_out)
        p.setPen(_pen(_c(primary, 0.75 * k), 1.5 * u))
        p.drawPath(lo_out)
        if m <= 0.06:
            p.setPen(_pen(_c(primary, 0.9 * k), 1.5 * u))
            p.drawPath(inner_up)
        else:
            p.setPen(_pen(_c(accent, 0.55 * k), 1.1 * u))
            p.drawPath(inner_up)
        # chin node
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_c(accent, 0.5 * k)))
        p.drawEllipse(QPointF(0.0, 0.82), 0.012, 0.012)
        p.setBrush(Qt.BrushStyle.NoBrush)
