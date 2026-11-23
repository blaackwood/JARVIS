"""Extras do novo visual: esfera holografica, topo, abas Controles e Config."""
import math
import time

from core.i18n import tr

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QRadialGradient

NO = Qt.PenStyle.NoPen
NB = Qt.BrushStyle.NoBrush
AL = Qt.AlignmentFlag
ROUND = Qt.PenCapStyle.RoundCap
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
TABS = (("home", "INÍCIO"), ("tasks", "TAREFAS"), ("routines", "ROTINAS"),
        ("controls", "CONTROLES"), ("settings", "CONFIG"))
ONOFF = ["Desligado", "Ligado"]
RED = (255, 100, 130)


def qc(c, a=1.0):
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(max(0.0, min(1.0, a)) * 255))


def mk_font(size, bold=False, spacing=0.0, family="Segoe UI"):
    f = QFont(family, size)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def mixc(a, b, m):
    return (a[0] + (b[0] - a[0]) * m, a[1] + (b[1] - a[1]) * m, a[2] + (b[2] - a[2]) * m)


class HoloMixin:
    def _tr(self, text):
        """Translate a fixed interface label without translating user content."""
        return tr(text, getattr(self, "_language", None))

    # ------------------------------------------------------------ setup
    def init_extras(self):
        self.muted = False
        self.orb_style = "holo"
        self.f_tab = mk_font(8, True, 1.6)
        self.f_sub = mk_font(8, True, 1.4)
        self.f_date = mk_font(8, True, 1.6)
        self.f_clock = mk_font(14, True)
        self.f_ctl = mk_font(10, True)
        self.f_big = mk_font(14, True)
        rng = np.random.default_rng(7)
        n = 1500
        i = np.arange(n) + 0.5
        phi = np.arccos(1 - 2 * i / n)
        th = math.pi * (1 + 5 ** 0.5) * i
        P = np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)
        P = P + rng.normal(0, 0.035, (n, 3))
        P /= np.linalg.norm(P, axis=1)[:, None]
        shell = rng.choice(3, n, p=[0.5, 0.3, 0.2])
        self.h_u = P
        self.h_shell = shell
        self.h_rad = np.array([1.0, 0.80, 0.58])[shell] * (1 + rng.normal(0, 0.012, n))
        self.h_ph = rng.random(n) * 6.28
        self.h_len = 0.03 + 0.20 * rng.random(n) ** 2
        self.h_dir = np.array([1.0, -1.0, 1.0])[shell]
        self.h_spd = np.array([0.20, 0.14, 0.34])[shell]
        self.cflags = {"brief": True, "wake": True, "ptt": False}
        self.set_sel = 0
        self.sets = [
            {"t": "Controle remoto", "d": "Controle o Jarvis pelo celular ou por outro computador.",
             "rows": [{"l": "Acesso remoto", "o": ONOFF, "i": 0},
                      {"l": "Código de pareamento", "o": ["4821-7730"], "i": 0}]},
            {"t": "Atalho na área de trabalho", "d": "Cria um ícone para abrir o Jarvis com um clique.",
             "rows": [{"l": "Atalho", "o": ["Criar atalho", "Atalho criado ✓"], "i": 0}]},
            {"t": "Iniciar com o Windows", "d": "Abre o Jarvis sozinho quando o computador liga.",
             "rows": [{"l": "Início automático", "o": ONOFF, "i": 1}]},
            {"t": "Personalizar assistente", "d": "Nome, voz e jeito de falar do assistente.",
             "rows": [{"l": "Nome", "o": ["Jarvis", "Friday", "Edith"], "i": 0},
                      {"l": "Voz", "o": ["Masculina", "Feminina"], "i": 0},
                      {"l": "Idioma", "o": ["Português (BR)", "English"], "i": 0},
                      {"l": "Velocidade da fala", "o": ["Lenta", "Normal", "Rápida"], "i": 1}]},
            {"t": "Dispositivos de áudio", "d": "Escolha o microfone e a saída de som.",
             "rows": [{"l": "Microfone", "o": ["Microfone padrão", "Headset USB"], "i": 0},
                      {"l": "Saída de som", "o": ["Alto-falantes", "Fones de ouvido"], "i": 0},
                      {"l": "Volume da voz", "o": ["50%", "75%", "100%"], "i": 1}]},
            {"t": "Memória", "d": "O que o Jarvis guarda entre as conversas.",
             "rows": [{"l": "Memória de longo prazo", "o": ONOFF, "i": 1},
                      {"l": "Lembrar conversas por", "o": ["7 dias", "30 dias", "Sempre"], "i": 1},
                      {"l": "Limpar memória", "o": ["Limpar agora", "Memória limpa ✓"], "i": 0}]},
            {"t": "Plugins", "d": "Ligue ou desligue as habilidades extras.",
             "rows": [{"l": "Pesquisa na web", "o": ONOFF, "i": 1},
                      {"l": "Notícias", "o": ONOFF, "i": 1},
                      {"l": "Agenda", "o": ONOFF, "i": 1},
                      {"l": "Controle do PC", "o": ONOFF, "i": 0}]},
            {"t": "Config. de plugins", "d": "Ajustes finos de cada plugin.",
             "rows": [{"l": "Fonte de notícias", "o": ["Google Notícias", "Agência Brasil"], "i": 0},
                      {"l": "Resultados por pesquisa", "o": ["3", "5", "8"], "i": 1}]},
            {"t": "Motor e provedores", "d": "Qual tecnologia responde, ouve e fala.",
             "rows": [{"l": "Modelo de linguagem", "o": ["Claude", "Local"], "i": 0},
                      {"l": "Reconhecimento de voz", "o": ["Online", "Offline"], "i": 0},
                      {"l": "Síntese de voz", "o": ["Neural", "Sistema"], "i": 0}]},
        ]

    # ---------------------------------------------------------- actions
    def _log(self, tx):
        self.log.append((time.strftime("%H:%M:%S"), tx))
        self.log = self.log[-14:]

    def do_mute(self):
        self.muted = not self.muted
        self._log("Microfone mudo" if self.muted else "Microfone ligado")
        if self.muted and self.state == "listening":
            self._set("idle")

    def do_stop(self):
        self.auto = False
        if self.state == "idle":
            self._log("Nada para interromper")
        else:
            self._log("Fala interrompida")
            self._set("idle")

    def do_fs(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def do_sleep(self):
        self.auto = False
        self._set("idle")
        self._log("Assistente em espera")
        self._goto("home")

    def do_style(self):
        self.orb_style = "neural" if self.orb_style == "holo" else "holo"
        self._log("Esfera: " + ("holograma" if self.orb_style == "holo" else "núcleo neural"))

    def flip(self, k, name):
        self.cflags[k] = not self.cflags[k]
        self._log("%s: %s" % (name, "ligado" if self.cflags[k] else "desligado"))

    def cycle(self, row):
        row["i"] = (row["i"] + 1) % len(row["o"])

    # --------------------------------------------------------- widgets
    def _switch(self, p, x, y, on, color):
        r = QRectF(x, y, 42, 22)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        p.fillPath(path, qc(color, 0.85) if on else QColor(255, 255, 255, 30))
        p.setPen(NO)
        p.setBrush(QColor(255, 255, 255, 245) if on else QColor(255, 255, 255, 150))
        p.drawEllipse(QPointF(x + (31 if on else 11), y + 11), 8, 8)
        p.setBrush(NB)

    def _glyph(self, p, key, cx, cy, color, s=1.0, muted=False):
        pen = QPen(qc(color, 1.0), 1.8 * s)
        pen.setCapStyle(ROUND)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(NB)
        if key == "mute":
            p.drawRoundedRect(QRectF(cx - 3.5 * s, cy - 8 * s, 7 * s, 11 * s), 3.5 * s, 3.5 * s)
            p.drawArc(QRectF(cx - 7 * s, cy - 6 * s, 14 * s, 12 * s), 200 * 16, 140 * 16)
            p.drawLine(QPointF(cx, cy + 6 * s), QPointF(cx, cy + 9 * s))
            if muted:
                p.setPen(QPen(qc(RED, 1.0), 2.2 * s))
                p.drawLine(QPointF(cx - 8 * s, cy - 8 * s), QPointF(cx + 8 * s, cy + 9 * s))
        elif key == "stop":
            p.setBrush(qc(color, 0.35))
            p.drawRoundedRect(QRectF(cx - 6 * s, cy - 6 * s, 12 * s, 12 * s), 2.5 * s, 2.5 * s)
        elif key == "fs":
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                p.drawLine(QPointF(cx + sx * 8 * s, cy + sy * 8 * s), QPointF(cx + sx * 8 * s, cy + sy * 3.5 * s))
                p.drawLine(QPointF(cx + sx * 8 * s, cy + sy * 8 * s), QPointF(cx + sx * 3.5 * s, cy + sy * 8 * s))
        elif key == "sleep":
            a = QPainterPath()
            a.addEllipse(QPointF(cx, cy), 7 * s, 7 * s)
            b = QPainterPath()
            b.addEllipse(QPointF(cx + 4 * s, cy - 3 * s), 6 * s, 6 * s)
            p.drawPath(a.subtracted(b))
        elif key == "brief":
            p.drawEllipse(QPointF(cx, cy), 3.6 * s, 3.6 * s)
            for k in range(8):
                an = k * math.pi / 4
                p.drawLine(QPointF(cx + math.cos(an) * 6.5 * s, cy + math.sin(an) * 6.5 * s),
                           QPointF(cx + math.cos(an) * 9 * s, cy + math.sin(an) * 9 * s))
        elif key == "wake":
            for dx, hh in ((-6, 4), (-2, 10), (2, 14), (6, 7)):
                p.drawLine(QPointF(cx + dx * s, cy - hh * s / 2), QPointF(cx + dx * s, cy + hh * s / 2))
        elif key == "ptt":
            p.drawEllipse(QPointF(cx, cy), 8 * s, 8 * s)
            p.setBrush(qc(color, 0.9))
            p.drawEllipse(QPointF(cx, cy), 2.8 * s, 2.8 * s)
        else:
            p.drawEllipse(QPointF(cx, cy), 8 * s, 8 * s)
            p.drawEllipse(QPointF(cx, cy), 4 * s, 4 * s)
        p.setBrush(NB)

    def _icon_btn(self, p, x, y, key, action, color, active=False):
        r = QRectF(x, y, 34, 34)
        hid = ("btn", key)
        hov = self._hover == hid
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, qc(color, 0.20) if active else QColor(255, 255, 255, 26 if hov else 11))
        p.setBrush(NB)
        p.setPen(QPen(qc(color, 0.8) if active else QColor(255, 255, 255, 40 if hov else 26), 1))
        p.drawPath(path)
        self._glyph(p, key, r.center().x(), r.center().y(), color, 0.95, muted=(key == "mute" and self.muted))
        self._hit(r, action, hid)

    # ---------------------------------------------------------- topbar
    def _topbar(self, p, W):
        c = QPointF(44, 40)
        poly = QPainterPath()
        for i in range(6):
            a = math.radians(60 * i - 30)
            q = QPointF(c.x() + 12 * math.cos(a), c.y() + 12 * math.sin(a))
            poly.moveTo(q) if i == 0 else poly.lineTo(q)
        poly.closeSubpath()
        p.setBrush(NB)
        p.setPen(QPen(qc(self.col, 0.95), 2))
        p.drawPath(poly)
        p.setPen(NO)
        p.setBrush(qc(self.acc, 0.95))
        p.drawEllipse(c, 3.2, 3.2)
        p.setBrush(NB)
        p.setFont(self.f_small)
        p.setPen(QColor(255, 255, 255, 225))
        p.drawText(QRectF(66, 24, 200, 16), AL.AlignLeft, getattr(self, "name", "JARVIS"))
        # estado: bolinha pulsando + texto legivel
        col = RED if self.muted else self.acc
        label = self._tr("MUDO" if self.muted else self.STATES[self.state][0])
        pulse = 0.6 + 0.4 * math.sin(self.t * 4)
        p.setPen(NO)
        p.setBrush(qc(col, pulse))
        p.drawEllipse(QPointF(70, 52), 3.6, 3.6)
        p.setBrush(NB)
        p.setFont(self.f_sub)
        p.setPen(qc(col, 1.0))
        p.drawText(QRectF(80, 44, 160, 16), AL.AlignLeft | AL.AlignVCenter, self._tr(label))
        # direita: botoes + data/hora
        x_fs = W - 28 - 34
        x_stop = x_fs - 42
        x_mute = x_stop - 42
        self._icon_btn(p, x_mute, 23, "mute", self.do_mute, RED if self.muted else (60, 255, 200), self.muted)
        self._icon_btn(p, x_stop, 23, "stop", self.do_stop, (255, 130, 150))
        self._icon_btn(p, x_fs, 23, "fs", self.do_fs, (176, 156, 255), self.isFullScreen())
        lt = time.localtime()
        dx = x_mute - 14 - 96
        p.setFont(self.f_date)
        p.setPen(qc(self.acc, 0.95))
        day_names, month_names = DIAS, MESES
        if getattr(self, "_language", None) == "en-US":
            day_names = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
            month_names = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
        p.drawText(
            QRectF(dx, 18, 96, 16), AL.AlignRight | AL.AlignVCenter,
            "%s · %02d %s" % (day_names[lt.tm_wday], lt.tm_mday, month_names[lt.tm_mon - 1])
        )
        p.setFont(self.f_clock)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(dx, 34, 96, 22), AL.AlignRight | AL.AlignVCenter, time.strftime("%H:%M"))
        self._tabs_zone = (232.0, dx - 16)

    def _tabs(self, p, W):
        left, right = self._tabs_zone
        avail = right - left
        tw = min(112.0, (avail - 20) / 5.0)
        x0 = left + (avail - (5 * tw + 20)) / 2.0
        n_open = sum(1 for t in self.tasks if t["st"] < 2)
        n_on = sum(1 for r in self.routines if r["on"])
        badges = {"tasks": str(n_open), "routines": str(n_on)}
        for i, (key, label) in enumerate(TABS):
            badge = badges.get(key, "")
            r = QRectF(x0 + i * (tw + 5), 24, tw, 32)
            act = self.tab == key
            hov = self._hover == ("tab", key)
            path = QPainterPath()
            path.addRoundedRect(r, 16, 16)
            p.fillPath(path, qc(self.col, 0.24) if act else QColor(255, 255, 255, 22 if hov else 9))
            p.setBrush(NB)
            p.setPen(QPen(qc(self.acc, 0.75) if act else QColor(255, 255, 255, 22), 1))
            p.drawPath(path)
            p.setFont(self.f_tab)
            p.setPen(QColor(255, 255, 255, 255 if act else 160))
            off = 9 if badge else 0
            p.drawText(QRectF(r.x() - off, r.y(), r.width(), r.height()), AL.AlignCenter, self._tr(label))
            if badge:
                bc = QPointF(r.right() - 19, r.center().y())
                p.setPen(NO)
                p.setBrush(qc(self.acc, 0.9 if act else 0.35))
                p.drawEllipse(bc, 9, 9)
                p.setBrush(NB)
                p.setFont(mk_font(8, True))
                p.setPen(QColor(10, 10, 20, 255) if act else QColor(255, 255, 255, 220))
                p.drawText(QRectF(bc.x() - 9, bc.y() - 9, 18, 18), AL.AlignCenter, badge)
            self._hit(r, lambda k=key: self._goto(k), ("tab", key))

    # -------------------------------------------------------------- orb
    def _orb(self, p, cx, cy, R):
        if self.orb_style == "neural":
            self._orb_neural(p, cx, cy, R)
        else:
            self._orb_holo(p, cx, cy, R)

    def _orb_holo(self, p, cx, cy, R):
        t, amp, think = self.t, self.amp, self.think_v
        col, acc = self.col, self.acc
        C = QPointF(cx, cy)
        g = QRadialGradient(C, R * 2.4)
        g.setColorAt(0.0, qc(col, 0.20 + 0.25 * amp))
        g.setColorAt(0.55, qc(col, 0.05))
        g.setColorAt(1.0, qc(col, 0.0))
        p.setPen(NO)
        p.setBrush(g)
        p.drawEllipse(C, R * 2.4, R * 2.4)
        p.setBrush(NB)
        sg = max(0.8, R / 180.0)

        def arc(r, start, span, w, c, a, cap=Qt.PenCapStyle.FlatCap):
            pen = QPen(qc(c, a), w)
            pen.setCapStyle(cap)
            p.setPen(pen)
            p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(start * 16), int(span * 16))

        # ---- aneis HUD (atras dos fragmentos)
        p.setBrush(NB)
        a0 = t * 7.0 * (1 + 2 * amp)
        segs = (52, 30, 24, 58, 20, 36, 44, 26)
        gap = (360 - sum(segs)) / len(segs)
        a = a0
        for L in segs:
            arc(R * 1.28, a, L, R * 0.13, col, 0.10)
            arc(R * 1.28, a, L, R * 0.06, col, 0.55)
            arc(R * 1.28, a, L, R * 0.02, acc, 0.55)
            a += L + gap
        for w, al in ((6.0, 0.10), (1.6, 0.55)):
            p.setPen(QPen(qc(acc, al), w * sg))
            p.drawEllipse(C, R * 1.16, R * 1.16)
        p.setPen(QPen(qc(col, 0.20), 1))
        p.drawEllipse(C, R * 1.50, R * 1.50)
        rot = -t * 5.0
        short, long_ = [], []
        for i in range(90):
            an = math.radians(i * 4 + rot)
            ca, sa = math.cos(an), math.sin(an)
            ln = 0.075 if i % 5 == 0 else 0.035
            seg = QLineF(cx + ca * R * 1.40, cy + sa * R * 1.40, cx + ca * R * (1.40 + ln), cy + sa * R * (1.40 + ln))
            (long_ if i % 5 == 0 else short).append(seg)
        p.setPen(QPen(qc(acc, 0.28), 1.0 * sg))
        p.drawLines(short)
        p.setPen(QPen(qc(acc, 0.60), 1.6 * sg))
        p.drawLines(long_)
        yel = (255, 205, 90)
        span = 46 + 120 * think + 40 * amp
        st = -t * 42.0
        arc(R * 1.22, st, span, R * 0.05, yel, 0.14, ROUND)
        arc(R * 1.22, st, span, R * 0.022, yel, 0.95, ROUND)
        p.setPen(NO)
        p.setBrush(qc(yel, 0.95))
        for k in range(4):
            an = math.radians(st + span + 7 + k * 6)
            p.drawEllipse(QPointF(cx + math.cos(an) * R * 1.22, cy + math.sin(an) * R * 1.22), 2.0 * sg, 2.0 * sg)
        p.setBrush(NB)
        r0 = R * 1.56
        for i in range(96):
            an = -a0 * 0.01 + i * (2 * math.pi / 96)
            v = float(self.spec[i])
            r1 = r0 + R * (0.03 + 0.24 * v)
            pen = QPen(qc(acc, 0.28 + 0.65 * min(1.0, v * 1.8)), 2.4 * sg if i % 2 else 1.5 * sg)
            pen.setCapStyle(ROUND)
            p.setPen(pen)
            p.drawLine(QPointF(cx + math.cos(an) * r0, cy + math.sin(an) * r0),
                       QPointF(cx + math.cos(an) * r1, cy + math.sin(an) * r1))

        # ---- esfera de fragmentos
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setBrush(NB)
        for k in range(4):
            wk = abs(math.cos(t * 0.25 + k * math.pi / 4))
            p.setPen(QPen(qc(col, 0.09), 1))
            p.drawEllipse(QRectF(cx - R * wk, cy - R, 2 * R * wk, 2 * R))
        u = self.h_u
        ang0 = t * self.h_spd * (1 + 2.0 * think) * self.h_dir
        tilt = 0.40 + 0.08 * math.sin(t * 0.21)
        cb, sb = math.cos(tilt), math.sin(tilt)
        disp = self.h_rad * (1 + amp * 0.13 * np.sin(self.h_ph + t * 5.5 + u[:, 1] * 5.0)
                             + 0.012 * math.sin(t * 1.2))

        def proj(ang):
            ca, sa = np.cos(ang), np.sin(ang)
            x = u[:, 0] * ca + u[:, 2] * sa
            z = -u[:, 0] * sa + u[:, 2] * ca
            y2 = u[:, 1] * cb - z * sb
            z2 = u[:, 1] * sb + z * cb
            f = 3.8 / (3.8 - z2 * disp)
            return cx + x * disp * R * f, cy + y2 * disp * R * f, z2 * disp

        xh, yh, zh = proj(ang0)
        xt, yt, _ = proj(ang0 - self.h_dir * self.h_len * (1 + 1.5 * amp))
        bk = np.digitize(np.clip((zh + 1.0) / 2.0, 0, 1), [0.30, 0.55, 0.78])
        key = self.h_shell * 4 + bk
        order = np.argsort(key, kind="stable")
        offs = np.concatenate([[0], np.cumsum(np.bincount(key, minlength=12))]).tolist()
        lines = [QLineF(a_, b_, c_, d_) for a_, b_, c_, d_ in
                 zip(xt[order].tolist(), yt[order].tolist(), xh[order].tolist(), yh[order].tolist())]
        scol = (mixc(col, acc, 0.25), mixc(col, acc, 0.65), mixc(acc, (255, 255, 255), 0.45))
        AA = (0.10, 0.24, 0.50, 0.88)
        WW = (0.9, 1.2, 1.6, 2.1)

        def draw_group(b):
            for s in range(3):
                i0, i1 = offs[s * 4 + b], offs[s * 4 + b + 1]
                if i1 > i0:
                    pen = QPen(qc(scol[s], AA[b]), WW[b] * sg)
                    pen.setCapStyle(ROUND)
                    p.setPen(pen)
                    p.drawLines(lines[i0:i1])

        draw_group(0)
        draw_group(1)
        cr = R * (0.44 + 0.16 * amp + 0.03 * math.sin(t * 2.0))
        g2 = QRadialGradient(C, cr)
        g2.setColorAt(0.0, QColor(255, 255, 255, 235))
        g2.setColorAt(0.22, qc(acc, 0.85))
        g2.setColorAt(0.60, qc(col, 0.28))
        g2.setColorAt(1.0, qc(col, 0.0))
        p.setPen(NO)
        p.setBrush(g2)
        p.drawEllipse(C, cr, cr)
        p.setBrush(NB)
        for k in range(3):
            an = t * (0.6 + 0.25 * k) * (-1 if k == 1 else 1) + k * 1.1
            rx = R * 0.46
            ry = abs(math.cos(an)) * rx
            p.save()
            p.translate(cx, cy)
            p.rotate(k * 60 + 20 * math.sin(t * 0.3 + k))
            p.setPen(QPen(qc(acc, 0.22), 5 * sg))
            p.drawEllipse(QRectF(-rx, -ry, 2 * rx, 2 * ry))
            p.setPen(QPen(qc(acc, 0.65), 1.4 * sg))
            p.drawEllipse(QRectF(-rx, -ry, 2 * rx, 2 * ry))
            p.restore()
        draw_group(2)
        draw_group(3)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # --------------------------------------------------------- controles
    def _ctl_items(self):
        fl = self.cflags
        return [
            {"k": "mute", "t": "Microfone", "d": "Desligado, o Jarvis para de escutar", "kind": "sw",
             "on": not self.muted, "c": (60, 255, 200), "fn": self.do_mute},
            {"k": "stop", "t": "Interromper", "d": "Para a fala e volta ao repouso", "kind": "act",
             "lbl": "PARAR", "c": (255, 130, 150), "fn": self.do_stop},
            {"k": "fs", "t": "Tela cheia", "d": "Alterna o modo tela cheia (F11)", "kind": "act",
             "lbl": "SAIR" if self.isFullScreen() else "ENTRAR", "c": (176, 156, 255), "fn": self.do_fs},
            {"k": "sleep", "t": "Dormir agora", "d": "Coloca o assistente em espera", "kind": "act",
             "lbl": "DORMIR", "c": (120, 190, 255), "fn": self.do_sleep},
            {"k": "brief", "t": "Resumo da manhã", "d": "Fala notícias e agenda ao acordar", "kind": "sw",
             "on": fl["brief"], "c": (255, 176, 64), "fn": lambda: self.flip("brief", "Resumo da manhã")},
            {"k": "wake", "t": "Palavra de ativação", "d": "Responde quando ouvir o nome dele", "kind": "sw",
             "on": fl["wake"], "c": (60, 255, 200), "fn": lambda: self.flip("wake", "Palavra de ativação")},
            {"k": "ptt", "t": "Apertar para falar", "d": "Só escuta com a tecla pressionada", "kind": "sw",
             "on": fl["ptt"], "c": (176, 156, 255), "fn": lambda: self.flip("ptt", "Apertar para falar")},
            {"k": "style", "t": "Visual da esfera", "d": "Alterna holograma e núcleo neural", "kind": "act",
             "lbl": "HOLOGRAMA" if self.orb_style == "holo" else "NEURAL", "c": (255, 176, 64),
             "fn": self.do_style},
        ]

    def _controls_view(self, p, W, H, items=None, title=None):
        x0, y0 = 28, 84
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(x0, y0, 700, 30), AL.AlignLeft | AL.AlignVCenter,
                   self._tr(title or "Controles rápidos do assistente (clique para alternar)"))
        cols = 4 if W >= 1100 else 3
        gap = 14.0
        cw = (W - 56 - gap * (cols - 1)) / cols
        ch = 104.0
        for i, it in enumerate(items if items is not None else self._ctl_items()):
            r = QRectF(x0 + (i % cols) * (cw + gap), y0 + 40 + (i // cols) * (ch + gap), cw, ch)
            on = it["kind"] == "sw" and it["on"]
            c = it["c"]
            hov = self._hover == ("ctl", it["k"])
            path = QPainterPath()
            path.addRoundedRect(r, 16, 16)
            p.fillPath(path, QColor(255, 255, 255, 20 if hov else 10))
            if on:
                p.fillPath(path, qc(c, 0.10))
            p.setBrush(NB)
            p.setPen(QPen(qc(c, 0.55) if on else QColor(255, 255, 255, 26), 1))
            p.drawPath(path)
            ic = QPointF(r.x() + 38, r.y() + 36)
            p.setPen(NO)
            p.setBrush(qc(c, 0.16))
            p.drawEllipse(ic, 21, 21)
            p.setBrush(NB)
            self._glyph(p, it["k"] if it["k"] != "style" else "x", ic.x(), ic.y(), c, 1.0,
                        muted=(it["k"] == "mute" and self.muted))
            p.setFont(self.f_ctl)
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(QRectF(r.x() + 70, r.y() + 16, cw - 84, 20), AL.AlignLeft | AL.AlignVCenter, self._tr(it["t"]))
            p.setFont(self.f_meta)
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(QRectF(r.x() + 70, r.y() + 38, cw - 84, 30), AL.AlignLeft | AL.AlignTop
                       | Qt.TextFlag.TextWordWrap, self._tr(it["d"]))
            if it["kind"] == "sw":
                self._switch(p, r.right() - 16 - 42, r.bottom() - 32, on, c)
                p.setFont(mk_font(8, True, 1.4))
                p.setPen(qc(c, 0.95) if on else QColor(255, 255, 255, 110))
                p.drawText(QRectF(r.x() + 70, r.bottom() - 32, 90, 22), AL.AlignLeft | AL.AlignVCenter,
                           self._tr("LIGADO" if on else "DESLIGADO"))
            else:
                p.setFont(mk_font(8, True, 1.4))
                fm = QFontMetrics(p.font())
                tw = fm.horizontalAdvance(it["lbl"]) + 30
                cr = QRectF(r.right() - 16 - tw, r.bottom() - 34, tw, 24)
                cp = QPainterPath()
                cp.addRoundedRect(cr, 12, 12)
                p.fillPath(cp, qc(c, 0.18))
                p.setBrush(NB)
                p.setPen(QPen(qc(c, 0.6), 1))
                p.drawPath(cp)
                p.setPen(qc(c, 1.0))
                p.drawText(cr, AL.AlignCenter, button_label)
            self._hit(r, it["fn"], ("ctl", it["k"]))

    # ----------------------------------------------------- configuracoes
    def _settings_view(self, p, W, H):
        x0, y0 = 28, 84
        lw = min(310.0, W * 0.30)
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(x0, y0, 700, 30), AL.AlignLeft | AL.AlignVCenter,
                   self._tr("Configurações do Jarvis"))
        ty = y0 + 36
        avail = H - 110 - ty
        n = len(self.sets)
        ih = max(32.0, min(46.0, avail / n - 6))
        for i, s in enumerate(self.sets):
            r = QRectF(x0, ty + i * (ih + 6), lw, ih)
            act = i == self.set_sel
            hov = self._hover == ("set", i)
            path = QPainterPath()
            path.addRoundedRect(r, 12, 12)
            p.fillPath(path, qc(self.col, 0.22) if act else QColor(255, 255, 255, 20 if hov else 9))
            p.setBrush(NB)
            p.setPen(QPen(qc(self.acc, 0.7) if act else QColor(255, 255, 255, 22), 1))
            p.drawPath(path)
            p.setFont(self.f_body)
            p.setPen(QColor(255, 255, 255, 255 if act else 190))
            p.drawText(QRectF(r.x() + 16, r.y(), lw - 70, ih), AL.AlignLeft | AL.AlignVCenter,
                       QFontMetrics(self.f_body).elidedText(self._tr(s["t"]), Qt.TextElideMode.ElideRight, int(lw - 74)))
            row0 = s["rows"][0]
            tag = ("ON" if row0["i"] else "OFF") if row0["o"] == ONOFF else "›"
            on = tag == "ON"
            p.setFont(mk_font(8, True, 1.4))
            p.setPen(qc((60, 255, 200), 0.95) if on else QColor(255, 255, 255, 110))
            p.drawText(QRectF(r.right() - 50, r.y(), 36, ih), AL.AlignRight | AL.AlignVCenter, self._tr(tag))
            self._hit(r, lambda k=i: setattr(self, "set_sel", k), ("set", i))
        dx = x0 + lw + 18
        dw = W - 28 - dx
        dh = H - 110 - ty
        s = self.sets[self.set_sel]
        r = QRectF(dx, ty, dw, dh)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.fillPath(path, QColor(255, 255, 255, 10))
        p.setBrush(NB)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.drawPath(path)
        p.setPen(QPen(qc(self.acc, 0.8), 2))
        p.drawLine(QPointF(dx + 22, ty + 0.5), QPointF(dx + 62, ty + 0.5))
        p.setFont(self.f_big)
        p.setPen(QColor(255, 255, 255, 245))
        p.drawText(QRectF(dx + 22, ty + 18, dw - 44, 26), AL.AlignLeft | AL.AlignVCenter, self._tr(s["t"]))
        p.setFont(self.f_body)
        p.setPen(QColor(255, 255, 255, 135))
        p.drawText(QRectF(dx + 22, ty + 48, dw - 44, 22), AL.AlignLeft | AL.AlignVCenter, self._tr(s["d"]))
        ry = ty + 88
        for j, row in enumerate(s["rows"]):
            rr = QRectF(dx + 22, ry + j * 62, dw - 44, 52)
            hid = ("row", self.set_sel, j)
            hov = self._hover == hid
            rp = QPainterPath()
            rp.addRoundedRect(rr, 12, 12)
            p.fillPath(rp, QColor(255, 255, 255, 18 if hov else 9))
            p.setFont(self.f_body)
            p.setPen(QColor(255, 255, 255, 220))
            p.drawText(QRectF(rr.x() + 18, rr.y(), rr.width() * 0.5, rr.height()), AL.AlignLeft | AL.AlignVCenter,
                       self._tr(row["l"]))
            val = self._tr(row["o"][row["i"]])
            if row["o"] == ONOFF:
                self._switch(p, rr.right() - 18 - 42, rr.y() + 15, bool(row["i"]), (60, 255, 200))
            elif len(row["o"]) == 1:
                p.setFont(self.f_mono)
                p.setPen(qc(self.acc, 0.95))
                p.drawText(QRectF(rr.x(), rr.y(), rr.width() - 18, rr.height()), AL.AlignRight | AL.AlignVCenter, val)
            else:
                p.setFont(mk_font(9, True))
                tw = QFontMetrics(p.font()).horizontalAdvance(val) + 36
                cr = QRectF(rr.right() - 14 - tw, rr.y() + 13, tw, 26)
                cp = QPainterPath()
                cp.addRoundedRect(cr, 13, 13)
                p.fillPath(cp, qc(self.acc, 0.15))
                p.setBrush(NB)
                p.setPen(QPen(qc(self.acc, 0.55), 1))
                p.drawPath(cp)
                p.setPen(qc(self.acc, 1.0))
                p.drawText(cr, AL.AlignCenter, val)
            if len(row["o"]) > 1:
                self._hit(rr, lambda rw=row: self.cycle(rw), hid)
