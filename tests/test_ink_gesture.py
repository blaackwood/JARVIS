import asyncio
import math
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

from core.ink_gesture import (
    InkGestureTracker, closing_index, make_annotated_crop, capture_ink_crop,
    describe_ink, bounds, encode_live_jpeg, match_ink_control,
)


def circle(cx=300, cy=220, rx=90, ry=65, n=64, close=True):
    pts = [
        (cx + rx * math.cos(2 * math.pi * i / n),
         cy + ry * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]
    if close:
        pts.append(pts[0])
    return pts


class InkGestureRecognitionTests(unittest.TestCase):
    def test_closed_loop_snaps_and_keeps_only_the_loop(self):
        tracker = InkGestureTracker()
        tracker.begin()
        snapped = False
        for p in circle():
            snapped = tracker.add(p) or snapped
        self.assertTrue(snapped)
        self.assertTrue(tracker.snapped)
        self.assertGreaterEqual(len(tracker.points), 8)
        self.assertLessEqual(
            math.hypot(tracker.points[0][0]-tracker.points[-1][0],
                       tracker.points[0][1]-tracker.points[-1][1]),
            0.01,
        )
        before = list(tracker.points)
        tracker.add((900, 900))
        self.assertEqual(tracker.points, before)
        result = tracker.finish()
        self.assertEqual(result, before)
        self.assertFalse(tracker.active)

    def test_open_line_does_not_become_a_selection(self):
        tracker = InkGestureTracker()
        tracker.begin()
        for i in range(80):
            tracker.add((float(i * 8), float(i * 2)))
        self.assertFalse(tracker.snapped)
        self.assertIsNone(tracker.finish())

    def test_small_loop_and_short_scribble_do_not_snap(self):
        tiny = circle(cx=100, cy=100, rx=8, ry=7, n=32)
        self.assertIsNone(closing_index(tiny))
        tracker = InkGestureTracker()
        tracker.begin()
        for p in [(0,0),(30,5),(5,40),(38,15),(0,0)]:
            tracker.add(p)
        self.assertFalse(tracker.snapped)

    def test_closing_index_rejects_non_enclosing_zigzag(self):
        zigzag = [(i * 14, 25 if i % 2 else 0) for i in range(40)]
        self.assertIsNone(closing_index(zigzag))

    def test_tracker_cancel_drops_incomplete_stroke(self):
        tracker = InkGestureTracker()
        tracker.begin((20,20))
        tracker.add((40,20))
        tracker.cancel()
        self.assertFalse(tracker.active)
        self.assertEqual(tracker.points, [])


class InkCropTests(unittest.TestCase):
    def test_crop_includes_teal_loop_and_returns_monitor_viewport(self):
        monitor = {"left": 100, "top": 50, "width": 640, "height": 480}
        image = Image.new("RGB", (640, 480), (30, 35, 42))
        result = make_annotated_crop(image, monitor, circle(320, 240, 80, 60), 1.0)
        self.assertTrue(result["image"].startswith(b"\x89PNG"))
        self.assertEqual(result["monitor"], monitor)
        self.assertEqual(result["crop_bounds"][0:2], [160, 100])
        self.assertGreater(result["viewport"]["w"], 0)
        self.assertGreater(result["viewport"]["h"], 0)
        self.assertGreater(result["image_size"][0], 100)

    def test_crop_respects_capture_pixel_scale(self):
        monitor = {"left": 0, "top": 0, "width": 600, "height": 400}
        # The image is 1.5× physical screen dimensions, like a scaled capture.
        image = Image.new("RGB", (900, 600), (12, 18, 24))
        pts = circle(300, 200, 70, 55)
        result = make_annotated_crop(image, monitor, pts, 1.5)
        self.assertGreater(result["image_size"][0], 100)
        self.assertLessEqual(max(result["image_size"]), 1568)

    def test_capture_chooses_monitor_under_loop_not_primary(self):
        monitors = [
            {"left": 0, "top": 0, "width": 2806, "height": 900},
            {"left": 1440, "top": 69, "width": 1366, "height": 768},
            {"left": 0, "top": 0, "width": 1440, "height": 900},
        ]
        seen = []
        def capture_fn(monitor):
            seen.append(dict(monitor))
            return Image.new("RGB", (monitor["width"], monitor["height"]), (20, 30, 40)), monitor, 1.0
        pts = circle(2000, 400, 85, 55)
        result = capture_ink_crop(pts, monitors=monitors, capture_fn=capture_fn)
        self.assertEqual(seen, [monitors[1]])
        self.assertEqual(result["monitor"], monitors[1])

    def test_capture_rejects_points_outside_all_monitors(self):
        monitors = [
            {"left": 0, "top": 0, "width": 1000, "height": 700},
            {"left": 0, "top": 0, "width": 1000, "height": 700},
        ]
        with self.assertRaisesRegex(RuntimeError, "not inside"):
            capture_ink_crop(circle(2000, 200), monitors=monitors,
                             capture_fn=lambda m: None)

    def test_live_frame_encoder_converts_png_crop_to_jpeg(self):
        monitor = {"left": 0, "top": 0, "width": 640, "height": 480}
        png = make_annotated_crop(
            Image.new("RGB", (640, 480), (30, 35, 42)),
            monitor, circle(320, 240, 80, 60), 1.0
        )["image"]
        jpeg = encode_live_jpeg(png)
        self.assertEqual(jpeg[:2], bytes((255, 216)))
        self.assertEqual(jpeg[-2:], bytes((255, 217)))
        self.assertLess(len(jpeg), len(png))

    def test_accessibility_match_snaps_unique_control_rectangle(self):
        from types import SimpleNamespace
        from core.screenview import Element
        element = Element(
            eid=1, role="button", name="Save", value="", left=125, top=97,
            width=50, height=25, enabled=True
        )
        view = SimpleNamespace(degraded=False, source="uia", app="notepad", elements=[element])
        matched = match_ink_control(circle(300, 220, 90, 65), view=view, scale=0.5)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["label"], "Save")
        self.assertEqual(matched["role"], "button")
        self.assertEqual(matched["rect"], (250.0, 194.0, 100.0, 50.0))

    def test_accessibility_match_refuses_multiple_interactable_controls(self):
        from types import SimpleNamespace
        from core.screenview import Element
        elements = [
            Element(eid=1, role="button", name="Save", value="", left=110, top=90,
                    width=45, height=25, enabled=True),
            Element(eid=2, role="button", name="Cancel", value="", left=150, top=105,
                    width=45, height=25, enabled=True),
        ]
        view = SimpleNamespace(degraded=False, source="uia", app="notepad", elements=elements)
        self.assertIsNone(match_ink_control(circle(), view=view, scale=0.5))

    def test_accessibility_match_ignores_protected_fields(self):
        from types import SimpleNamespace
        from core.screenview import Element
        element = Element(
            eid=1, role="edit", name="Password", value="secret", left=125, top=97,
            width=50, height=25, enabled=True, protected=True
        )
        view = SimpleNamespace(degraded=False, source="uia", app="browser", elements=[element])
        self.assertIsNone(match_ink_control(circle(), view=view, scale=0.5))

    def test_accessibility_match_keeps_original_loop_when_view_is_degraded(self):
        from types import SimpleNamespace
        view = SimpleNamespace(degraded=True, source="self", app="jarvis", elements=[])
        self.assertIsNone(match_ink_control(circle(), view=view, scale=0.5))

    def test_snapped_crop_includes_accessible_control_bounds(self):
        monitor = {"left": 0, "top": 0, "width": 640, "height": 480}
        image = Image.new("RGB", (640, 480), (30, 35, 42))
        result = make_annotated_crop(
            image, monitor, circle(300, 220, 70, 50), 1.0,
            annotation_rect=(275, 205, 50, 30)
        )
        self.assertTrue(result["snapped_to_control"])
        self.assertIn("image", result)

    def test_description_does_not_guess_control_identity(self):
        note = describe_ink(circle())
        self.assertIn("closed teal circle", note)
        self.assertIn("do not guess", note.lower())


class InkOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_live_pen_overlay_shows_and_clears_without_click_interception(self):
        from gui.screen_marks import DesktopInkOverlay
        overlay = DesktopInkOverlay()
        try:
            overlay.set_stroke(circle(250, 200, 70, 45), snapped=True)
            self.app.processEvents()
            self.assertTrue(overlay.isVisible())
            self.assertTrue(overlay._snapped)
            self.assertGreaterEqual(len(overlay._points), 8)
            overlay.clear_stroke()
            self.app.processEvents()
            self.assertFalse(overlay.isVisible())
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
