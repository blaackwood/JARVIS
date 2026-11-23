"""Opt-in native Windows test for click-through desktop teaching overlays.

Run with JARVIS_NATIVE_DESKTOP_TESTS=1 and the normal Windows Qt platform.
"""
import ctypes
import os
import platform
import time
import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from gui.visual_board import VisualBoardOverlay


@unittest.skipUnless(
    platform.system() == "Windows" and os.environ.get("JARVIS_NATIVE_DESKTOP_TESTS") == "1",
    "Requires an interactive Windows desktop; opt in with JARVIS_NATIVE_DESKTOP_TESTS=1.",
)
class NativeVisualPassThroughTests(unittest.TestCase):
    def test_physical_click_reaches_real_window_beneath_visual_board(self):
        app = QApplication.instance() or QApplication([])
        user32 = ctypes.windll.user32
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        old_cursor = POINT()
        user32.GetCursorPos(ctypes.byref(old_cursor))
        target = QWidget()
        board = None
        try:
            target.setWindowFlags(target.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            target.setWindowTitle("JARVIS native click-through test")
            target.resize(520, 260)
            screen = app.primaryScreen().availableGeometry()
            target.move(screen.center().x() - 260, screen.center().y() - 130)
            button = QPushButton("TARGET CLICK TEST", target)
            button.resize(240, 64)
            button.move((target.width() - button.width()) // 2,
                        (target.height() - button.height()) // 2)
            clicked = []
            button.clicked.connect(lambda: clicked.append(True))
            target.show()
            target.raise_()
            app.processEvents()

            board = VisualBoardOverlay()
            board.set_content({
                "title": "Guia de teste",
                "elements": [{"type": "text", "x": 50, "y": 50,
                              "text": "A explicação continua visível"}],
            })
            board.show()
            board.raise_()
            app.processEvents()

            point = button.mapToGlobal(button.rect().center())
            self.assertTrue(board.geometry().contains(point))
            board.set_input_passthrough(True)
            app.processEvents()

            user32.SetCursorPos(point.x(), point.y())
            time.sleep(0.08)
            class NativePoint(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            native_point = NativePoint(point.x(), point.y())
            window_from_point = user32.WindowFromPoint
            window_from_point.argtypes = [NativePoint]
            window_from_point.restype = ctypes.c_void_p
            hit = window_from_point(native_point)
            target_hwnd = int(target.winId())
            self.assertEqual(
                int(hit or 0), target_hwnd,
                "Windows hit testing should target the app beneath the lesson overlay.",
            )
            user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
            time.sleep(0.04)
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up

            deadline = time.monotonic() + 1.2
            while time.monotonic() < deadline and not clicked:
                app.processEvents()
                time.sleep(0.01)
            self.assertTrue(clicked, "The underlying window did not receive the real click.")
        finally:
            if board is not None:
                try:
                    board.set_input_passthrough(False)
                    board.close()
                except Exception:
                    pass
            target.close()
            user32.SetCursorPos(old_cursor.x, old_cursor.y)
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
