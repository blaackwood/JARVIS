"""Temporary visual marks over the real desktop, independent of the teaching board."""
from __future__ import annotations

import math
import platform
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget

_TONES = {
    "cyan": QColor(102, 235, 255), "teal": QColor(105, 232, 201),
    "amber": QColor(255, 207, 110), "coral": QColor(255, 130, 122),
    "lilac": QColor(205, 164, 255), "sky": QColor(132, 188, 255),
    "lime": QColor(170, 245, 132), "red": QColor(255, 92, 104),
    "white": QColor(248, 251, 255),
}
_KINDS = {"point","target","ring","frame","underline","strike","check","cross",
          "connect","trace","line","curve","arrow","circle","rect","label",
          "write","highlight","spotlight","num"}


def normalize_screen_marks(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("marks payload must be an object")
    marks = payload.get("marks")
    if not isinstance(marks, list) or not marks or len(marks) > 24:
        raise ValueError("provide 1 to 24 screen marks")
    viewport = payload.get("viewport") or {}
    try:
        vx = max(0.0, min(1000.0, float(viewport.get("x", 0))))
        vy = max(0.0, min(1000.0, float(viewport.get("y", 0))))
        vw = max(0.1, min(1000.0-vx, float(viewport.get("w", 1000))))
        vh = max(0.1, min(1000.0-vy, float(viewport.get("h", 1000))))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("viewport must contain numeric x, y, w and h from the screen crop mapping")
    clean = []
    for raw in marks:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").lower().strip()
        if kind not in _KINDS:
            continue
        def n(key, default=0, low=0, high=1000):
            try:
                value = float(raw.get(key, default))
                if not math.isfinite(value): return default
                return max(low, min(high, value))
            except (TypeError, ValueError, OverflowError):
                return default
        points=[]
        for pt in (raw.get("points") or [])[:64]:
            if isinstance(pt, (list,tuple)) and len(pt)>=2:
                points.append([n_value(pt[0]), n_value(pt[1])])
        mark={
            "id":str(raw.get("id") or "").strip()[:64],
            "kind":kind, "x":n("x",500), "y":n("y",500),
            "w":n("w",100,1,1000), "h":n("h",80,1,1000),
            "r":n("r",28,2,500), "text":str(raw.get("text") or raw.get("label") or "")[:100],
            "n":int(n("n",1,1,99)), "points":points,
            "tone":str(raw.get("tone") or "cyan").lower(),
        }
        if mark["tone"] not in _TONES: mark["tone"]="cyan"
        # Map coordinates from the captured crop into the primary desktop.
        mark["x"] = max(0.0, min(1000.0, vx + mark["x"] * vw / 1000.0))
        mark["y"] = max(0.0, min(1000.0, vy + mark["y"] * vh / 1000.0))
        mark["w"] = max(1.0, min(1000.0, mark["w"] * vw / 1000.0))
        mark["h"] = max(1.0, min(1000.0, mark["h"] * vh / 1000.0))
        # The overlay computes circle radius from screen width, so preserve
        # that same coordinate basis when the source image is a crop.
        mark["r"] = max(2.0, mark["r"] * vw / 1000.0)
        mark["points"] = [
            [max(0.0,min(1000.0,vx + point[0]*vw/1000.0)),
             max(0.0,min(1000.0,vy + point[1]*vh/1000.0))]
            for point in mark["points"]
        ]
        if kind in {"line","curve","trace","arrow","connect"} and len(points)<2:
            continue
        if kind in {"label","write","num"} and not mark["text"]:
            if kind=="num": mark["text"]=str(mark["n"])
            else: continue
        clean.append(mark)
    if not clean:
        raise ValueError("no valid screen marks")
    return {"marks":clean,"duration":max(2,min(45,int(payload.get("duration",12) or 12)))}


def n_value(value):
    try:
        v=float(value)
        if not math.isfinite(v): return 500
        return max(0,min(1000,v))
    except (TypeError,ValueError,OverflowError):
        return 500


class ScreenMarksOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._marks=[]
        self._spotlight=None
        self._next_id=1
        self._duration=12
        self._timer=QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear_marks)

    def set_marks(self, payload: dict, operation: str = "append"):
        app=QApplication.instance()
        screen=app.primaryScreen() if app else None
        if screen is None: raise RuntimeError("primary monitor unavailable")
        self.setGeometry(screen.geometry())
        incoming=[dict(m) for m in payload["marks"]]
        if operation == "replace":
            self._marks=[]
        known={str(m.get("id")) for m in self._marks}
        for mark in incoming:
            mark_id=str(mark.get("id") or "").strip()
            if not mark_id or mark_id in known:
                while f"p{self._next_id}" in known:
                    self._next_id+=1
                mark_id=f"p{self._next_id}"
                self._next_id+=1
            mark["id"]=mark_id
            known.add(mark_id)
            self._marks.append(mark)
        self._duration=max(2,min(45,int(payload.get("duration",self._duration) or self._duration)))
        self._spotlight=next((m for m in reversed(self._marks) if m["kind"]=="spotlight"),None)
        self._timer.stop()
        self._timer.start(self._duration*1000)
        self.update()
        self.show()
        self.raise_()

    def describe_marks(self) -> dict:
        return {
            "visible": self.isVisible(),
            "duration_seconds": self._duration,
            "marks": [
                {"element_id": str(m.get("id") or ""),
                 "kind": m.get("kind"), "text": m.get("text",""),
                 "x": round(float(m.get("x",0)),1), "y": round(float(m.get("y",0)),1),
                 "w": round(float(m.get("w",0)),1), "h": round(float(m.get("h",0)),1),
                 "tone": m.get("tone","cyan")}
                for m in self._marks
            ],
        }

    def edit_mark(self, operation: str, element_id: str = "",
                  patch: dict | None = None, dx: float = 0.0,
                  dy: float = 0.0) -> str:
        operation=str(operation or "").lower()
        if operation == "clear":
            self.clear_marks()
            return "cleared all screen marks"
        if operation == "add":
            from gui.screen_marks import normalize_screen_marks
            normalized=normalize_screen_marks({"marks":[dict(patch or {})],"duration":self._duration})
            self.set_marks(normalized, operation="append")
            return f"added {self._marks[-1]['id']}"
        item=next((m for m in self._marks if str(m.get("id"))==str(element_id)),None)
        if item is None:
            return f"not_found: {element_id}"
        if operation == "delete":
            self._marks.remove(item)
        elif operation == "move":
            dx=float(dx); dy=float(dy)
            for key, delta in (("x",dx),("y",dy)):
                item[key]=max(0.0,min(1000.0,float(item.get(key,500))+delta))
            item["points"]=[
                [max(0.0,min(1000.0,float(x)+dx)),
                 max(0.0,min(1000.0,float(y)+dy))]
                for x,y in item.get("points",[])
            ]
        elif operation in {"update","recolor"}:
            changed=dict(item)
            values=dict(patch or {})
            if operation=="recolor":
                values={"tone":values.get("tone") or values.get("color") or "cyan"}
            changed.update({k:v for k,v in values.items() if k!="id"})
            from gui.screen_marks import normalize_screen_marks
            normalized=normalize_screen_marks({"marks":[changed],"duration":self._duration})
            item.clear(); item.update(normalized["marks"][0]); item["id"]=str(element_id)
        else:
            return "invalid_operation"
        self._spotlight=next((m for m in reversed(self._marks) if m["kind"]=="spotlight"),None)
        if not self._marks:
            self._timer.stop()
            self.hide()
        self.update()
        verb = {"move": "moved", "update": "updated", "recolor": "recolored",
                "delete": "deleted"}.get(operation, operation)
        return f"{verb} {element_id}"
    
    def clear_marks(self):
        self._timer.stop()
        self._marks=[]
        self._spotlight=None
        self.hide()
        self.update()

    def _pt(self,x,y):
        return QPointF(self.width()*float(x)/1000,self.height()*float(y)/1000)

    def _rect(self,m):
        center=self._pt(m["x"],m["y"])
        w=self.width()*m["w"]/1000
        h=self.height()*m["h"]/1000
        return QRectF(center.x()-w/2,center.y()-h/2,w,h)

    def paintEvent(self,event):
        if not self._marks:return
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        if self._spotlight:
            p.fillRect(self.rect(),QColor(0,0,0,145))
            hole=self._rect(self._spotlight)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(hole,QColor(0,0,0,0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        for m in self._marks:
            kind=m["kind"]; color=QColor(_TONES[m["tone"]])
            p.save()
            p.setPen(QPen(color,3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            pt=self._pt(m["x"],m["y"]); rect=self._rect(m)
            if kind in {"point","target","ring"}:
                radius=max(10,min(56,self.width()*m["r"]/1000))
                p.drawEllipse(pt,radius,radius)
                if kind!="ring":
                    p.setBrush(color);p.drawEllipse(pt,4,4)
                if kind=="target":
                    p.drawEllipse(pt,radius*.52,radius*.52)
            elif kind == "circle":
                p.drawEllipse(rect)
            elif kind in {"frame","rect","highlight","spotlight"}:
                if kind in {"highlight"}:
                    fill=QColor(color);fill.setAlpha(62);p.setBrush(fill)
                p.drawRoundedRect(rect,8,8)
            elif kind in {"underline","strike"}:
                yy=rect.bottom() if kind=="underline" else rect.center().y()
                p.drawLine(QPointF(rect.left(),yy),QPointF(rect.right(),yy))
            elif kind in {"check","cross"}:
                r=max(10,min(40,self.width()*m["r"]/1000))
                if kind=="check":
                    path=QPainterPath(QPointF(pt.x()-r*.7,pt.y()))
                    path.lineTo(pt.x()-r*.15,pt.y()+r*.55)
                    path.lineTo(pt.x()+r*.8,pt.y()-r*.65)
                    p.drawPath(path)
                else:
                    p.drawLine(QPointF(pt.x()-r*.55,pt.y()-r*.55),QPointF(pt.x()+r*.55,pt.y()+r*.55))
                    p.drawLine(QPointF(pt.x()+r*.55,pt.y()-r*.55),QPointF(pt.x()-r*.55,pt.y()+r*.55))
            elif kind in {"line","arrow","curve","trace","connect"}:
                pts=[self._pt(x,y) for x,y in m["points"]]
                path=QPainterPath(pts[0])
                if kind=="curve" and len(pts)>=3:
                    for i in range(1,len(pts)-1,2):
                        end=pts[min(i+1,len(pts)-1)]
                        path.quadTo(pts[i],end)
                    if len(pts)%2==0:path.lineTo(pts[-1])
                else:
                    for q in pts[1:]:path.lineTo(q)
                p.drawPath(path)
                if kind=="arrow" and len(pts)>=2:
                    a,b=pts[-2],pts[-1]
                    ang=math.atan2(b.y()-a.y(),b.x()-a.x());size=16
                    for d in (2.55,-2.55):
                        p.drawLine(b,QPointF(b.x()+math.cos(ang+d)*size,b.y()+math.sin(ang+d)*size))
            elif kind in {"label","write","num"}:
                p.setFont(QFont("Segoe UI",16,QFont.Weight.Bold))
                p.drawText(QRectF(pt.x()+12,pt.y()-24,280,48),
                           Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,m["text"])
            p.restore()
        p.end()



class DesktopInkOverlay(QWidget):
    """Live, click-through pen stroke spanning all monitors; never steals focus."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._points = []
        self._snapped = False
        self._generation = 0
        self._maps = []
        self._virtual = QRect()
        self._build_screen_map()
        self.setGeometry(self._virtual)

    def _build_screen_map(self):
        app = QApplication.instance()
        screens = list(app.screens()) if app else []
        monitors = []
        try:
            from core import screenview
            monitors = list(screenview.monitors())[1:]
        except Exception:
            monitors = []
        unused = list(monitors)
        virtual = QRect()
        self._maps = []
        for screen in screens:
            geom = screen.geometry()
            virtual = geom if virtual.isNull() else virtual.united(geom)
            dpr = max(0.1, float(screen.devicePixelRatio() or 1.0))
            chosen = None
            best = float("inf")
            for mon in unused:
                mw = float(mon.get("width", 0))
                mh = float(mon.get("height", 0))
                if not mw or not mh:
                    continue
                score = abs(mw / max(1, geom.width()) - dpr) + abs(mh / max(1, geom.height()) - dpr)
                if score < best:
                    best, chosen = score, mon
            if chosen is not None:
                unused.remove(chosen)
                self._maps.append((dict(chosen), QRect(geom), dpr))
        self._virtual = virtual if not virtual.isNull() else QRect(0, 0, 1, 1)

    def _to_overlay(self, point):
        x, y = float(point[0]), float(point[1])
        for monitor, geom, dpr in self._maps:
            left, top = float(monitor["left"]), float(monitor["top"])
            right = left + float(monitor["width"])
            bottom = top + float(monitor["height"])
            if left <= x <= right and top <= y <= bottom:
                gx = geom.x() + (x - left) / dpr
                gy = geom.y() + (y - top) / dpr
                return QPointF(gx - self._virtual.x(), gy - self._virtual.y())
        # Same-DPI virtual desktop fallback.
        return QPointF(x - self._virtual.x(), y - self._virtual.y())

    def set_stroke(self, points, snapped=False):
        self._generation += 1
        self._points = [self._to_overlay(p) for p in (points or [])]
        self._snapped = bool(snapped)
        if not self._points:
            self.clear_stroke()
            return
        if self.geometry() != self._virtual:
            self.setGeometry(self._virtual)
        self.update()
        self.show()
        self.raise_()
        if platform.system() == "Windows":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11)
            except Exception:
                pass

    def clear_stroke(self, delay_ms=0):
        self._generation += 1
        generation = self._generation
        if delay_ms > 0:
            QTimer.singleShot(int(delay_ms), lambda g=generation: self._clear_if_current(g))
        else:
            self._points = []
            self._snapped = False
            self.hide()
            self.update()

    def _clear_if_current(self, generation):
        if generation != self._generation:
            return
        self._points = []
        self._snapped = False
        self.hide()
        self.update()

    def paintEvent(self, event):
        if len(self._points) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath(self._points[0])
        for point in self._points[1:]:
            path.lineTo(point)
        if self._snapped and len(self._points) > 3:
            path.closeSubpath()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(120, 255, 226, 65), 15,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(3, 39, 34, 220), 6,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(120, 255, 226, 255), 3.5,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        tip = self._points[-1]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(230, 255, 250, 245))
        painter.drawEllipse(tip, 3.5, 3.5)
        if self._snapped:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(230, 255, 250, 190), 2))
            painter.drawEllipse(tip, 11, 11)
        painter.end()


class DesktopGuidanceOverlay(QWidget):
    """Animated, click-through target frame spanning every logical desktop monitor."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._virtual = QRect(0, 0, 1, 1)
        self._target = QRectF()
        self._label = ""
        self._step = 1
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._refresh_geometry()

    def _refresh_geometry(self):
        app = QApplication.instance()
        screens = list(app.screens()) if app else []
        area = QRect()
        for screen in screens:
            area = screen.geometry() if area.isNull() else area.united(screen.geometry())
        self._virtual = area if not area.isNull() else QRect(0, 0, 1, 1)
        if self.geometry() != self._virtual:
            self.setGeometry(self._virtual)

    def show_target(self, rect, label: str, step: int = 1):
        if not isinstance(rect, (tuple, list)) or len(rect) != 4:
            raise ValueError("guided target requires [left, top, width, height]")
        x, y, w, h = (int(round(float(v))) for v in rect)
        if w <= 0 or h <= 0:
            raise ValueError("guided target has no visible area")
        self._refresh_geometry()
        # screenview.Element rectangles use global logical screen coordinates,
        # as does Qt's virtual desktop geometry (including negative origins).
        self._target = QRectF(
            x - self._virtual.x(), y - self._virtual.y(), w, h
        )
        self._label = str(label or "Target")[:100]
        self._step = max(1, min(99, int(step or 1)))
        self._phase = 0.0
        self._timer.start()
        self.update()
        self.show()
        self.raise_()
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
            except Exception:
                pass

    def clear_target(self):
        self._timer.stop()
        self._target = QRectF()
        self.hide()
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.075) % math.tau
        self.update()

    def paintEvent(self, event):
        if self._target.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self._target.adjusted(-7, -7, 7, 7)
        pulse = (math.sin(self._phase) + 1.0) * 0.5
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(
            QColor(120, 255, 226, 50 + int(65 * pulse)), 14 + 5 * pulse,
            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        ))
        painter.drawPath(path)
        painter.setPen(QPen(
            QColor(3, 39, 34, 225), 6, Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        ))
        painter.drawPath(path)
        painter.setPen(QPen(
            QColor(120, 255, 226, 225), 2.3, Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        ))
        painter.drawPath(path)
        tip = path.pointAtPercent((self._phase / math.tau) % 1.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(232, 255, 250, 245))
        painter.drawEllipse(tip, 4.5, 4.5)

        text = f"{self._step}  {self._label}"
        width = min(420.0, max(140.0, 18.0 + len(text) * 7.0))
        height = 32.0
        x = max(8.0, min(float(self.width()) - width - 8.0, rect.left()))
        y = rect.top() - height - 9.0
        if y < 8:
            y = rect.bottom() + 9.0
        y = max(8.0, min(float(self.height()) - height - 8.0, y))
        chip = QRectF(x, y, width, height)
        painter.setPen(QPen(QColor(120, 255, 226, 220), 1.2))
        painter.setBrush(QColor(6, 22, 24, 238))
        painter.drawRoundedRect(chip, 7, 7)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.setPen(QColor(221, 255, 247))
        painter.drawText(
            chip.adjusted(11, 1, -8, -1),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.end()
