"""
JARVIS - novo visual (previa independente).

Nada aqui mexe no Jarvis atual: e so uma janela de demonstracao com o visual
inteiramente novo. Teclas: 1 espera, 2 ouvindo, 3 pensando, 4 falando,
Espaco liga/desliga a demo automatica, F11 tela cheia, Esc sai.

Conceito: em vez de um rosto, um NUCLEO NEURAL - uma esfera de luz feita de
nos e conexoes, que respira, vibra com a voz e muda de cor conforme o estado,
cercada por um anel espectral e orbitas. Paineis de vidro nas laterais.
"""
import math
import random
import sys
import time

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics, QLinearGradient,
                         QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PyQt6.QtWidgets import QApplication, QWidget

from holo_ui import HoloMixin

try:
    import psutil
except Exception:
    psutil = None

BG = QColor(6, 7, 15)
STATES = {
    "idle": ("EM ESPERA", (130, 98, 255), (176, 156, 255)),
    "listening": ("ESCUTANDO", (40, 235, 190), (160, 255, 228)),
    "thinking": ("PENSANDO", (255, 176, 64), (255, 226, 150)),
    "speaking": ("FALANDO", (130, 98, 255), (60, 255, 200)),
}
ORDER = ["idle", "listening", "thinking", "speaking"]
LOGTXT = {
    "idle": "Aguardando chamada",
    "listening": "Ouvindo seu comando",
    "thinking": "Interpretando o pedido",
    "speaking": "Respondendo por voz",
}
MODULES = ["Voz", "Visão", "Navegador", "Memória", "Agentes", "Agenda"]


def qc(c, a=1.0):
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(max(0.0, min(1.0, a)) * 255))


def mk_font(size, bold=False, spacing=0.0, family="Segoe UI"):
    f = QFont(family, size)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


