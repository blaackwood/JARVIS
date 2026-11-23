import unittest

from gui.region_selector import selection_to_source, selection_to_screen_viewport, valid_selection


class ScreenAreaSelectionGeometryTests(unittest.TestCase):
    def test_selection_maps_logical_rect_to_full_resolution_source(self):
        # 2x capture scale: a 61x41 logical selection becomes 122x82 pixels.
        bounds = selection_to_source((20, 10, 61, 41), (200, 100), (400, 200))
        self.assertEqual(bounds, (40, 20, 162, 102))
        self.assertEqual(bounds[2] - bounds[0], 122)
        self.assertEqual(bounds[3] - bounds[1], 82)

    def test_selection_is_clipped_to_source_image(self):
        self.assertEqual(
            selection_to_source((90, 45, 30, 20), (100, 50), (200, 100)),
            (180, 90, 200, 100),
        )

    def test_selection_returns_precise_crop_viewport_on_full_screen_grid(self):
        viewport = selection_to_screen_viewport((200, 100, 300, 200), (1000, 500))
        self.assertEqual(viewport, {"x": 200, "y": 200, "w": 300, "h": 400})

    def test_tiny_click_is_not_a_selection(self):
        self.assertFalse(valid_selection((10, 10, 4, 4)))
        self.assertTrue(valid_selection((10, 10, 12, 12)))


if __name__ == "__main__":
    unittest.main()
