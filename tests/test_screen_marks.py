import unittest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QApplication

from gui.screen_marks import ScreenMarksOverlay, normalize_screen_marks


class ScreenMarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_normalizes_marks_and_clamps_coordinates(self):
        payload = normalize_screen_marks({
            "duration": 100,
            "marks": [
                {"kind": "target", "x": 1200, "y": -10, "tone": "teal"},
                {"kind": "arrow", "points": [[0,0],[500,500],[1000,1000]]},
                {"kind": "label", "x": 400, "y": 300, "text": "Click here"},
            ],
        })
        self.assertEqual(payload["duration"], 45)
        self.assertEqual(payload["marks"][0]["x"], 1000)
        self.assertEqual(payload["marks"][0]["y"], 0)
        self.assertEqual(payload["marks"][1]["points"][1], [500,500])
        self.assertEqual(len(payload["marks"]), 3)

    def test_crop_viewport_maps_mark_coordinates_back_to_full_desktop(self):
        payload = normalize_screen_marks({
            "viewport": {"x": 100, "y": 200, "w": 300, "h": 400},
            "marks": [
                {"kind": "target", "x": 500, "y": 500, "w": 100, "h": 200, "r": 100},
                {"kind": "arrow", "points": [[0,0],[1000,1000]]},
            ],
        })
        mark = payload["marks"][0]
        self.assertEqual((mark["x"], mark["y"]), (250, 400))
        self.assertEqual((mark["w"], mark["h"]), (30, 80))
        self.assertEqual(mark["r"], 30)
        self.assertEqual(payload["marks"][1]["points"], [[100,200],[400,600]])

    def test_rejects_invalid_or_empty_mark_sets(self):
        with self.assertRaises(ValueError):
            normalize_screen_marks({"marks": []})
        with self.assertRaises(ValueError):
            normalize_screen_marks({"marks": [{"kind": "line"}]})

    def test_overlay_renders_pointer_and_spotlight_to_qimage(self):
        overlay = ScreenMarksOverlay()
        overlay.resize(640, 480)
        overlay._marks = normalize_screen_marks({
            "duration": 5,
            "marks": [
                {"kind": "target", "x": 220, "y": 330, "r": 24, "tone": "cyan"},
                {"kind": "spotlight", "x": 600, "y": 500, "w": 200, "h": 180},
                {"kind": "arrow", "points": [[50,100],[250,300],[500,400]], "tone": "amber"},
                {"kind": "label", "x": 600, "y": 500, "text": "Aqui"},
            ],
        })["marks"]
        overlay._spotlight = next(m for m in overlay._marks if m["kind"] == "spotlight")
        image = QImage(640,480,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        overlay.render(painter)
        painter.end()
        self.assertGreater(image.pixelColor(140,158).alpha(),0)
        overlay.close()

    def test_screen_marks_are_classified_as_reversible_overlays(self):
        from core.authorization import classify_action
        self.assertEqual(classify_action("show_screen_marks", {"marks": [{"kind": "ring"}]}),
                         "reversible_change")
        self.assertEqual(classify_action("clear_screen_marks", {}),
                         "reversible_change")

    def test_screen_marks_have_stable_ids_and_support_item_edits(self):
        overlay = ScreenMarksOverlay()
        try:
            overlay.resize(640, 480)
            overlay.set_marks(normalize_screen_marks({
                "duration": 30,
                "marks": [
                    {"kind": "target", "x": 200, "y": 300, "tone": "cyan"},
                    {"kind": "label", "x": 500, "y": 500, "text": "Next"},
                ],
            }))
            first = overlay.describe_marks()
            self.assertEqual([m["element_id"] for m in first["marks"]], ["p1", "p2"])
            self.assertEqual(overlay.edit_mark("move", "p1", dx=25, dy=-40), "moved p1")
            moved = overlay.describe_marks()["marks"][0]
            self.assertEqual((moved["x"], moved["y"]), (225.0, 260.0))
            self.assertEqual(overlay.edit_mark("recolor", "p1", {"tone": "red"}), "recolored p1")
            recolored = overlay.describe_marks()["marks"][0]
            self.assertEqual(recolored["tone"], "red")
            self.assertEqual(overlay.edit_mark("update", "p2", {"text": "Updated"}), "updated p2")
            self.assertEqual(overlay.describe_marks()["marks"][1]["text"], "Updated")
            self.assertEqual(overlay.edit_mark("delete", "p1"), "deleted p1")
            self.assertEqual([m["element_id"] for m in overlay.describe_marks()["marks"]], ["p2"])
            self.assertTrue(overlay.edit_mark("add", patch={"kind": "ring", "x": 700, "y": 300}).startswith("added p"))
            self.assertEqual(len(overlay.describe_marks()["marks"]), 2)
        finally:
            overlay.close()

    def test_screen_mark_inspection_is_read_only_and_edits_are_reversible(self):
        from core.authorization import classify_action
        self.assertEqual(classify_action("inspect_screen_marks", {}), "read_only")
        self.assertEqual(classify_action("edit_screen_marks", {"operation": "delete"}), "reversible_change")

    def test_tool_loader_registers_screen_marks(self):
        from actions import screen_marks, clear_screen_marks, inspect_screen_marks, edit_screen_marks
        self.assertEqual(screen_marks.TOOL["name"], "show_screen_marks")
        self.assertIn("PRIMARY", screen_marks.TOOL["description"])
        self.assertEqual(clear_screen_marks.TOOL["name"], "clear_screen_marks")
        self.assertEqual(inspect_screen_marks.TOOL["name"], "inspect_screen_marks")
        self.assertEqual(edit_screen_marks.TOOL["name"], "edit_screen_marks")


if __name__ == "__main__":
    unittest.main()
