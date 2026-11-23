"""Frozen-screen area selection for asking JARVIS about one region."""
from __future__ import annotations

import io

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

def selection_to_source(rect, widget_size, source_size):
    """Map an inclusive widget-space selection to a clipped source-image crop."""
    x, y, w, h = (int(v) for v in rect)
    ww, wh = (max(1, int(v)) for v in widget_size)
    sw, sh = (max(1, int(v)) for v in source_size)
    left = max(0, min(sw - 1, round(x * sw / ww)))
    top = max(0, min(sh - 1, round(y * sh / wh)))
    right = max(left + 1, min(sw, round((x + w) * sw / ww)))
    bottom = max(top + 1, min(sh, round((y + h) * sh / wh)))
    return (left, top, right, bottom)


def selection_to_screen_viewport(rect, widget_size):
    """Return crop bounds within the whole monitor as normalized 0..1000 units."""
    x, y, w, h = (int(v) for v in rect)
    ww, wh = (max(1, int(v)) for v in widget_size)
    return {
        "x": max(0, min(1000, round(x * 1000 / ww))),
        "y": max(0, min(1000, round(y * 1000 / wh))),
        "w": max(1, min(1000, round(w * 1000 / ww))),
        "h": max(1, min(1000, round(h * 1000 / wh))),
    }


def valid_selection(rect, minimum=12):
    x, y, w, h = (int(v) for v in rect)
    return w >= minimum and h >= minimum


class ScreenRegionSelector(QDialog):
    def __init__(self, source_image, pixel_scale: float, geometry):
        super().__init__(None)
        self._source = source_image.copy()
        self._scale = max(0.1, float(pixel_scale))
        self._start = None
        self._selection = QRect()
        self.image_bytes = None
        self.image_bounds = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setGeometry(geometry)
        buf = io.BytesIO()
        self._source.save(buf, format="PNG")
        self._pixmap = QPixmap()
        self._pixmap.loadFromData(buf.getvalue(), "PNG")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        full = self.rect()
        painter.drawPixmap(full, self._pixmap)
        painter.fillRect(full, QColor(0, 0, 0, 132))
        sel = self._selection.normalized().intersected(full)
        if not sel.isNull() and sel.width() > 1 and sel.height() > 1:
            sx = self._pixmap.width() / max(1, self.width())
            sy = self._pixmap.height() / max(1, self.height())
            src = QRect(
                round(sel.left() * sx), round(sel.top() * sy),
                max(1, round(sel.width() * sx)), max(1, round(sel.height() * sy))
            ).intersected(self._pixmap.rect())
            painter.drawPixmap(sel, self._pixmap, src)
            painter.setPen(QPen(QColor(122, 236, 255), 2))
            painter.drawRect(sel.adjusted(1, 1, -1, -1))
            painter.setPen(QColor(245, 250, 255))
            painter.fillRect(QRect(sel.left(), max(0, sel.top()-26), 150, 23), QColor(9, 20, 31, 220))
            painter.drawText(QRect(sel.left()+7, max(0, sel.top()-24), 140, 19),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{sel.width()} × {sel.height()}")
        painter.fillRect(QRect(14, 14, min(self.width()-28, 510), 38), QColor(8, 18, 29, 220))
        painter.setPen(QColor(241, 248, 255))
        painter.drawText(QRect(26, 14, min(self.width()-52, 490), 38),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "Arraste para selecionar a área • Esc ou botão direito cancela")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.reject()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._selection = QRect(self._start, self._start)
            self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._selection = QRect(self._start, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        self._selection = QRect(self._start, event.position().toPoint()).normalized()
        self._start = None
        sel = self._selection.intersected(self.rect())
        if not valid_selection((sel.x(), sel.y(), sel.width(), sel.height())):
            self._selection = QRect()
            self.update()
            return
        bounds = selection_to_source(
            (sel.x(), sel.y(), sel.width(), sel.height()),
            (self.width(), self.height()),
            (self._source.width, self._source.height),
        )
        crop = self._source.crop(bounds)
        out = io.BytesIO()
        crop.save(out, format="PNG", optimize=True)
        self.image_bytes = out.getvalue()
        self.image_bounds = selection_to_screen_viewport(
            (sel.x(), sel.y(), sel.width(), sel.height()),
            (self.width(), self.height()),
        )
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


def select_screen_area() -> dict:
    """Freeze the primary monitor and return PNG bytes plus crop-to-screen mapping."""
    from core import screenview
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("The desktop UI is not running.")
    screens = app.screens()
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("Windows did not report a primary monitor.")
    monitors = screenview.monitors()
    monitor = screenview._primary_monitor(monitors)
    if not monitor or not monitor.get("width") or not monitor.get("height"):
        raise RuntimeError("The primary monitor could not be identified.")
    image, _monitor, pixel_scale = screenview.capture(monitor)
    picker = ScreenRegionSelector(image, pixel_scale, screen.geometry())
    picker.show()
    picker.raise_()
    picker.activateWindow()
    result = picker.exec()
    data = picker.image_bytes if result == QDialog.DialogCode.Accepted else None
    bounds = picker.image_bounds if result == QDialog.DialogCode.Accepted else None
    picker.close()
    if not data or not bounds:
        raise RuntimeError("Area selection was cancelled.")
    return {"image": data, "viewport": bounds, "screen_size": [screen.geometry().width(), screen.geometry().height()]}
