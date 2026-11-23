import unittest
from unittest import mock

import core.visual_board as vb


def rich_scene(**extra):
    names = ["sol", "folha", "agua", "co2", "acucar", "oxigenio"]
    parts = [{"id": n, "label": n.capitalize(), "shape": "sphere", "size": 10,
              "dx": -50 + i * 20, "dy": (i % 3) * 15 - 15, "dz": 0}
             for i, n in enumerate(names)]
    links = [{"from": "sol", "to": "folha"}, {"from": "folha", "to": "oxigenio"}]
    el = {"type": "model3d", "shape": "none", "x": 2, "y": 3, "width": 62, "height": 88,
          "parts": parts, "links": links}
    el.update(extra)
    return el


class ThreeDOnlyTests(unittest.TestCase):
    def setUp(self):
        self._old = vb.ENFORCE_3D
        vb.ENFORCE_3D = True

    def tearDown(self):
        vb.ENFORCE_3D = self._old

    def test_flat_shapes_are_rejected(self):
        with self.assertRaises(ValueError):
            vb.enforce_3d([{"type": "circle"}, {"type": "model3d"}])

    def test_scene_without_model_is_rejected(self):
        with self.assertRaises(ValueError):
            vb.enforce_3d([{"type": "text", "text": "ola"}])

    def test_model3d_with_caption_is_accepted(self):
        vb.enforce_3d([rich_scene(), {"type": "text", "text": "ola"}])

    def test_poor_scene_is_rejected(self):
        poor = {"type": "model3d", "parts": [
            {"shape": "sphere", "dx": 0, "dy": 0, "dz": 0} for _ in range(2)], "links": []}
        with self.assertRaises(ValueError) as ctx:
            vb.enforce_3d([poor])
        self.assertIn("too poor", str(ctx.exception))

    def test_stacked_scene_is_repaired(self):
        scene = {"type": "model3d", "parts": [
            {"label": n, "shape": "sphere", "dx": 0, "dy": 0, "dz": 0} for n in "ABCD"],
            "links": [{"from": "a", "to": "B"}, {"from": "x", "to": "y"}]}
        vb.enforce_3d([scene])
        self.assertEqual(len({p["id"] for p in scene["parts"]}), 4)
        self.assertTrue(any(p["dx"] for p in scene["parts"]))
        self.assertEqual(len(scene["links"]), 1)

    def test_show_visual_refuses_2d_and_accepts_3d(self):
        from actions.visual_board import show_visual
        player = mock.Mock()
        flat = show_visual({"title": "t", "elements": [
            {"type": "circle", "x": 10, "y": 10, "radius": 5}]}, player=player)
        self.assertTrue(flat.startswith("VISUAL_INVALID"))
        solid = show_visual({"title": "t", "operation": "replace", "elements": [
            rich_scene()]}, player=player)
        self.assertTrue(solid.startswith("VISUAL_SHOWN"), solid)

    def test_lesson_requires_a_3d_scene(self):
        from actions.present_visual_lesson import present_visual_lesson
        player = mock.Mock()
        result = present_visual_lesson({"title": "t", "beats": [
            {"say": "Um circulo.", "elements": [
                {"type": "circle", "x": 20, "y": 20, "radius": 4}]},
        ]}, player=player)
        self.assertTrue(result.startswith("PRESENTATION_INVALID"), result)
        ok = present_visual_lesson({"title": "t", "beats": [
            {"say": "Uma esfera.", "elements": [rich_scene()]},
        ]}, player=player)
        self.assertTrue(ok.startswith("PRESENTATION_SHOWN"), ok)


    def test_lesson_only_last_beat_must_be_rich(self):
        from actions.present_visual_lesson import present_visual_lesson
        full = rich_scene()
        first = dict(full)
        first["parts"] = full["parts"][:2]
        first["links"] = []
        result = present_visual_lesson({"title": "t", "beats": [
            {"say": "Comeca simples.", "elements": [first]},
            {"say": "Agora completo.", "elements": [full]},
        ]}, player=mock.Mock())
        self.assertTrue(result.startswith("PRESENTATION_SHOWN"), result)


if __name__ == "__main__":
    unittest.main()