class NovoVisual(HoloMixin, QWidget):
    STATES = STATES

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self._tr("JARVIS - novo visual (previa)"))
        self.resize(1280, 780)
        self.setMinimumSize(1000, 640)
        self.state = "idle"
        self.auto = True
        self._auto_t = 0.0
        self.t = 0.0
        self._last = time.perf_counter()
        self.amp = 0.0
        self.spec = np.zeros(96)
        self.col = list(STATES["idle"][1])
        self.acc = list(STATES["idle"][2])
        self.think_v = 0.0
        self.cpu = self.mem = self.disk = 0.0
        self._stat_t = 99.0
        self._bg = None
        self.log = [(time.strftime("%H:%M:%S"), "Visual novo carregado")]
        self.tab = "home"
        self.panel = None
        self._panel_last = None
        self.panel_p = 0.0
        self.panel_scroll = 0.0
        self._panel_max = 0.0
        self._hits = []
        self._hover = None
        self.setMouseTracking(True)
        self._seed()

        n = 520
        i = np.arange(n) + 0.5
        phi = np.arccos(1 - 2 * i / n)
        th = math.pi * (1 + 5 ** 0.5) * i
        self.pts = np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)
        self.ph = np.random.rand(n) * 6.28
        d = ((self.pts[:, None, :] - self.pts[None, :, :]) ** 2).sum(2)
        np.fill_diagonal(d, 9.0)
        nn = np.argsort(d, 1)[:, :2]
        pairs = set()
        for a in range(n):
            for b in nn[a]:
                pairs.add((min(a, int(b)), max(a, int(b))))
        self.pairs = np.array(sorted(pairs))

        self.f_title = mk_font(30, False, 16.0)
        self.f_state = mk_font(10, True, 7.0)
        self.f_small = mk_font(8, True, 2.6)
        self.f_body = mk_font(10)
        self.f_mono = mk_font(9, False, 0.0, "Consolas")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.init_extras()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    # ------------------------------------------------------------ logic
    def _set(self, s):
        if s == self.state:
            return
        self.state = s
        self.log.append((time.strftime("%H:%M:%S"), self._tr(LOGTXT[s])))
        self.log = self.log[-14:]

    def keyPressEvent(self, e):
        k = e.key()
        if Qt.Key.Key_1 <= k <= Qt.Key.Key_4:
            self.auto = False
            self._set(ORDER[k - Qt.Key.Key_1])
        elif k == Qt.Key.Key_Space:
            self.auto = not self.auto
        elif k == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif k == Qt.Key.Key_N:
            self.auto = False
            self._set('speaking')
            self.open_news()
        elif k == Qt.Key.Key_S:
            self.auto = False
            self._set('speaking')
            self.open_search()
        elif k == Qt.Key.Key_H:
            self._goto('home')
        elif k == Qt.Key.Key_T:
            self._goto('tasks')
        elif k == Qt.Key.Key_R:
            self._goto('routines')
        elif k == Qt.Key.Key_M:
            self.do_mute()
        elif k == Qt.Key.Key_I:
            self.do_stop()
        elif k == Qt.Key.Key_C:
            self._goto('controls')
        elif k == Qt.Key.Key_G:
            self._goto('settings')
        elif k == Qt.Key.Key_O:
            self.do_style()
        elif k == Qt.Key.Key_Escape:
            if self.panel is not None:
                self.close_panel()
            elif self.isFullScreen():
                self.showNormal()
            else:
                self.close()

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        self.t += dt
        if self.auto:
            self._auto_t += dt
            if self._auto_t > 5.0:
                self._auto_t = 0.0
                self._set(ORDER[(ORDER.index(self.state) + 1) % 4])
        if self.muted and self.state == 'listening':
            self._set('idle')
        s, t = self.state, self.t
        if s == "speaking":
            tgt = 0.30 + 0.40 * abs(math.sin(t * 3.3) * math.sin(t * 1.3 + 1)) + 0.1 * random.random()
        elif s == "listening":
            tgt = 0.10 + 0.35 * abs(math.sin(t * 2.1 + math.sin(t * 0.7) * 2)) * random.random() ** 0.5
        elif s == "thinking":
            tgt = 0.10 + 0.05 * math.sin(t * 4)
        else:
            tgt = 0.03 + 0.02 * math.sin(t)
        self.amp += (tgt - self.amp) * (1 - math.exp(-dt / 0.07))
        i = np.arange(96)
        base = np.abs(np.sin(i * 0.41 + t * 3.1) * np.sin(i * 0.13 - t * 1.9))
        self.spec += (self.amp * (0.25 + 0.9 * base) + 0.02 - self.spec) * (1 - math.exp(-dt / 0.06))
        pc, ac = STATES[s][1], STATES[s][2]
        k = 1 - math.exp(-dt / 0.25)
        for j in range(3):
            self.col[j] += (pc[j] - self.col[j]) * k
            self.acc[j] += (ac[j] - self.acc[j]) * k
        self.think_v += ((1.0 if s == "thinking" else 0.0) - self.think_v) * (1 - math.exp(-dt / 0.4))
        self._stat_t += dt
        if self._stat_t > 1.0:
            self._stat_t = 0.0
            if psutil:
                try:
                    self.cpu = psutil.cpu_percent()
                    self.mem = psutil.virtual_memory().percent
                    self.disk = psutil.disk_usage("C:\\").percent
                except Exception:
                    pass
            else:
                self.cpu, self.mem, self.disk = 23.0, 48.0, 61.0
        self.panel_p += ((1.0 if self.panel is not None else 0.0) - self.panel_p) * (1 - math.exp(-dt / 0.12))
        self.update()

    # --------------------------------------------------------- background
    def _make_bg(self):
        W, H = self.width(), self.height()
        pm = QPixmap(W, H)
        pm.fill(BG)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRadialGradient(W / 2, H * 0.40, max(W, H) * 0.7)
        g.setColorAt(0.0, QColor(22, 18, 48))
        g.setColorAt(1.0, QColor(6, 7, 15, 0))
        q.fillRect(0, 0, W, H, g)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(255, 255, 255, 16))
        for x in range(20, W, 34):
            for y in range(20, H, 34):
                q.drawEllipse(QPointF(x, y), 0.9, 0.9)
        q.end()
        self._bg = pm

    # ------------------------------------------------------------- paint
    def paintEvent(self, _):
        try:
            self._paint()
        except Exception as e:  # keep the preview alive while iterating
            print("paint error:", e)

    def _paint(self):
        W, H = self.width(), self.height()
        if self._bg is None or self._bg.width() != W or self._bg.height() != H:
            self._make_bg()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.drawPixmap(0, 0, self._bg)
        self._hits = []
        self._topbar(p, W)
        self._tabs(p, W)
        if self.tab == "home":
            self._home(p, W, H)
        elif self.tab == "tasks":
            self._tasks_view(p, W, H)
        elif self.tab == "routines":
            self._routines_view(p, W, H)
        elif self.tab == "controls":
            self._controls_view(p, W, H)
        else:
            self._settings_view(p, W, H)
        self._capsule(p, W, H)
        self._signature(p, W, H)
        p.end()

    # --------------------------------------------------------------- orb
    def _orb_neural(self, p, cx, cy, R):
        t, amp = self.t, self.amp
        col, acc = self.col, self.acc
        C = QPointF(cx, cy)
        NO, NB = Qt.PenStyle.NoPen, Qt.BrushStyle.NoBrush

        g = QRadialGradient(C, R * 2.7)
        g.setColorAt(0.0, qc(col, 0.22 + 0.28 * amp))
        g.setColorAt(0.5, qc(col, 0.06))
        g.setColorAt(1.0, qc(col, 0.0))
        p.setPen(NO)
        p.setBrush(g)
        p.drawEllipse(C, R * 2.7, R * 2.7)

        # spectrum ring
        r0 = R * 1.34
        rot = t * 0.12
        for i in range(96):
            a = rot + i * (2 * math.pi / 96)
            v = float(self.spec[i])
            r1 = r0 + R * (0.04 + 0.34 * v)
            ca, sa = math.cos(a), math.sin(a)
            pen = QPen(qc(acc, 0.30 + 0.65 * min(1.0, v * 1.8)), 2.6 if i % 2 else 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx + ca * r0, cy + sa * r0), QPointF(cx + ca * r1, cy + sa * r1))
        p.setBrush(NB)
        p.setPen(QPen(qc(col, 0.22), 1))
        p.drawEllipse(C, r0 - R * 0.06, r0 - R * 0.06)

        # the neural sphere
        P = self.pts
        ang = t * 0.22 * (1 + 2.2 * self.think_v) + self.think_v * 1.1 * P[:, 1]
        ca_, sa_ = np.cos(ang), np.sin(ang)
        x = P[:, 0] * ca_ + P[:, 2] * sa_
        z = -P[:, 0] * sa_ + P[:, 2] * ca_
        y = P[:, 1]
        ax = 0.38 + 0.10 * math.sin(t * 0.23)
        cb, sb = math.cos(ax), math.sin(ax)
        y2 = y * cb - z * sb
        z2 = y * sb + z * cb
        listen = 1.0 if self.state == "listening" else 0.0
        disp = (1 + amp * 0.20 * np.sin(self.ph + t * 5.0 + P[:, 1] * 4.0)
                + 0.018 * math.sin(t * 1.1) - 0.05 * amp * listen)
        X, Y, Z = x * disp, y2 * disp, z2 * disp
        f = 3.6 / (3.6 - Z)
        sx = cx + X * R * f
        sy = cy + Y * R * f
        depth = np.clip((Z + 1) / 2, 0, 1)
        mixv = np.clip((Y + 1) / 2, 0, 1)
        sxl, syl = sx.tolist(), sy.tolist()
        dl, ml, fl, zl = depth.tolist(), mixv.tolist(), f.tolist(), Z.tolist()
        sc = R / 200.0

        a_i, b_i = self.pairs[:, 0], self.pairs[:, 1]
        bucket = np.digitize((Z[a_i] + Z[b_i]) / 2, [-0.25, 0.25])

        def lines(bk, alpha, width):
            idx = np.nonzero(bucket == bk)[0]
            ls = [QLineF(sxl[a], syl[a], sxl[b], syl[b]) for a, b in self.pairs[idx].tolist()]
            p.setPen(QPen(qc(col, alpha), width))
            p.drawLines(ls)

        def dots(idx):
            p.setPen(NO)
            for i in idx:
                d, m = dl[i], ml[i]
                c = (col[0] + (acc[0] - col[0]) * m, col[1] + (acc[1] - col[1]) * m,
                     col[2] + (acc[2] - col[2]) * m)
                p.setBrush(qc(c, 0.18 + 0.82 * d ** 1.6))
                s = (0.9 + 2.0 * d) * sc * fl[i]
                p.drawEllipse(QPointF(sxl[i], syl[i]), s, s)

        order = np.argsort(Z).tolist()
        back = [i for i in order if zl[i] < 0]
        front = [i for i in order if zl[i] >= 0]
        lines(0, 0.07, 1.0)
        dots(back)

        cr = R * (0.52 + 0.22 * amp + 0.03 * math.sin(t * 2.0))
        g2 = QRadialGradient(C, cr)
        g2.setColorAt(0.0, QColor(255, 255, 255, 215))
        g2.setColorAt(0.25, qc(acc, 0.85))
        g2.setColorAt(0.65, qc(col, 0.30))
        g2.setColorAt(1.0, qc(col, 0.0))
        p.setPen(NO)
        p.setBrush(g2)
        p.drawEllipse(C, cr, cr)

        lines(1, 0.16, 1.0)
        lines(2, 0.34, 1.2)
        dots(front)

        # orbits with comet satellites
        p.setBrush(NB)
        for k, (tilt, a, b, spd) in enumerate(((24, 1.62, 0.50, 0.7), (-38, 1.78, 0.42, -0.5),
                                               (72, 1.55, 0.58, 0.9))):
            p.save()
            p.translate(cx, cy)
            p.rotate(tilt + 4 * math.sin(t * 0.2 + k))
            p.setPen(QPen(qc(col, 0.18), 1))
            p.drawEllipse(QRectF(-R * a, -R * b, 2 * R * a, 2 * R * b))
            th = t * spd + k * 2.1
            sg = 1 if spd > 0 else -1
            p.setPen(NO)
            for j in range(12):
                tj = th - sg * j * 0.07
                p.setBrush(qc(acc, (1 - j / 12.0) * 0.9))
                rr = max(0.6, (3.4 - j * 0.2) * R / 200.0)
                p.drawEllipse(QPointF(R * a * math.cos(tj), R * b * math.sin(tj)), rr, rr)
            p.restore()

    # ---------------------------------------------------------- chrome
    def _wordmark(self, p, cx, cy, R):
        y = cy + R * (1.86 if self.orb_style == 'holo' else 1.78) + 14
        p.setFont(self.f_title)
        p.setPen(QColor(244, 242, 255, 235))
        al = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        p.drawText(QRectF(cx - 300, y, 600, 44), al, getattr(self, "name", "JARVIS"))
        p.setFont(self.f_state)
        p.setPen(qc(self.acc, 0.95))
        p.drawText(QRectF(cx - 300, y + 42, 600, 22), al, self._tr(STATES[self.state][0]))

    def _topbar_old(self, p, W):
        c = QPointF(44, 40)
        poly = QPainterPath()
        for i in range(6):
            a = math.radians(60 * i - 30)
            q = QPointF(c.x() + 12 * math.cos(a), c.y() + 12 * math.sin(a))
            poly.moveTo(q) if i == 0 else poly.lineTo(q)
        poly.closeSubpath()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qc(self.col, 0.95), 2))
        p.drawPath(poly)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(self.acc, 0.95))
        p.drawEllipse(c, 3.2, 3.2)
        p.setFont(self.f_small)
        p.setPen(QColor(255, 255, 255, 215))
        p.drawText(QRectF(66, 26, 300, 16), Qt.AlignmentFlag.AlignLeft, "JARVIS")
        p.setPen(QColor(255, 255, 255, 90))
        p.drawText(QRectF(66, 42, 300, 14), Qt.AlignmentFlag.AlignLeft, self._tr("JARVIS SYSTEMS  ·  DESKTOP"))
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QRectF(W - 28 - 80, 26, 80, 26), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   time.strftime("%H:%M"))
        pw = 138
        r = QRectF(W - 28 - 80 - pw - 12, 26, pw, 26)
        path = QPainterPath()
        path.addRoundedRect(r, 13, 13)
        p.fillPath(path, QColor(10, 10, 24, 235))
        p.fillPath(path, qc(self.col, 0.16))
        p.setPen(QPen(qc(self.col, 0.6), 1))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        pulse = 0.6 + 0.4 * math.sin(self.t * 4)
        p.setBrush(qc(self.acc, pulse))
        p.drawEllipse(QPointF(r.x() + 15, r.center().y()), 3.5, 3.5)
        p.setFont(self.f_small)
        p.setPen(qc(self.acc, 1.0))
        p.drawText(QRectF(r.x() + 26, r.y(), pw - 30, r.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._tr(STATES[self.state][0]))

    def _signature(self, p, W, H):
        """Subtle creator credit, anchored to the lower-right edge."""
        p.save()
        p.setFont(mk_font(8, True))
        p.setPen(QColor(178, 188, 220, 155))
        p.drawText(
            QRectF(W - 178, H - 24, 150, 15),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "By blaackwood",
        )
        p.restore()

    def _card(self, p, x, y, w, h, title):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), 16, 16)
        p.fillPath(path, QColor(255, 255, 255, 10))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 24), 1))
        p.drawPath(path)
        p.setPen(QPen(qc(self.acc, 0.8), 2))
        p.drawLine(QPointF(x + 16, y + 0.5), QPointF(x + 46, y + 0.5))
        p.setFont(self.f_small)
        p.setPen(QColor(255, 255, 255, 125))
        p.drawText(QRectF(x + 16, y + 12, w - 32, 16), Qt.AlignmentFlag.AlignLeft, self._tr(title))

    def _left(self, p, x, y, w):
        self._card(p, x, y, w, 152, "SISTEMA")
        for i, (n, v) in enumerate((("CPU", self.cpu), ("MEMORIA", self.mem), ("DISCO", self.disk))):
            yy = y + 42 + i * 34
            p.setFont(self.f_body)
            p.setPen(QColor(255, 255, 255, 170))
            p.drawText(QRectF(x + 16, yy, w - 32, 16), Qt.AlignmentFlag.AlignLeft, self._tr(n))
            p.drawText(QRectF(x + 16, yy, w - 32, 16), Qt.AlignmentFlag.AlignRight, "%d%%" % round(v))
            tr = QRectF(x + 16, yy + 20, w - 32, 5)
            pt = QPainterPath()
            pt.addRoundedRect(tr, 2.5, 2.5)
            p.fillPath(pt, QColor(255, 255, 255, 20))
            fw = max(5.0, tr.width() * min(1.0, v / 100.0))
            fr = QRectF(tr.x(), tr.y(), fw, tr.height())
            gr = QLinearGradient(fr.left(), 0, fr.right(), 0)
            gr.setColorAt(0, qc(self.col, 1))
            gr.setColorAt(1, qc(self.acc, 1))
            pf = QPainterPath()
            pf.addRoundedRect(fr, 2.5, 2.5)
            p.fillPath(pf, gr)

        y2 = y + 168
        self._card(p, x, y2, w, 176, "MÓDULOS")
        cw = (w - 44) / 2.0
        for i, m in enumerate(MODULES):
            m = self._tr(m)
            r = QRectF(x + 16 + (i % 2) * (cw + 12), y2 + 40 + (i // 2) * 42, cw, 32)
            pp = QPainterPath()
            pp.addRoundedRect(r, 10, 10)
            p.fillPath(pp, QColor(255, 255, 255, 12))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc((60, 255, 200), 0.55 + 0.45 * math.sin(self.t * 2 + i)))
            p.drawEllipse(QPointF(r.x() + 12, r.center().y()), 3.2, 3.2)
            p.setFont(self.f_body)
            p.setPen(QColor(255, 255, 255, 205))
            p.drawText(QRectF(r.x() + 24, r.y(), cw - 26, r.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._tr(m))

    def _right(self, p, x, y, w, h):
        self._card(p, x, y, w, h, "ATIVIDADE")
        fm = QFontMetrics(self.f_body)
        body_top = y + 44
        available = max(20.0, h - 52)
        text_width = max(40, int(w - 32))
        # Wrap every complete entry; no eliding/truncation. Select recent entries
        # that fit, but always show at least the newest entry even if it is long.
        # A pele live usa QTextEdit sobre o card para permitir selecao manual.
        # Nao desenhar o mesmo log embaixo (duplicava/empilhava texto).
        if getattr(self, "live", False):
            return
        prepared = []
        for idx, (ts, tx) in enumerate(self.log):
            wrapped = wrap_lines(fm, str(tx), text_width)
            row_h = 15 + 3 + max(1, len(wrapped)) * fm.lineSpacing() + 5
            prepared.append((idx, ts, tx, wrapped, row_h))
        selected = []
        used = 0.0
        for item in reversed(prepared):
            if selected and used + item[4] > available:
                break
            selected.append(item)
            used += item[4]
        selected.reverse()
        n = max(1, len(selected))
        yy = body_top
        for k, (idx, ts, tx, wrapped, row_h) in enumerate(selected):
            a = 0.35 + 0.65 * (k + 1) / n
            p.setFont(self.f_mono)
            p.setPen(qc(self.acc, 0.55 * a))
            p.drawText(QRectF(x + 16, yy, w - 32, 14), Qt.AlignmentFlag.AlignLeft, ts)
            yy += 16
            p.setFont(self.f_body)
            p.setPen(QColor(255, 255, 255, int(235 * a)))
            for line in wrapped:
                p.drawText(QPointF(x + 16, yy + fm.ascent()), self._tr(line))
                yy += fm.lineSpacing()
            yy += 6

    def _capsule(self, p, W, H):
        w = min(760.0, W * 0.56)
        h = 52.0
        x = (W - w) / 2.0
        y = H - 84.0
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        p.fillPath(path, QColor(255, 255, 255, 14))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qc(self.col, 0.35 + 0.4 * self.amp), 1.2))
        p.drawPath(path)
        mc = QPointF(x + 30, y + h / 2)
        rr = 15 + 5 * self.amp
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(self.col, 0.18))
        p.drawEllipse(mc, rr, rr)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qc(self.acc, 0.9), 1.5))
        p.drawEllipse(mc, 15, 15)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
        p.drawRoundedRect(QRectF(mc.x() - 3, mc.y() - 7, 6, 10), 3, 3)
        p.drawArc(QRectF(mc.x() - 6, mc.y() - 5, 12, 11), 200 * 16, 140 * 16)
        p.drawLine(QPointF(mc.x(), mc.y() + 6), QPointF(mc.x(), mc.y() + 9))
        if self.muted:
            p.setPen(QPen(QColor(255, 100, 130), 2.2))
            p.drawLine(QPointF(mc.x() - 8, mc.y() - 8), QPointF(mc.x() + 8, mc.y() + 9))
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 105))
        p.drawText(QRectF(x + 62, y, w - 120, h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "" if getattr(self, "live", False) else self._tr("Fale com o Jarvis ou digite um comando..."))
        sc = QPointF(x + w - 30, y + h / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(self.col, 0.95))
        p.drawEllipse(sc, 15, 15)
        p.setPen(QPen(QColor(255, 255, 255, 245), 2))
        p.drawLine(QPointF(sc.x() - 5, sc.y()), QPointF(sc.x() + 5, sc.y()))
        p.drawLine(QPointF(sc.x() + 1, sc.y() - 5), QPointF(sc.x() + 5, sc.y()))
        p.drawLine(QPointF(sc.x() + 1, sc.y() + 5), QPointF(sc.x() + 5, sc.y()))
        p.setFont(mk_font(8))
        p.setPen(QColor(255, 255, 255, 70))
        p.drawText(QRectF(0, y + h + 10, W, 16), Qt.AlignmentFlag.AlignHCenter,
                   "" if getattr(self, "live", False) else self._tr("1-4 states  N news  S search  H home  T tasks  R routines  C controls  G settings  F4 mute  ESC interrupt  F11 full screen  ESC exit"))



    # ===================================================== data + actions
    def _seed(self):
        self.f_head = mk_font(10, True)
        self.f_meta = mk_font(8)
        self.tasks = [
            {"t": "Gerar resumo semanal das notícias", "tag": "Pesquisa", "due": "Hoje · 18:00", "pr": 1, "st": 0, "pg": 0.0},
            {"t": "Organizar a pasta de downloads", "tag": "Arquivos", "due": "Amanhã", "pr": 0, "st": 0, "pg": 0.0},
            {"t": "Configurar uma voz feminina para o Jarvis", "tag": "Voz", "due": "Sem prazo", "pr": 0, "st": 0, "pg": 0.0},
            {"t": "Atualizar a memória de longo prazo", "tag": "Memória", "due": "Hoje", "pr": 2, "st": 1, "pg": 0.62},
            {"t": "Revisar o novo visual do HUD", "tag": "Interface", "due": "Esta semana", "pr": 1, "st": 1, "pg": 0.35},
            {"t": "Backup da pasta do projeto", "tag": "Sistema", "due": "Feito às 22:30", "pr": 0, "st": 2, "pg": 1.0},
            {"t": "Testar comandos de voz sem internet", "tag": "Voz", "due": "Feito ontem", "pr": 1, "st": 2, "pg": 1.0},
        ]
        self.routines = [
            {"n": "Resumo da manhã", "d": "Notícias, agenda e clima falados ao acordar", "h": 7, "m": 0,
             "days": [0, 1, 2, 3, 4, 5, 6], "on": True, "last": "ok · hoje 07:00", "c": (130, 98, 255)},
            {"n": "Lembrete de estudo", "d": "Avisa a hora do bloco de estudos", "h": 19, "m": 0,
             "days": [0, 1, 2, 3, 4], "on": True, "last": "ok · ontem 19:00", "c": (60, 255, 200)},
            {"n": "Backup do projeto", "d": "Copia a pasta do Jarvis para o backup", "h": 22, "m": 30,
             "days": [0, 1, 2, 3, 4, 5, 6], "on": True, "last": "ok · ontem 22:30", "c": (255, 176, 64)},
            {"n": "Limpeza de downloads", "d": "Move arquivos antigos para a pasta de arquivos", "h": 10, "m": 0,
             "days": [5], "on": False, "last": "pausada", "c": (255, 100, 140)},
            {"n": "Relatório semanal", "d": "Resume o que foi feito e o que ficou pendente", "h": 20, "m": 0,
             "days": [6], "on": True, "last": "ok · dom 20:00", "c": (120, 190, 255)},
        ]

    def _goto(self, tab):
        self.tab = tab
        self._hover = None

    def open_panel(self, c):
        c = dict(c)
        c["ts"] = time.strftime("%H:%M:%S")
        self.panel = c
        self._panel_copy_text = c.pop("_copy_text", None)
        self._panel_last = c
        self.panel_scroll = 0.0
        self._goto("home")
        # Opening a detail panel is a view action, not a new activity event.

    def close_panel(self):
        self.panel = None

    def copy_panel_content(self):
        c = self.panel or {}
        explicit = getattr(self, "_panel_copy_text", None)
        if explicit is not None:
            text = str(explicit)
        elif c.get("paras"):
            text = "\n\n".join(str(v) for v in c.get("paras", []))
        elif c.get("items"):
            text = "\n".join(
                f"{i}. {it.get('h','')} — {it.get('src','')} — {it.get('when','')} — {it.get('url','')}"
                for i, it in enumerate(c.get("items", []), 1)
            )
        else:
            text = str(c.get("title") or "")
        QApplication.clipboard().setText(text)
        return text

    def open_news(self):
        url = "https://news.google.com/home?hl=pt-BR"
        self.open_panel({
            "kind": "NEWS", "title": "notícias do Brasil e do mundo 16 de novembro 2026",
            "items": [
                {"h": "'Apagão mundial' em 17 de novembro: especialista explica por que um colapso elétrico global é improvável",
                 "src": "G1", "when": "16 nov · 15:31", "host": "news.google.com", "url": url},
                {"h": "Programação de treinos do Brasil em São Paulo e credenciamento para atividades no Ibirapuera",
                 "src": "Confederação Brasileira de Basketball", "when": "16 nov · 13:03", "host": "news.google.com", "url": url},
                {"h": "Copa do Mundo Feminina da FIFA completa 35 anos e chega ao Brasil em 2027",
                 "src": "Prefeitura de Porto Alegre", "when": "16 nov · 10:18", "host": "news.google.com", "url": url},
                {"h": "Eleições no Brasil e nos EUA mostram força do eleitorado que não se identifica com extremos, diz Tim Dixon",
                 "src": "Folha de S.Paulo", "when": "16 nov · 23:00", "host": "news.google.com", "url": url},
                {"h": "Segunda-feira, 16/11/2026 - Notícias sobre o mercado financeiro, com Álvaro Bandeira",
                 "src": "Jornal do Brasil", "when": "16 nov · 11:14", "host": "news.google.com", "url": url},
                {"h": "Lula e Sánchez defendem união contra o avanço da extrema-direita",
                 "src": "Agência Brasil", "when": "16 nov · 15:09", "host": "news.google.com", "url": url},
            ]})

    def open_search(self):
        self.open_panel({
            "kind": "PESQUISA", "title": "como funciona a fotossíntese",
            "paras": [
                "A fotossíntese é o processo pelo qual plantas, algas e algumas bactérias transformam energia luminosa em energia química, produzindo glicose a partir de gás carbônico e água e liberando oxigênio.",
                "Ela acontece em duas etapas: a fase clara, nas membranas dos tilacoides, em que a luz quebra a água e gera ATP e NADPH; e o ciclo de Calvin, no estroma, em que esses compostos fixam o CO2 e montam o açúcar.",
                "Fatores como intensidade de luz, temperatura, concentração de CO2 e disponibilidade de água controlam a velocidade do processo, e por isso aparecem tanto em questões de biologia quanto na prática agrícola.",
            ],
            "sources": ["Khan Academy", "Brasil Escola", "Embrapa"]})

    # ============================================================ input
    def mouseMoveEvent(self, e):
        pos = e.position()
        hv = None
        for r, act, hid in reversed(self._hits):
            if r.contains(pos):
                hv = hid
                break
        if hv != self._hover:
            self._hover = hv
            self.setCursor(Qt.CursorShape.PointingHandCursor if hv else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position()
        for r, act, hid in reversed(self._hits):
            if r.contains(pos):
                act()
                break

    def wheelEvent(self, e):
        if self.panel is not None and self._panel_max > 0:
            self.panel_scroll = max(0.0, min(self._panel_max, self.panel_scroll - e.angleDelta().y() * 0.6))

    def _hit(self, rect, action, hid):
        self._hits.append((QRectF(rect), action, hid))

    # ============================================================ tabs
    def _tabs_old(self, p, W):
        n_open = sum(1 for t in self.tasks if t["st"] < 2)
        n_on = sum(1 for r in self.routines if r["on"])
        names = (("home", "INÍCIO", ""), ("tasks", "TAREFAS", str(n_open)), ("routines", "ROTINAS", str(n_on)))
        tw, gap = 126, 6
        x0 = (W - (3 * tw + 2 * gap)) / 2.0
        for i, (key, label, badge) in enumerate(names):
            r = QRectF(x0 + i * (tw + gap), 24, tw, 32)
            act = self.tab == key
            hov = self._hover == ("tab", key)
            path = QPainterPath()
            path.addRoundedRect(r, 16, 16)
            p.fillPath(path, qc(self.col, 0.24) if act else QColor(255, 255, 255, 22 if hov else 9))
            p.setBrush(NB)
            p.setPen(QPen(qc(self.acc, 0.75) if act else QColor(255, 255, 255, 22), 1))
            p.drawPath(path)
            p.setFont(self.f_small)
            p.setPen(QColor(255, 255, 255, 255 if act else 150))
            off = 9 if badge else 0
            p.drawText(QRectF(r.x() - off, r.y(), r.width(), r.height()), Qt.AlignmentFlag.AlignCenter, label)
            if badge:
                bc = QPointF(r.right() - 20, r.center().y())
                p.setPen(NO)
                p.setBrush(qc(self.acc, 0.9 if act else 0.35))
                p.drawEllipse(bc, 9, 9)
                p.setFont(mk_font(8, True))
                p.setPen(QColor(10, 10, 20, 255) if act else QColor(255, 255, 255, 220))
                p.drawText(QRectF(bc.x() - 9, bc.y() - 9, 18, 18), Qt.AlignmentFlag.AlignCenter, badge)
            self._hit(r, lambda k=key: self._goto(k), ("tab", key))

    # ============================================================= home
    def _home(self, p, W, H):
        cw = max(190, min(260, W * 0.2))
        pp = self.panel_p
        R0 = min(W * 0.14, H * 0.19)
        ph = min(H * 0.44, 360.0)
        ptop = H - 96 - ph
        avail = ptop - 84 - 8
        R1 = min(R0, avail / 3.9)
        R = R0 + (R1 - R0) * pp
        cy0 = H * 0.41
        cy1 = 92 + avail / 2.0 + 4
        cy = cy0 + (cy1 - cy0) * pp
        cx = W / 2.0
        self._orb(p, cx, cy, R)
        if pp < 0.99:
            p.setOpacity(max(0.0, 1.0 - pp * 1.4))
            self._wordmark(p, cx, cy, R)
            p.setOpacity(1.0)
        self._left(p, 28, 84, cw)
        self._right(p, W - 28 - cw, 84, cw, H - 84 - 110)
        if pp > 0.01 and self._panel_last:
            px = 28 + cw + 20
            self._content_panel(p, px, ptop, W - 2 * px, ph, pp)

    def _content_panel(self, p, x, y, w, h, pp):
        c = self._panel_last
        live = self.panel is not None and pp > 0.9
        p.save()
        p.setOpacity(max(0.0, min(1.0, pp)))
        p.translate(0, (1 - pp) * 28)
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), 18, 18)
        p.fillPath(path, QColor(13, 11, 28, 238))
        p.setBrush(NB)
        p.setPen(QPen(qc(self.col, 0.5), 1.2))
        p.drawPath(path)
        p.setPen(QPen(qc(self.acc, 0.9), 2))
        p.drawLine(QPointF(x + 18, y + 0.6), QPointF(x + 64, y + 0.6))

        fs = QFontMetrics(self.f_small)
        chipw = fs.horizontalAdvance(c["kind"]) + 26
        chip = QRectF(x + 16, y + 14, chipw, 24)
        pc = QPainterPath()
        pc.addRoundedRect(chip, 12, 12)
        p.fillPath(pc, qc(self.acc, 0.16))
        p.setFont(self.f_small)
        p.setPen(qc(self.acc, 1.0))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, self._tr(c["kind"]))
        fh = QFontMetrics(self.f_head)
        tx = x + 16 + chipw + 12
        tw = w - (tx - x) - 152
        p.setFont(self.f_head)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(tx, y + 14, tw, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fh.elidedText(c["title"], Qt.TextElideMode.ElideRight, int(tw)))
        p.setFont(self.f_mono)
        p.setPen(qc(self.acc, 0.7))
        p.drawText(QRectF(x + w - 146, y + 14, 62, 24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, c["ts"])
        cc = QPointF(x + w - 26, y + 26)
        hov = self._hover == ("panel", "close")
        p.setPen(NO)
        p.setBrush(QColor(255, 255, 255, 40 if hov else 16))
        p.drawEllipse(cc, 12, 12)
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.6))
        p.drawLine(QPointF(cc.x() - 4, cc.y() - 4), QPointF(cc.x() + 4, cc.y() + 4))
        p.drawLine(QPointF(cc.x() - 4, cc.y() + 4), QPointF(cc.x() + 4, cc.y() - 4))
        if live:
            self._hit(QRectF(x + w - 40, y + 12, 28, 28), self.close_panel, ("panel", "close"))
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawLine(QPointF(x + 16, y + 50), QPointF(x + w - 16, y + 50))

        body = QRectF(x + 2, y + 54, w - 4, h - 60)
        p.setClipRect(body)
        top = y + 60 - self.panel_scroll
        items = c.get("items")
        if items:
            ih = 82.0
            total = len(items) * ih
            for i, it in enumerate(items):
                yy = top + i * ih
                if yy + ih < body.top() or yy > body.bottom():
                    continue
                r = QRectF(x + 14, yy, w - 28 - 8, ih - 8)
                hid = ("item", i)
                hv = self._hover == hid
                pi = QPainterPath()
                pi.addRoundedRect(r, 12, 12)
                p.fillPath(pi, QColor(255, 255, 255, 24 if hv else 11))
                nc = QPointF(r.x() + 24, r.center().y())
                p.setPen(NO)
                p.setBrush(qc(self.acc, 0.18))
                p.drawEllipse(nc, 13, 13)
                p.setFont(mk_font(9, True))
                p.setPen(qc(self.acc, 1.0))
                p.drawText(QRectF(nc.x() - 13, nc.y() - 13, 26, 26), Qt.AlignmentFlag.AlignCenter, str(i + 1))
                hx = r.x() + 50
                hw = r.width() - 64
                p.setFont(self.f_head)
                p.setPen(QColor(255, 255, 255, 240))
                for li, ln in enumerate(wrap_lines(fh, it["h"], hw, 2)):
                    p.drawText(QPointF(hx, r.y() + 20 + li * (fh.lineSpacing())), ln)
                my = r.bottom() - 24
                fm_ = QFontMetrics(self.f_meta)
                src = fm_.elidedText(it["src"], Qt.TextElideMode.ElideRight, 170)
                sw = fm_.horizontalAdvance(src) + 18
                sr = QRectF(hx, my, sw, 18)
                ps = QPainterPath()
                ps.addRoundedRect(sr, 9, 9)
                p.fillPath(ps, qc(self.acc, 0.15))
                p.setFont(self.f_meta)
                p.setPen(qc(self.acc, 1.0))
                p.drawText(sr, Qt.AlignmentFlag.AlignCenter, src)
                p.setPen(QColor(255, 255, 255, 120))
                p.drawText(QRectF(hx + sw + 10, my, 140, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, it["when"])
                p.drawText(QRectF(r.right() - 190, my, 176, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           it["host"] + "  ↗")
        else:
            fb = QFontMetrics(self.f_body)
            yy = top
            p.setFont(self.f_body)
            for para in c.get("paras", []):
                p.setPen(QColor(255, 255, 255, 220))
                for ln in wrap_lines(fb, para, w - 44):
                    p.drawText(QPointF(x + 20, yy + 14), ln)
                    yy += fb.lineSpacing() + 2
                yy += 10
            xx = x + 20
            p.setFont(self.f_meta)
            fm_ = QFontMetrics(self.f_meta)
            p.setPen(QColor(255, 255, 255, 110))
            p.drawText(QPointF(xx, yy + 14), self._tr("FONTES") if c.get("sources") else "")
            xx += 58
            for s_ in c.get("sources", []):
                sw = fm_.horizontalAdvance(s_) + 20
                sr = QRectF(xx, yy, sw, 20)
                ps = QPainterPath()
                ps.addRoundedRect(sr, 10, 10)
                p.fillPath(ps, qc(self.acc, 0.15))
                p.setPen(qc(self.acc, 1.0))
                p.drawText(sr, Qt.AlignmentFlag.AlignCenter, s_)
                xx += sw + 8
            total = yy + 30 - top
        self._panel_max = max(0.0, total - (body.height() - 8))
        p.setClipping(False)
        if self._panel_max > 0:
            th = max(30.0, body.height() * body.height() / (total + 8))
            ty = body.top() + (body.height() - th) * (self.panel_scroll / self._panel_max)
            p.setPen(NO)
            p.setBrush(QColor(255, 255, 255, 50))
            p.drawRoundedRect(QRectF(x + w - 9, ty, 4, th), 2, 2)
        p.restore()

    # =========================================================== tarefas
    def _chip(self, p, x, y, text, color, font=None, h=20):
        font = font or self.f_meta
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 20
        r = QRectF(x, y, w, h)
        pp = QPainterPath()
        pp.addRoundedRect(r, h / 2, h / 2)
        p.fillPath(pp, qc(color, 0.16))
        p.setFont(font)
        p.setPen(qc(color, 1.0))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        return w

    def _tasks_view(self, p, W, H):
        x0, y0, x1, y1 = 28, 84, W - 28, H - 110
        n = [sum(1 for t in self.tasks if t["st"] == i) for i in range(3)]
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 170))
        if getattr(self, "_language", None) == "en-US":
            summary = "%d to do   ·   %d in progress   ·   %d completed      %s"
        else:
            summary = "%d a fazer   ·   %d em andamento   ·   %d concluídas      %s"
        hint = getattr(self, "tasks_hint", "(clique num cartão para avançar)")
        p.drawText(
            QRectF(x0, y0, 600, 30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            summary % (tuple(n) + (hint,))
        )
        bw, bh = 150, 30
        br = QRectF(x1 - bw, y0, bw, bh)
        hov = self._hover == ("task", "new")
        pb = QPainterPath()
        pb.addRoundedRect(br, 15, 15)
        p.fillPath(pb, qc(self.col, 0.95 if hov else 0.75))
        p.setFont(self.f_small)
        p.setPen(QColor(255, 255, 255, 255))
        p.drawText(br, Qt.AlignmentFlag.AlignCenter, self._tr("+  NOVA TAREFA"))
        self._hit(br, self._new_task, ("task", "new"))

        cols = ((self._tr("A FAZER"), 0, (130, 98, 255)), (self._tr("EM ANDAMENTO"), 1, (255, 176, 64)), (self._tr("CONCLUÍDO"), 2, (60, 255, 200)))
        gap = 16
        cw = (x1 - x0 - 2 * gap) / 3.0
        top = y0 + 44
        for ci, (name, st, color) in enumerate(cols):
            cx_ = x0 + ci * (cw + gap)
            area = QRectF(cx_, top, cw, y1 - top)
            pa = QPainterPath()
            pa.addRoundedRect(area, 16, 16)
            p.fillPath(pa, QColor(255, 255, 255, 8))
            p.setBrush(NB)
            p.setPen(QPen(QColor(255, 255, 255, 20), 1))
            p.drawPath(pa)
            p.setPen(NO)
            p.setBrush(qc(color, 1.0))
            p.drawEllipse(QPointF(cx_ + 20, top + 24), 4, 4)
            p.setFont(self.f_small)
            p.setPen(QColor(255, 255, 255, 190))
            p.drawText(QRectF(cx_ + 34, top + 14, cw - 80, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            p.setFont(self.f_mono)
            p.setPen(qc(color, 0.9))
            p.drawText(QRectF(cx_ + cw - 50, top + 14, 36, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(n[st]))
            yy = top + 48
            for ti, t in enumerate(self.tasks):
                if t["st"] != st:
                    continue
                ch = 104.0 if st == 1 else 88.0
                if yy + ch > y1 - 6:
                    break
                r = QRectF(cx_ + 12, yy, cw - 24, ch)
                hid = ("task", ti)
                hv = self._hover == hid
                pcard = QPainterPath()
                pcard.addRoundedRect(r, 14, 14)
                p.fillPath(pcard, QColor(255, 255, 255, 26 if hv else 14))
                p.setBrush(NB)
                p.setPen(QPen(qc(color, 0.55 if hv else 0.18), 1))
                p.drawPath(pcard)
                prc = ((120, 140, 190), (255, 176, 64), (255, 90, 120))[t["pr"]]
                p.setPen(NO)
                p.setBrush(qc(prc, 1.0))
                p.drawEllipse(QPointF(r.x() + 16, r.y() + 20), 4, 4)
                fh = QFontMetrics(self.f_head)
                p.setFont(self.f_head)
                done = st == 2
                p.setPen(QColor(255, 255, 255, 140 if done else 240))
                for li, ln in enumerate(wrap_lines(fh, t["t"], r.width() - 44, 2)):
                    p.drawText(QPointF(r.x() + 30, r.y() + 25 + li * fh.lineSpacing()), ln)
                my = r.y() + 52
                wch = self._chip(p, r.x() + 14, my, self._tr(t["tag"]), color)
                p.setFont(self.f_meta)
                p.setPen(QColor(255, 255, 255, 120))
                p.drawText(QRectF(r.x() + 14 + wch + 10, my, r.width() - wch - 40, 20),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._tr(t["due"]))
                if st == 1:
                    tr = QRectF(r.x() + 14, r.bottom() - 16, r.width() - 28, 5)
                    ptr = QPainterPath()
                    ptr.addRoundedRect(tr, 2.5, 2.5)
                    p.fillPath(ptr, QColor(255, 255, 255, 22))
                    fr = QRectF(tr.x(), tr.y(), max(5.0, tr.width() * t["pg"]), 5)
                    gr = QLinearGradient(fr.left(), 0, fr.right(), 0)
                    gr.setColorAt(0, qc(self.col, 1))
                    gr.setColorAt(1, qc(color, 1))
                    pf = QPainterPath()
                    pf.addRoundedRect(fr, 2.5, 2.5)
                    p.fillPath(pf, gr)
                self._hit(r, (lambda i=ti: self._advance(i)), hid)
                yy += ch + 10

    def _advance(self, i):
        t = self.tasks[i]
        t["st"] = (t["st"] + 1) % 3
        t["pg"] = {0: 0.0, 1: 0.2, 2: 1.0}[t["st"]]
        t["due"] = {0: "Sem prazo", 1: "Hoje", 2: "Feito agora"}[t["st"]]
        self.log.append((time.strftime("%H:%M:%S"), "Tarefa: " + t["t"]))
        self.log = self.log[-14:]

    def _new_task(self):
        k = len(self.tasks) + 1
        self.tasks.append({"t": "Nova tarefa %d" % k, "tag": "Geral", "due": "Sem prazo", "pr": 0, "st": 0, "pg": 0.0})

    # =========================================================== rotinas
    def _routines_view(self, p, W, H):
        x0, y0, x1, y1 = 28, 84, W - 28, H - 110
        n_on = sum(1 for r in self.routines if r["on"])
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 170))
        if getattr(self, "_language", None) == "en-US":
            summary = "%d active routines out of %d      (click a switch to enable or pause)"
        else:
            summary = "%d rotinas ativas de %d      (clique no interruptor para ligar ou pausar)"
        p.drawText(
            QRectF(x0, y0, 700, 30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            summary % (n_on, len(self.routines))
        )
        rh, gap = 62.0, 10.0
        yy = y0 + 42
        for i, r in enumerate(self.routines[:(max(1, int((y1 - y0 - 112) / (rh + gap))) if getattr(self, "live", False) else len(self.routines))]):
            rect = QRectF(x0, yy, x1 - x0, rh)
            self._hit(rect, (lambda i=i: self._open_routine_i(i)), ("routine", i))
            hid = ("routine", i)
            hv = self._hover == hid
            pr = QPainterPath()
            pr.addRoundedRect(rect, 16, 16)
            p.fillPath(pr, QColor(255, 255, 255, 18 if hv else 10))
            p.setBrush(NB)
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawPath(pr)
            dim = 1.0 if r["on"] else 0.4
            p.setPen(NO)
            p.setBrush(qc(r["c"], dim))
            p.drawRoundedRect(QRectF(rect.x() + 10, rect.y() + 14, 4, rh - 28), 2, 2)
            tg = QRectF(rect.x() + 28, rect.center().y() - 11, 42, 22)
            ptg = QPainterPath()
            ptg.addRoundedRect(tg, 11, 11)
            p.fillPath(ptg, qc(self.acc, 0.85) if r["on"] else QColor(255, 255, 255, 30))
            kx = tg.right() - 11 if r["on"] else tg.x() + 11
            p.setBrush(QColor(255, 255, 255, 255 if r["on"] else 150))
            p.drawEllipse(QPointF(kx, tg.center().y()), 8, 8)
            self._hit(tg.adjusted(-6, -6, 6, 6), (lambda i=i: self._toggle(i)), ("routine", i))
            nx = rect.x() + 90
            p.setFont(self.f_head)
            p.setPen(QColor(255, 255, 255, int(245 * dim)))
            p.drawText(QRectF(nx, rect.y() + 10, rect.width() * 0.42, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, r["n"])
            p.setFont(self.f_meta)
            p.setPen(QColor(255, 255, 255, int(130 * dim)))
            p.drawText(QRectF(nx, rect.y() + 33, rect.width() * 0.42, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, r["d"])
            sx_ = rect.x() + rect.width() * 0.50
            wch = self._chip(p, sx_, rect.y() + 12, self._tr(r.get("chip") or sched_label(r["days"])), r["c"] if r["on"] else (140, 140, 160))
            p.setFont(self.f_mono)
            p.setPen(QColor(255, 255, 255, int(200 * dim)))
            p.drawText(QRectF(sx_ + wch + 10, rect.y() + 12, 70, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       (r.get("hm") or "%02d:%02d" % (r["h"], r["m"])))
            p.setFont(self.f_meta)
            p.setPen(QColor(255, 255, 255, 110))
            p.drawText(QRectF(sx_, rect.y() + 36, rect.width() * 0.2, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "última: " + r["last"])
            nxt = self._tr(r.get("next") or next_run(r)) if r["on"] else self._tr("pausada")
            p.setFont(self.f_body)
            p.setPen(qc(self.acc, 0.95 if r["on"] else 0.35))
            p.drawText(QRectF(rect.right() - 230, rect.y(), 214, rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       (self._tr("próxima  ") + nxt) if r["on"] else self._tr("pausada"))
            yy += rh + gap

        # 24 h timeline
        ty = yy + 6
        th = max(70.0, y1 - ty)
        card = QRectF(x0, ty, x1 - x0, th)
        pc = QPainterPath()
        pc.addRoundedRect(card, 16, 16)
        p.fillPath(pc, QColor(255, 255, 255, 8))
        p.setBrush(NB)
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.drawPath(pc)
        p.setFont(self.f_small)
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(x0 + 16, ty + 10, 300, 16), Qt.AlignmentFlag.AlignLeft, self._tr("HOJE · 24 HORAS"))
        ax0, ax1 = x0 + 30, x1 - 30
        ay = ty + th - 28
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(QPointF(ax0, ay), QPointF(ax1, ay))
        p.setFont(self.f_meta)
        for hh in range(0, 25, 3):
            xx = ax0 + (ax1 - ax0) * hh / 24.0
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.drawLine(QPointF(xx, ay - 4), QPointF(xx, ay + 4))
            p.setPen(QColor(255, 255, 255, 100))
            p.drawText(QRectF(xx - 20, ay + 6, 40, 14), Qt.AlignmentFlag.AlignCenter, "%02dh" % (hh % 24))
        wd = time.localtime().tm_wday
        for r in self.routines:
            if r.get("h") is None or wd not in r["days"] or (getattr(self, "live", False) and not r["on"]):
                continue
            xx = ax0 + (ax1 - ax0) * (r["h"] + r["m"] / 60.0) / 24.0
            p.setPen(NO)
            p.setBrush(qc(r["c"], 0.25 if r["on"] else 0.08))
            p.drawEllipse(QPointF(xx, ay - 18), 12, 12)
            p.setBrush(qc(r["c"], 1.0 if r["on"] else 0.35))
            p.drawEllipse(QPointF(xx, ay - 18), 5, 5)
            p.setFont(self.f_meta)
            p.setPen(QColor(255, 255, 255, 200 if r["on"] else 90))
            p.drawText(QRectF(xx - 70, ay - 52, 140, 14), Qt.AlignmentFlag.AlignCenter, r["n"])
        lt = time.localtime()
        nx = ax0 + (ax1 - ax0) * (lt.tm_hour + lt.tm_min / 60.0) / 24.0
        p.setPen(QPen(qc(self.acc, 0.9), 1.5))
        p.drawLine(QPointF(nx, ay - 34), QPointF(nx, ay + 4))
        p.setPen(NO)
        p.setBrush(qc(self.acc, 1.0))
        p.drawEllipse(QPointF(nx, ay - 34), 3.5, 3.5)

    def _open_routine_i(self, i):
        pass

    def _toggle(self, i):
        r = self.routines[i]
        r["on"] = not r["on"]
        self.log.append((time.strftime("%H:%M:%S"), ("Rotina ligada: " if r["on"] else "Rotina pausada: ") + r["n"]))
        self.log = self.log[-14:]


NO = Qt.PenStyle.NoPen
NB = Qt.BrushStyle.NoBrush
DAYN = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def wrap_lines(fm, text, width, max_lines=None):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if fm.horizontalAdvance(t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        rest = " ".join(lines[max_lines - 1:])
        lines = lines[:max_lines - 1] + [fm.elidedText(rest, Qt.TextElideMode.ElideRight, int(width))]
    return lines


def next_run(r):
    now = time.localtime()
    for add in range(8):
        wd = (now.tm_wday + add) % 7
        if wd not in r["days"]:
            continue
        if add == 0 and (now.tm_hour, now.tm_min) >= (r["h"], r["m"]):
            continue
        lab = "hoje" if add == 0 else "amanhã" if add == 1 else DAYN[wd].lower()
        return "%s %02d:%02d" % (lab, r["h"], r["m"])
    return "-"


def sched_label(days):
    d = sorted(days)
    if len(d) == 7:
        return "Todos os dias"
    if d == [0, 1, 2, 3, 4]:
        return "Seg a Sex"
    return ", ".join(DAYN[i] for i in d)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = NovoVisual()
    w.show()
    sys.exit(app.exec())

