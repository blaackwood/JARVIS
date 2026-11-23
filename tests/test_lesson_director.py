import unittest
from unittest import mock

from core import lesson_director


def semantic_lesson():
    return {
        "title": "Buraco negro", "archetype": "anatomy", "beats": [
            {"say": "No centro fica a singularidade.", "add": [
                {"id": "singularity", "label": "Singularidade", "role": "dark", "place": "center"}]},
            {"say": "Em volta existe uma fronteira sem volta.", "add": [
                {"id": "horizon", "label": "Horizonte", "role": "shell", "place": "around", "of": "singularity"}]},
            {"say": "Fora dela, o gás forma um disco brilhante.", "add": [
                {"id": "disk", "label": "Disco", "role": "disk", "place": "ring", "of": "singularity"}]},
        ],
    }


class LessonDirectorTests(unittest.TestCase):
    def test_generates_a_cumulative_3d_lesson_for_any_subject(self):
        lesson = semantic_lesson()
        with mock.patch("core.gemini.as_json", return_value=lesson) as call:
            out = lesson_director.generate_lesson("como funciona um buraco negro")
        self.assertEqual(out["title"], "Buraco negro")
        self.assertIn("buraco negro", call.call_args.args[0])
        self.assertEqual(len(out["beats"]), 3)
        for beat in out["beats"]:
            self.assertEqual([e["type"] for e in beat["elements"]], ["model3d"])
        counts = [len(beat["elements"][0]["parts"]) for beat in out["beats"]]
        self.assertEqual(counts, sorted(counts))
        self.assertGreaterEqual(counts[-1], 3)

    def test_bad_answers_return_none(self):
        for bad in (None, {}, {"beats": []}, "texto"):
            with self.subTest(bad=bad), mock.patch("core.gemini.as_json", return_value=bad):
                self.assertIsNone(lesson_director.generate_lesson("x"))

    def test_list_answer_is_wrapped_and_compiled_to_3d(self):
        with mock.patch("core.gemini.as_json", return_value=semantic_lesson()["beats"]):
            out = lesson_director.generate_lesson("historia")
        self.assertEqual(len(out["beats"]), 3)
        self.assertTrue(all(beat["elements"][0]["type"] == "model3d" for beat in out["beats"]))

    def test_rejects_legacy_flat_2d_beats(self):
        flat = {"title": "Legacy", "beats": [
            {"say": "Um círculo.", "elements": [{"type": "circle", "x": 20, "y": 20, "radius": 4}]}
        ]}
        with mock.patch("core.gemini.as_json", return_value=flat):
            self.assertIsNone(lesson_director.generate_lesson("explique um círculo"))

    def test_rejects_incomplete_precompiled_scenes(self):
        data = {"title": "Legacy", "beats": [
            {"say": "Legenda.", "elements": [{"type": "text", "text": "oi"}]}
        ]}
        with mock.patch("core.gemini.as_json", return_value=data):
            self.assertIsNone(lesson_director.generate_lesson("explique isto"))


if __name__ == "__main__":
    unittest.main()
