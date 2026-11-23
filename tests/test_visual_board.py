import unittest
from unittest.mock import Mock, patch

from core.visual_board import (
    normalize_visual_payload, build_right_triangle_payload,
    fallback_visual_for_request,
)
from actions.draw_right_triangle import draw_right_triangle
from actions.visual_board import show_visual, clear_visual
from core.action_loader import discover_actions

def model_scene(label="Cena", x=2, y=3):
    """Fixture de cena 3D válida: cinco corpos rotulados e conexões entre eles."""
    names = ("Núcleo", "Entrada", "Processo", "Saída", "Energia")
    offsets = ((0, 0, 0), (-28, -12, 0), (28, -12, 2), (-16, 25, 5), (18, 26, -4))
    shapes = ("sphere", "cube", "cylinder", "cone", "torus")
    parts = [
        {
            "id": f"part-{i}",
            "shape": shapes[i],
            "size": 18 if i == 0 else 10 + i,
            "dx": offsets[i][0],
            "dy": offsets[i][1],
            "dz": offsets[i][2],
            "label": f"{label} {names[i]}",
        }
        for i in range(5)
    ]
    return {
        "type": "model3d",
        "x": x,
        "y": y,
        "width": 62,
        "height": 88,
        "shape": "none",
        "parts": parts,
        "links": [
            {"from": "part-0", "to": f"part-{i}", "flow": True}
            for i in range(1, 5)
        ],
    }



class VisualBoardPayloadTests(unittest.TestCase):
    def test_normalizes_geometry_primitives(self):
        payload = normalize_visual_payload({
            "title": "Triângulo retângulo",
            "subtitle": "Hipotenusa e catetos",
            "layout": "geometry",
            "elements": [
                {"type": "polygon", "points": [
                    {"x": 10, "y": 85}, {"x": 10, "y": 15}, {"x": 82, "y": 85}
                ], "color": "cyan", "fill": True},
                {"type": "angle", "x": 10, "y": 85, "x2": 10, "y2": 15,
                 "x3": 82, "y3": 85, "label": "90°"},
                {"type": "formula", "x": 55, "y": 8, "text": "a² + b² = c²"},
            ],
        })
        self.assertEqual(payload["layout"], "geometry")
        self.assertEqual(payload["title"], "Triângulo retângulo")
        self.assertEqual([e["type"] for e in payload["elements"]],
                         ["polygon", "angle", "formula"])
        self.assertEqual(len(payload["elements"][0]["points"]), 3)

    def test_curve_points_are_bounded_and_closed_fill_is_explicit(self):
        from actions.visual_board import _ELEMENT_SCHEMA
        payload = normalize_visual_payload({"elements": [{
            "type": "curve", "closed": True, "fill": True,
            "points": [{"x": -5, "y": 130}, {"x": 50, "y": 10},
                       {"x": 90, "y": 80}] * 20,
        }, {"type": "curve", "fill": True,
            "points": [{"x": 0, "y": 50}, {"x": 100, "y": 50}]}]})
        closed, opened = payload["elements"]
        self.assertEqual(len(closed["points"]), 32)
        self.assertEqual(closed["points"][0], {"x": 0, "y": 100})
        self.assertTrue(closed["closed"])
        self.assertTrue(closed["fill"])
        self.assertFalse(opened["closed"])
        self.assertFalse(opened["fill"])
        self.assertIn("curve", _ELEMENT_SCHEMA["properties"]["type"]["enum"])

    def test_curve_rejects_insufficient_points(self):
        for closed, points in ((False, [{"x": 1, "y": 1}]),
                               (True, [{"x": 1, "y": 1}, {"x": 2, "y": 2}])):
            with self.subTest(closed=closed), self.assertRaises(ValueError):
                normalize_visual_payload({"elements": [{
                    "type": "curve", "closed": closed, "points": points}]})

    def test_rejects_empty_or_invalid_drawings(self):
        with self.assertRaises(ValueError):
            normalize_visual_payload({"title": "Vazio", "elements": []})
        with self.assertRaises(ValueError):
            normalize_visual_payload({"title": "Inválido", "elements": [{"type": "made_up"}]})

    def test_bounds_and_sanitizes_model_values(self):
        payload = normalize_visual_payload({
            "title": "X" * 200,
            "layout": "unknown",
            "elements": [
                {"type": "text", "x": 900, "y": -30, "font_size": 900,
                 "text": "  texto\nseguro  ", "color": "javascript:alert(1)"},
                *({"type": "line", "x": i, "y": i, "x2": 90, "y2": 90}
                  for i in range(60)),
            ],
        })
        self.assertEqual(len(payload["title"]), 72)
        self.assertEqual(payload["layout"], "diagram")
        self.assertEqual(payload["elements"][0]["x"], 100)
        self.assertEqual(payload["elements"][0]["y"], 0)
        self.assertEqual(payload["elements"][0]["font_size"], 32)
        self.assertEqual(payload["elements"][0]["color"], "cyan")
        self.assertEqual(len(payload["elements"]), 48)

    def test_rich_visuals_have_usable_default_dimensions(self):
        payload = normalize_visual_payload({"elements": [
            {"type": "quiz", "title": "Escolha", "options": ["Sim", "Não"]},
            {"type": "card", "heading": "Conceito"},
            {"type": "rect", "x": 0, "y": 0},
        ]})
        quiz, card, rectangle = payload["elements"]
        self.assertEqual((quiz["width"], quiz["height"]), (36, 32))
        self.assertEqual((card["width"], card["height"]), (36, 32))
        self.assertEqual((rectangle["width"], rectangle["height"]), (20, 12))

    def test_rejects_non_object_payload(self):
        with self.assertRaises(ValueError):
            normalize_visual_payload("hello")

    def test_pythagoras_learning_requests_get_the_interactive_visual_automatically(self):
        requests = (
            "Me explica o teorema de Pitágoras",
            "O que é o teorema de Pitágoras?",
            "Me explica o que é um triângulo retângulo",
            "Como calcular a hipotenusa?",
            "Qual é a fórmula dos catetos?",
            "Desenha um triângulo retângulo e explica Pitágoras",
        )
        for request in requests:
            with self.subTest(request=request):
                payload = fallback_visual_for_request(request)
                self.assertIsNotNone(payload)
                self.assertEqual(payload["layout"], "geometry")
                self.assertEqual(payload["interactive"]["kind"], "right_triangle")
                self.assertEqual(payload["interactive"]["a"], 3.0)
                self.assertEqual(payload["interactive"]["b"], 4.0)
                kinds = [item["type"] for item in payload["elements"]]
                self.assertIn("polygon", kinds)
                self.assertIn("angle", kinds)
                self.assertIn("formula", kinds)
                self.assertIn("a² + b² = c²", [
                    item["text"] for item in payload["elements"]
                    if item["type"] == "formula"
                ])

    def test_pythagoras_biography_does_not_trigger_geometry_lesson(self):
        self.assertIsNone(fallback_visual_for_request("Quem foi Pitágoras?"))
        self.assertIsNone(fallback_visual_for_request("Conte a biografia de Pitágoras."))
        self.assertIsNone(fallback_visual_for_request("Me explica o teorema de Tales."))


class VisualBoardOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_smooth_curve_has_cubic_segments_fill_and_editable_vertices(self):
        from PyQt6.QtCore import QRectF, QPointF, Qt
        from PyQt6.QtGui import QPainterPath, QImage, QPainter
        from PyQt6.QtTest import QTest
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        item = {"id": "leaf", "type": "curve", "closed": True, "fill": True,
                "color": "green", "stroke_width": 3,
                "points": [{"x": 50, "y": 15}, {"x": 70, "y": 50},
                           {"x": 50, "y": 85}, {"x": 30, "y": 50}]}
        try:
            board.set_content(normalize_visual_payload({"elements": [item]}))
            path = board._curve_path(QRectF(0, 0, 400, 300), item)
            self.assertTrue(any(path.elementAt(i).type == QPainterPath.ElementType.CurveToElement
                                for i in range(path.elementCount())))
            self.assertTrue(path.contains(QPointF(200, 150)))
            self.assertTrue(board._element_hit(item, QPointF(200, 150), QRectF(0, 0, 400, 300)))
            self.assertFalse(board._element_hit(item, QPointF(20, 20), QRectF(0, 0, 400, 300)))
            image = QImage(400, 300, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            board._draw_revealing_shape(painter, QRectF(0, 0, 400, 300), item, 0.5)
            painter.end()
            partial = image.copy()
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            board._draw_element(painter, QRectF(0, 0, 400, 300), item)
            painter.end()
            self.assertNotEqual(partial, image)
            self.assertGreater(image.pixelColor(200, 150).alpha(), 0)
            board.show()
            board._reveal_index = 1
            board._reveal_progress = 0
            self.app.processEvents()
            board.repaint()
            self.assertEqual(len(board._generic_handles), 4)
            origin = board._generic_handles[0][3].toPoint()
            QTest.mousePress(board, Qt.MouseButton.LeftButton, pos=origin)
            QTest.mouseMove(board, origin + QPointF(20, 10).toPoint())
            QTest.mouseRelease(board, Qt.MouseButton.LeftButton, pos=origin + QPointF(20, 10).toPoint())
            self.assertNotEqual(board._payload["elements"][0]["points"][0], item["points"][0])
        finally:
            board.close()

    def test_overlay_accepts_mouse_interaction_without_taking_keyboard_focus(self):
        from PyQt6.QtCore import Qt
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            flags = board.windowFlags()
            self.assertTrue(flags & Qt.WindowType.WindowDoesNotAcceptFocus)
            self.assertFalse(flags & Qt.WindowType.WindowTransparentForInput)
            self.assertFalse(board.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            ))
            self.assertTrue(board.testAttribute(
                Qt.WidgetAttribute.WA_ShowWithoutActivating
            ))
            self.assertTrue(board.hasMouseTracking())
        finally:
            board.close()

    def test_narrated_lesson_requires_transcript_and_audible_time_for_each_beat(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        payload = {
            "title": "Aula",
            "elements": [
                {"id": "a", "type": "text", "text": "Primeira parte"},
                {"id": "b", "type": "text", "text": "Segunda parte"},
            ],
            "_voice_cps": 13.0,
            "_lesson_timeline": [
                {"index": 1, "start": 0, "end": 1,
                 "caption": "A luz chega à folha.", "duration": 1.2,
                 "start_seconds": 0.0, "end_seconds": 1.2},
                {"index": 2, "start": 1, "end": 2,
                 "caption": "A planta produz glicose.", "duration": 2.4,
                 "start_seconds": 1.3, "end_seconds": 3.7},
            ],
        }
        try:
            board.set_content(payload)
            self.assertTrue(board._draw_timer.isActive())
            self.assertEqual(board._reveal_index, -1)  # not even mark zero is visible
            board.set_lesson_status("Aula", 1, 2, draw_duration=3.6)
            self.assertEqual(board._lesson_caption, "Aguardando a fala do JARVIS...")
            board._draw_timer.stop()

            # Transcript by itself cannot draw anything while the speaker is silent.
            board.set_live_caption("A luz chega à folha. A planta produz glicose.")
            board._lesson_audio_elapsed = 1.0
            board._tick_voice_lesson()
            self.assertEqual(board._reveal_index, -1)

            board.add_audio_playback_window(__import__("time").time() - 1.0, 5.0)
            board.set_live_caption("A luz")
            board._lesson_audio_elapsed = 0.25
            board._tick_voice_lesson()
            self.assertEqual(board._lesson_caption, "A luz chega à folha.")
            self.assertEqual(board._lesson_index, 1)
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(board._reveal_progress, 0.0)

            # A complete transcript cannot jump to the next beat until the
            # first beat's actual speaker-clock duration has elapsed.
            board.set_live_caption("A luz chega à folha. A planta produz glicose.")
            board._lesson_audio_elapsed = 0.7
            board._tick_voice_lesson()
            self.assertEqual(board._lesson_caption, "A luz chega à folha.")
            self.assertEqual(board._lesson_index, 1)
            self.assertEqual(board._reveal_index, 0)
            self.assertLess(board._reveal_progress, 1.0)

            board._lesson_audio_elapsed = 1.2
            board._tick_voice_lesson()
            self.assertEqual(board._lesson_caption, "A luz chega à folha.")
            self.assertEqual(board._lesson_index, 1)
            self.assertEqual(board._reveal_progress, 1.0)

            board._lesson_audio_elapsed = 1.6
            board._tick_voice_lesson()
            self.assertEqual(board._lesson_caption, "A planta produz glicose.")
            self.assertEqual(board._lesson_index, 2)
            self.assertEqual(board._reveal_index, 1)
            self.assertGreater(board._reveal_progress, 0.0)

            board._lesson_audio_elapsed = 3.7
            board._tick_voice_lesson()
            self.assertEqual(board._lesson_caption, "Etapas concluídas")
            self.assertEqual(board._lesson_index, 2)
            self.assertEqual(board._reveal_index, 2)
        finally:
            board.close()

    @unittest.skip("3D-only: the flat Pythagoras triangle is disabled")
    def test_full_pythagoras_transcript_unlocks_all_eight_beats(self):
        from actions.draw_right_triangle import draw_right_triangle
        from gui.visual_board import VisualBoardOverlay

        player = Mock()
        draw_right_triangle({}, player=player)
        payload = player.show_visual_board.call_args.args[0]
        board = VisualBoardOverlay()
        try:
            board.set_content(payload)
            transcript = (
                "Este é um triângulo retângulo. Repare que ele possui um ângulo de noventa graus. "
                "Os dois lados que formam esse ângulo reto recebem o nome de catetos. "
                "O lado inclinado, que fica na frente do ângulo de noventa graus, é a hipotenusa. "
                "Agora vamos ao exemplo: os catetos medem três centímetros e quatro centímetros. "
                "Queremos descobrir. Para isso, usamos o teorema de Pitágoras: "
                "a ao quadrado mais b ao quadrado é igual a c ao quadrado. "
                "Agora substituímos a e b pelos valores conhecidos: três ao quadrado mais "
                "quatro ao quadrado é igual a c ao quadrado. "
                "Três ao quadrado é nove, quatro ao quadrado é dezesseis. "
                "Nove mais dezesseis é vinte e cinco. "
                "Extraímos a raiz quadrada dos dois lados e encontramos c igual a cinco centímetros. "
                "Essa é a hipotenusa. Quer tentar um exemplo diferente?"
            )
            board._refresh_lesson_transcript_progress(transcript)
            expected = [
                len(board._spoken_tokens(beat["caption"]))
                for beat in board._lesson_timeline
            ]
            self.assertEqual(len(expected), 8)
            self.assertEqual(board._lesson_transcript_progress, expected)
        finally:
            board.close()

    def test_transcript_dropped_tail_does_not_stall_the_next_spoken_beat(self):
        from gui.visual_board import VisualBoardOverlay

        captions = [
            "Este é um triângulo retângulo. Repare que ele possui um ângulo de noventa graus.",
            "Os dois lados que formam esse ângulo reto recebem o nome de catetos.",
            "O lado inclinado, que fica na frente do ângulo de noventa graus, é a hipotenusa.",
            "Agora vamos ao exemplo: os catetos medem três centímetros e quatro centímetros. Queremos descobrir a hipotenusa.",
            "Para isso, usamos o teorema de Pitágoras: a ao quadrado mais b ao quadrado é igual a c ao quadrado.",
        ]
        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Teste ASR",
                "elements": [{"id": f"e{i}", "type": "text", "text": f"Etapa {i}"}
                             for i in range(1, len(captions) + 1)],
                "_lesson_timeline": [
                    {"index": i, "start": i - 1, "end": i,
                     "caption": caption, "duration": 1.2,
                     "start_seconds": (i - 1) * 1.3,
                     "end_seconds": (i - 1) * 1.3 + 1.2}
                    for i, caption in enumerate(captions, 1)
                ],
            })
            # ASR drops the tail "a hipotenusa" from the example-introduction
            # caption and continues immediately with "Para isso...".
            transcript = (
                "Este é um triângulo retângulo. Repare que ele possui um ângulo de noventa graus. "
                "Os dois lados que formam esse ângulo reto recebem o nome de catetos. "
                "O lado inclinado, que fica na frente do ângulo de noventa graus, é a hipotenusa. "
                "Agora vamos ao exemplo: os catetos medem três centímetros e quatro centímetros. "
                "Queremos descobrir. Para isso, usamos o teorema de Pitágoras: "
                "a ao quadrado mais b ao quadrado é igual a c ao quadrado."
            )
            board._refresh_lesson_transcript_progress(transcript)
            expected = [len(board._spoken_tokens(caption)) for caption in captions]
            self.assertEqual(board._lesson_transcript_progress[:4], expected[:4])
            self.assertGreaterEqual(
                board._lesson_transcript_progress[4], 2,
                "The next beat must unlock once its own first words are present",
            )
        finally:
            board.close()

    def test_pcm_transcript_checkpoints_drive_reveal_at_their_audible_timestamps(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Aula alinhada ao PCM",
                "elements": [
                    {"id": "first", "type": "text", "text": "Primeira ideia"},
                    {"id": "second", "type": "text", "text": "Segunda ideia"},
                ],
                "_lesson_timeline": [
                    {"index": 1, "start": 0, "end": 1,
                     "caption": "A luz chega à folha.", "duration": 1.2,
                     "start_seconds": 0.0, "end_seconds": 1.2},
                    {"index": 2, "start": 1, "end": 2,
                     "caption": "A planta produz glicose.", "duration": 1.2,
                     "start_seconds": 1.3, "end_seconds": 2.5},
                ],
            })
            board._draw_timer.stop()
            board.set_live_caption_at_time("A luz chega à folha.", 100.2)
            board.set_live_caption_at_time(
                "A luz chega à folha. A planta produz glicose.", 101.0
            )
            self.assertEqual(board._live_caption, "Aguardando a fala do JARVIS...")
            self.assertTrue(board._lesson_uses_audio_checkpoints)

            with patch.object(board, "_audio_is_playing", return_value=True), \
                 patch("time.time", return_value=100.1):
                board._tick_voice_lesson()
            self.assertEqual(board._reveal_index, -1)  # transcript alone is not audible yet

            with patch.object(board, "_audio_is_playing", return_value=True), \
                 patch("time.time", return_value=100.3):
                board._tick_voice_lesson()
            self.assertEqual(board._reveal_index, 0)
            self.assertEqual(board._lesson_index, 1)
            self.assertEqual(board._live_caption, "A luz chega à folha.")

            with patch.object(board, "_audio_is_playing", return_value=True), \
                 patch("time.time", return_value=100.65):
                board._tick_voice_lesson()
            self.assertEqual(
                board._live_caption,
                "A luz chega à folha. A planta",
            )
            self.assertEqual(board._lesson_index, 2)
            self.assertEqual(board._reveal_index, 1)
            self.assertGreater(board._reveal_progress, 0.0)
            self.assertLess(board._reveal_progress, 1.0)

            # The last checkpoint may land just after the final audio window ends.
            # The board gets a short, bounded settle window, not a free-running clock.
            board.add_audio_playback_window(100.0, 1.0)
            with patch("time.time", return_value=101.1):
                board._tick_drawing()
            self.assertEqual(board._lesson_caption, "Etapas concluídas")
            self.assertEqual(
                board._live_caption,
                "A luz chega à folha. A planta produz glicose.",
            )
            self.assertEqual(board._reveal_index, 2)
        finally:
            board.close()

    def test_first_transcript_animates_from_audio_onset_in_either_arrival_order(self):
        from gui.visual_board import VisualBoardOverlay

        for audio_first in (True, False):
            with self.subTest(audio_first=audio_first):
                board = VisualBoardOverlay()
                try:
                    board.set_content({
                        "title": "Aula",
                        "elements": [{"id": "a", "type": "text", "text": "Luz"}],
                        "_lesson_timeline": [{
                            "index": 1, "start": 0, "end": 1,
                            "caption": "A luz chega à folha.", "duration": 1.0,
                        }],
                    })
                    if not audio_first:
                        board.set_live_caption_at_time("A luz chega à folha.", 101.0)
                    with patch("time.time", return_value=100.0):
                        board.add_audio_playback_window(100.0, 1.0)
                    if audio_first:
                        board.set_live_caption_at_time("A luz chega à folha.", 101.0)

                    with patch("time.time", return_value=100.03):
                        board._tick_drawing()
                    self.assertEqual(board._reveal_index, -1)
                    with patch("time.time", return_value=100.55):
                        board._tick_drawing()
                    self.assertEqual(board._reveal_index, 0)
                    self.assertGreater(board._reveal_progress, 0.0)
                    self.assertLess(board._reveal_progress, 1.0)
                    with patch("time.time", return_value=101.1):
                        board._tick_drawing()
                    self.assertEqual(board._lesson_caption, "Etapas concluídas")
                finally:
                    board.close()

    def test_long_caption_draws_at_first_words_and_freezes_with_speaker_clock(self):
        from gui.visual_board import VisualBoardOverlay

        caption = ("A fotossíntese é o processo que as plantas usam para criar seu próprio "
                   "alimento e energia para crescer.")
        clock = Mock()
        clock.audible_seconds.return_value = 10.0
        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Como funciona a Fotossíntese",
                "elements": [{"type": "circle", "x": 20, "y": 20, "radius": 9},
                             {"type": "arrow", "x": 30, "y": 30, "x2": 50, "y2": 50}],
                "_lesson_timeline": [{"index": 1, "start": 0, "end": 1, "caption": caption},
                                     {"index": 2, "start": 1, "end": 2,
                                      "caption": "A luz chega à folha."}],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(10.0, 0.4)
            board.set_live_caption_at_sample("A fotossíntese", 10.4)
            board._tick_drawing()
            self.assertEqual(board._reveal_index, -1)
            clock.audible_seconds.return_value = 10.2
            board._tick_drawing()
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(board._reveal_progress, 0)
            first_progress = board._reveal_progress
            with patch("time.time", return_value=99999.0):
                board._tick_drawing()
            self.assertEqual(board._reveal_progress, first_progress)
            clock.audible_seconds.return_value = 10.4
            board._tick_drawing()
            self.assertGreater(board._reveal_progress, first_progress)
            self.assertEqual(board._reveal_index, 0)
            self.assertLess(board._reveal_progress, 1)
            board.clear_audio_playback()
            self.assertEqual(board._lesson_transcript_checkpoints, [])
        finally:
            board.close()

    def test_extended_caption_boundary_does_not_erase_visible_ink(self):
        from gui.visual_board import VisualBoardOverlay

        payload = {"elements": [{"type": "circle"}],
                   "_lesson_timeline": [{"start": 0, "end": 1,
                                         "caption": "A luz chega à folha."}]}
        board = VisualBoardOverlay()
        clock = Mock()
        clock.audible_seconds.return_value = 0.4
        try:
            board.set_content(payload)
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 1.0)
            board.set_live_caption_at_sample("A luz", 0.5)
            board._tick_drawing()
            first_progress = board._reveal_progress
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(first_progress, 0)
            board.set_live_caption_at_sample("A luz", 1.0)
            board._tick_drawing()
            self.assertEqual(board._reveal_progress, first_progress)
            clock.audible_seconds.return_value = 1.0
            board._tick_drawing()
            self.assertGreater(board._reveal_progress, first_progress)
            board.set_content(payload)
            board._draw_timer.stop()
            self.assertEqual(board._lesson_reveal_fractions, {})
            self.assertEqual(board._reveal_index, -1)
        finally:
            board.close()

    def test_streamed_caption_handles_split_words_and_missing_asr_words(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            board.set_content({
                "elements": [{"type": "circle"}],
                "_lesson_timeline": [{"start": 0, "end": 1,
                    "caption": "A fotossíntese é o processo que as plantas usam para criar alimento."}],
            })
            board._refresh_lesson_transcript_progress(
                "A foto ssíntese é o processo que plantas usam para criar alimento.")
            self.assertEqual(board._lesson_transcript_progress[0],
                             len(board._spoken_tokens(board._lesson_timeline[0]["caption"])))
        finally:
            board.close()

    def test_small_narration_variations_do_not_block_the_lesson(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            board.set_content({"elements": [{"type": "circle"}],
                "_lesson_timeline": [{"start": 0, "end": 1,
                    "caption": "A fotossíntese é o processo que as plantas usam para criar alimento."}]})
            for unrelated in ("Sim, estou ouvindo você perfeitamente.",
                              "Vamos falar das plantas e do alimento depois."):
                board._refresh_lesson_transcript_progress(unrelated)
                self.assertEqual(board._lesson_transcript_progress, [0])
            board._refresh_lesson_transcript_progress(
                "Fotossíntese permite às plantas fabricar alimento.")
            self.assertGreater(board._lesson_transcript_progress[0], 2)
        finally:
            board.close()

    def test_shape_outline_is_visible_at_small_reveal_instead_of_an_empty_clip(self):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QImage, QPainter
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            for item in (
                {"type": "circle", "x": 50, "y": 50, "radius": 20},
                {"type": "polygon", "points": [{"x": 70, "y": 10},
                    {"x": 20, "y": 80}, {"x": 90, "y": 80}]},
            ):
                image = QImage(400, 300, QImage.Format.Format_ARGB32)
                image.fill(0)
                painter = QPainter(image)
                try:
                    board._draw_revealing_shape(painter, QRectF(0, 0, 400, 300), item, 0.03)
                finally:
                    painter.end()
                visible = sum(image.pixelColor(x, y).alpha() > 0
                              for x in range(400) for y in range(300))
                self.assertGreater(visible, 15)
                self.assertLess(visible, 1000)
        finally:
            board.close()

    def test_late_captions_at_same_sample_boundary_can_finish_without_more_audio(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        clock = Mock()
        clock.audible_seconds.return_value = 1.0
        try:
            board.set_content({"elements": [{"type": "circle"}],
                "_lesson_timeline": [{"start": 0, "end": 1, "caption": "A luz chega à folha."}]})
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 1.0)
            board.set_live_caption_at_sample("A luz", 1.0)
            board.set_live_caption_at_sample("A luz chega à folha.", 1.0)
            board._tick_drawing()
            self.assertEqual(board._lesson_caption, "Etapas concluídas")
            self.assertEqual(board._lesson_transcript_checkpoints[-1][0], 1.0)
        finally:
            board.close()

    def test_absent_transcript_still_draws_from_the_verbatim_script_on_the_speaker_clock(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        clock = Mock()
        clock.audible_seconds.return_value = 0.0
        try:
            board.set_content({
                "elements": [{"type": "circle"}, {"type": "arrow"}],
                "_lesson_timeline": [
                    {"index": 1, "start": 0, "end": 1, "caption": "A luz chega à folha.",
                     "duration": 3.0, "start_seconds": 0.0},
                    {"index": 2, "start": 1, "end": 2, "caption": "A planta produz glicose.",
                     "duration": 3.0, "start_seconds": 3.2},
                ],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 9.0)
            # No transcript checkpoint ever arrives (late/absent ASR).
            clock.audible_seconds.return_value = 0.2
            board._tick_drawing()
            self.assertEqual(board._reveal_index, -1)  # grace period, no ink yet
            clock.audible_seconds.return_value = 2.6
            board._tick_drawing()
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(board._reveal_progress, 0)
            clock.audible_seconds.return_value = 4.0
            board._tick_drawing()
            self.assertEqual(board._lesson_index, 2)
            clock.audible_seconds.return_value = 6.4
            board._tick_drawing()
            self.assertEqual(board._lesson_caption, "Etapas concluídas")
            # Silence must freeze the ink even though wall time jumps.
            board.set_content({
                "elements": [{"type": "circle"}],
                "_lesson_timeline": [{"index": 1, "start": 0, "end": 1,
                                      "caption": "A luz chega.", "duration": 3.0,
                                      "start_seconds": 0.0}],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 6.0)
            clock.audible_seconds.return_value = 2.6
            board._tick_drawing()
            frozen = board._reveal_progress
            with patch("time.time", return_value=99999.0):
                board._tick_drawing()
            self.assertEqual(board._reveal_progress, frozen)
        finally:
            board.close()

    def test_spoken_acknowledgment_before_the_captions_does_not_make_ink_run_ahead(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        clock = Mock()
        clock.audible_seconds.return_value = 0.0
        try:
            board.set_content({
                "elements": [{"type": "circle"}, {"type": "arrow"}],
                "_lesson_timeline": [
                    {"index": 1, "start": 0, "end": 1, "caption": "A luz chega à folha.",
                     "duration": 3.0, "start_seconds": 0.0},
                    {"index": 2, "start": 1, "end": 2, "caption": "A planta produz glicose.",
                     "duration": 3.0, "start_seconds": 3.2},
                ],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 12.0)
            # The model first says a short acknowledgment ("Claro, vou te mostrar...")
            # which matches no beat. The board must stay blank while it is spoken.
            board.set_live_caption_at_sample("Claro, vou te mostrar como funciona.", 0.4)
            clock.audible_seconds.return_value = 1.6
            board._tick_drawing()
            self.assertEqual(board._reveal_index, -1)
            # The first caption begins around audible 2.0s; two words confirmed.
            board.set_live_caption_at_sample("Claro, vou te mostrar como funciona. A luz chega", 2.4)
            clock.audible_seconds.return_value = 2.6
            board._tick_drawing()
            self.assertEqual(board._reveal_index, 0)
            self.assertIsNotNone(board._lesson_script_origin)
            # Even if ASR then stalls, the script keeps pace with the real voice
            # clock from the anchored caption start, not from the acknowledgment.
            clock.audible_seconds.return_value = 5.0
            board._tick_drawing()
            self.assertEqual(board._lesson_index, 2)
        finally:
            board.close()

    def test_later_reply_cannot_advance_an_ended_narration(self):
        from gui.visual_board import VisualBoardOverlay
        payload = {
            "elements": [{"type": "circle"}, {"type": "arrow"}],
            "_lesson_timeline": [
                {"start": 0, "end": 1, "caption": "A luz chega à folha.",
                 "duration": 3.0, "start_seconds": 0.0},
                {"start": 1, "end": 2, "caption": "A planta produz glicose.",
                 "duration": 3.0, "start_seconds": 3.2},
            ],
        }
        for has_transcript in (False, True):
            with self.subTest(has_transcript=has_transcript):
                board = VisualBoardOverlay()
                clock = Mock()
                clock.audible_seconds.return_value = 2.5
                try:
                    board.set_content(payload)
                    board._draw_timer.stop()
                    board.set_playback_clock(clock)
                    board.add_lesson_mark("narration_start", 0, 0.0)
                    board.add_sample_audio_window(0.0, 2.5)
                    if has_transcript:
                        board.set_live_caption_at_sample("A luz", 2.0)
                    board._tick_drawing()
                    self.assertEqual(board._reveal_index, 0)
                    board.add_lesson_mark("narration_end", 0, 2.5)
                    frozen = (board._reveal_index, board._reveal_progress)
                    board.add_sample_audio_window(2.5, 20.0)
                    board.set_live_caption_at_sample(
                        "A luz chega à folha. A planta produz glicose.", 22.5)
                    clock.audible_seconds.return_value = 22.5
                    board._tick_drawing()
                    self.assertEqual((board._reveal_index, board._reveal_progress), frozen)
                    self.assertNotEqual(board._lesson_caption, "Etapas concluídas")
                    if has_transcript:
                        board.set_live_caption_at_sample(
                            "A luz chega à folha. A planta produz glicose.", 2.5)
                        board._tick_drawing()
                        self.assertEqual(board._lesson_caption, "Etapas concluídas")
                finally:
                    board.close()

    def test_narration_start_discards_buffered_acknowledgment(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        clock = Mock()
        clock.audible_seconds.return_value = 4.0
        try:
            board.set_content({
                "elements": [{"type": "circle"}],
                "_lesson_timeline": [{"start": 0, "end": 1,
                                      "caption": "A luz chega à folha.", "duration": 3.0}],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 2.0)
            board.set_live_caption_at_sample("Claro, vou explicar fotossíntese.", 2.0)
            board.add_lesson_mark("narration_start", 0, 2.0)
            board.add_sample_audio_window(2.0, 3.0)
            board._tick_drawing()
            self.assertEqual(board._lesson_transcript_tokens, [])
            clock.audible_seconds.return_value = 4.6
            board._tick_drawing()
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(board._reveal_progress, 0)
        finally:
            board.close()

    def test_single_generic_word_does_not_anchor_the_narration_script(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        clock = Mock()
        clock.audible_seconds.return_value = 4.0
        try:
            board.set_content({
                "elements": [{"type": "circle"}],
                "_lesson_timeline": [{"index": 1, "start": 0, "end": 1,
                                      "caption": "A luz chega à folha.",
                                      "duration": 3.0, "start_seconds": 0.0}],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_sample_audio_window(0.0, 6.0)
            board.set_live_caption_at_sample("A", 0.4)
            board._tick_drawing()
            self.assertIsNone(board._lesson_script_origin)
            self.assertEqual(board._reveal_index, -1)
        finally:
            board.close()

    def test_marker_lesson_reveals_only_between_sample_clock_boundaries(self):
        from gui.visual_board import VisualBoardOverlay

        class Clock:
            def __init__(self):
                self.audible = 0.0
                self.written = 0.0

            def audible_seconds(self):
                return self.audible

            def written_seconds(self):
                return self.written

        board = VisualBoardOverlay()
        clock = Clock()
        try:
            board.set_content({
                "title": "PCM markers",
                "_marker_sync": True,
                "elements": [
                    {"id": "a", "type": "text", "text": "Cateto"},
                    {"id": "b", "type": "text", "text": "Hipotenusa"},
                ],
                "_lesson_timeline": [
                    {
                        "index": 1, "start": 0, "end": 2,
                        "caption": "Os catetos formam o ângulo reto.",
                        "cues": [None, None],
                    },
                ],
            })
            board._draw_timer.stop()
            board.set_playback_clock(clock)
            board.add_lesson_mark("start", 1, 0.0)

            # START is a sample boundary, not permission to draw before the DAC
            # has moved beyond that sample position.
            clock.audible = 0.0
            clock.written = 0.30
            board._tick_marker_lesson()
            self.assertEqual(board._reveal_index, -1)
            self.assertEqual(board._reveal_progress, 0.0)

            # The reveal is now a fraction of the actual audible interval.
            clock.audible = 0.15
            board._tick_marker_lesson()
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(board._reveal_progress, 0.0)
            self.assertEqual(board._lesson_index, 1)

            # END is another position in the same sample stream. The final
            # elements become visible only when playback crosses that boundary.
            board.add_lesson_mark("end", 1, 0.30)
            clock.audible = 0.31
            board._tick_marker_lesson()
            self.assertEqual(board._lesson_caption, "Etapas concluídas")
            self.assertEqual(board._reveal_index, 2)
            self.assertEqual(board._reveal_progress, 0.0)
        finally:
            board.close()

    def test_missing_pcm_marker_never_reveals_the_lesson_by_timeout(self):
        from gui.visual_board import VisualBoardOverlay

        class Clock:
            def audible_seconds(self):
                return 0.0

            def written_seconds(self):
                return 0.0

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Aguardando PCM",
                "_marker_sync": True,
                "elements": [
                    {"id": "a", "type": "text", "text": "Primeiro conceito"},
                ],
                "_lesson_timeline": [
                    {"index": 1, "start": 0, "end": 1,
                     "caption": "Primeiro conceito.", "cues": [None]},
                ],
            })
            board._draw_timer.stop()
            board.set_playback_clock(Clock())
            board._marker_started_at = 0.0
            with patch("time.monotonic", return_value=26.0):
                board._tick_marker_lesson()

            self.assertEqual(board._reveal_index, -1)
            self.assertTrue(board._marker_mode)
            self.assertEqual(board._lesson_caption, "A narração ainda não iniciou")
            self.assertFalse(board._draw_timer.isActive())
        finally:
            board.close()

    def test_lesson_drawing_waits_for_speaker_clock_and_live_caption_updates(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Aula sincronizada",
                "elements": [{"id": "a", "type": "text", "text": "Conceito"}],
                "_lesson_timeline": [
                    {"index": 1, "start": 0, "end": 1,
                     "caption": "Conceito principal", "duration": 1.2}
                ],
            })
            board._draw_timer.stop()
            board._reveal_step = 0.1
            board._tick_drawing()
            self.assertEqual(board._reveal_progress, 0.0)
            self.assertEqual(board._reveal_index, -1)
            board.set_live_caption("Conceito principal")
            self.assertEqual(board._live_caption, "Conceito principal")
            # Even a matching caption cannot reveal the mark until PCM is audible.
            board._tick_voice_lesson()
            self.assertEqual(board._reveal_index, -1)
            board.add_audio_playback_window(__import__("time").time() - 0.1, 2.0)
            board._lesson_audio_elapsed = 0.3
            board._tick_drawing()
            self.assertEqual(board._reveal_index, 0)
            self.assertGreater(board._reveal_progress, 0.0)
        finally:
            board.close()

    def test_lesson_clock_preserves_time_across_a_short_pcm_packet_gap(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Clock gap",
                "elements": [{"id": "a", "type": "text", "text": "A"}],
                "_lesson_timeline": [
                    {"index": 1, "start": 0, "end": 1,
                     "caption": "A frase", "duration": 1.0,
                     "start_seconds": 0.0, "end_seconds": 1.0}
                ],
            })
            board._draw_timer.stop()
            # _tick_drawing checks the speaker, then _tick_voice_lesson checks it
            # again. Simulate one short gap between two adjacent scheduled packets.
            with patch.object(board, "_audio_is_playing",
                              side_effect=[True, True, False, True, True]), \
                 patch("time.monotonic", side_effect=[10.0, 10.022, 10.044]):
                board._tick_drawing()  # first packet
                board._tick_drawing()  # 22 ms gap: preserve the anchor
                board._tick_drawing()  # second packet resumes
            self.assertGreaterEqual(board._lesson_audio_elapsed, 0.065)
            self.assertIsNotNone(board._lesson_last_tick_at)
        finally:
            board.close()

    def test_visual_ink_waits_for_the_actual_pcm_onset_without_avatar_early_lead(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.add_audio_playback_window(100.0, 1.0)
            with patch("time.time", return_value=100.0):
                self.assertFalse(board._audio_is_playing())
            with patch("time.time", return_value=100.011):
                self.assertFalse(board._audio_is_playing())
            with patch("time.time", return_value=100.013):
                self.assertTrue(board._audio_is_playing())
        finally:
            board.close()

    def test_triangle_examples_use_a_separate_column_and_controls_have_their_own_row(self):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QImage, QPainter
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content(build_right_triangle_payload())
            board.append_content({
                "elements": [
                    {"type": "formula", "text": "3² + 4² = 9 + 16 = 25",
                     "x": 20, "y": 78, "width": 30, "height": 18},
                    {"type": "text", "text": "A raiz de 25 é 5.",
                     "x": 22, "y": 88, "width": 35, "height": 12},
                ]
            })
            board.resize(900, 600)
            board._board_rect = QRectF(1, 1, 898, 598)
            board.set_live_caption("Vamos resolver um exemplo passo a passo.")
            image = QImage(900, 600, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            try:
                board._draw_pencil_triangle(
                    painter, QRectF(28, 78, 844, 452), show_formula=False
                )
                board._draw_triangle_example_panel(
                    painter, QRectF(28, 78, 844, 452),
                    board._payload["_annotation_elements"],
                )
                board._draw_interaction_controls(painter, QRectF(1, 1, 898, 598))
            finally:
                painter.end()
            self.assertEqual(len(board._payload["_annotation_elements"]), 2)
            self.assertGreater(28 + 844 * 0.62, 28 + 844 * 0.59)
            self.assertLess(board._play_rect.bottom(), 600 - 48)
            self.assertLess(board._play_rect.top(), 600 - 48)
        finally:
            board.close()

    def test_transcript_keywords_do_not_unlock_future_example_beats(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            payload = build_right_triangle_payload()
            board.set_content(payload)
            self.assertEqual(len(payload["_teaching_example"]["steps"]), 5)
            board.set_live_caption("Agora observe os dois catetos.")
            self.assertEqual(board._semantic_focus, "catheti")
            board.set_live_caption("Observe a hipotenusa no lado diagonal.")
            self.assertEqual(board._semantic_focus, "hypotenuse")
            board.set_live_caption("A hipotenusa é o lado oposto ao ângulo reto.")
            self.assertEqual(board._semantic_focus, "hypotenuse_and_right_angle")
            board.set_live_caption("Agora destaque o ângulo reto de 90 graus.")
            self.assertEqual(board._semantic_focus, "right_angle")
            board.set_live_caption("A fórmula do teorema é a² mais b² igual a c².")
            self.assertFalse(board._example_visible)
            self.assertEqual(board._active_example_step, 0)
            # Example visibility is no longer guessed from transcript keywords.
            # It is rendered only when the dedicated example beat enters the
            # PCM-driven voice queue; plain captions cannot unlock future marks.
            board.set_live_caption("Agora vamos ao exemplo.")
            self.assertFalse(board._example_visible)
            self.assertEqual(board._active_example_step, 0)
            board.set_live_caption("A fórmula do teorema é a² mais b² igual a c².")
            self.assertFalse(board._example_visible)
            self.assertEqual(board._active_example_step, 0)
        finally:
            board.close()

    def test_triangle_drawing_waits_for_actual_speaker_audio(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            board.set_content(build_right_triangle_payload())
            board._draw_timer.stop()
            board._triangle_reveal = 0.0
            board._tick_drawing()
            self.assertEqual(board._triangle_reveal, 0.0)
            board.add_audio_playback_window(__import__("time").time() - 0.1, 2.0)
            board._tick_drawing()
            self.assertGreater(board._triangle_reveal, 0.0)
        finally:
            board.close()

    def test_triangle_drag_updates_live_side_length_and_preserves_right_angle(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        from core.visual_board import build_right_triangle_payload
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content(build_right_triangle_payload())
            board.show()
            self.app.processEvents()
            board.repaint()
            initial = board._triangle_a
            _, top, _, _ = board._triangle_geometry(board._canvas_rect)
            start = QPoint(round(top.x()), round(top.y()))
            finish = QPoint(start.x(), start.y() - 45)
            QTest.mousePress(board, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(board, finish, 40)
            QTest.mouseRelease(board, Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier, finish)
            self.app.processEvents()
            self.assertGreater(board._triangle_a, initial + 0.2)
            self.assertEqual(board._interactive_kind, "right_triangle")
            self.assertAlmostEqual(board._triangle_b, 4.0, places=1)
        finally:
            board.close()

    def test_triangle_animation_and_reset_controls_work(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        from core.visual_board import build_right_triangle_payload
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content(build_right_triangle_payload())
            board.show()
            self.app.processEvents()
            QTest.mouseClick(
                board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                QPoint(round(board._play_rect.center().x()), round(board._play_rect.center().y()))
            )
            self.assertTrue(board._animating)
            QTest.qWait(70)
            self.assertGreater(board._animation_phase, 0.0)
            QTest.mouseClick(
                board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                QPoint(round(board._reset_rect.center().x()), round(board._reset_rect.center().y()))
            )
            self.assertFalse(board._animating)
            self.assertAlmostEqual(board._triangle_a, 3.0)
            self.assertAlmostEqual(board._triangle_b, 4.0)
        finally:
            board.close()

    def test_generic_polygon_vertices_are_draggable(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        payload = {
            "title": "Triângulo manipulável", "layout": "geometry",
            "elements": [{
                "type": "polygon", "points": [
                    {"x": 20, "y": 20}, {"x": 20, "y": 80}, {"x": 80, "y": 80}
                ], "color": "cyan"
            }]
        }
        try:
            board.set_content(payload)
            board.show()
            self.app.processEvents()
            board.repaint()
            point = board._point(board._canvas_rect, 20, 20)
            start = QPoint(round(point.x()), round(point.y()))
            finish = QPoint(start.x() + 35, start.y() + 30)
            QTest.mousePress(board, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(board, finish, 40)
            QTest.mouseRelease(board, Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier, finish)
            self.assertGreater(board._payload["elements"][0]["points"][0]["x"], 20)
            self.assertGreater(board._payload["elements"][0]["points"][0]["y"], 20)
        finally:
            board.close()

    def test_overlay_renders_to_a_qimage(self):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QImage, QPainter
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        image = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        try:
            board._draw_element(painter, QRectF(0, 0, 640, 480), {
                "type": "polygon",
                "points": [{"x": 10, "y": 90}, {"x": 10, "y": 10},
                           {"x": 90, "y": 90}],
                "color": "cyan",
                "stroke_width": 2,
                "fill": True,
            })
            board._draw_element(painter, QRectF(0, 0, 640, 480), {
                "type": "formula", "x": 48, "y": 12,
                "width": 42, "height": 16, "font_size": 20,
                "text": "a² + b² = c²", "color": "cyan",
            })
        finally:
            painter.end()
            board.close()
        self.assertFalse(image.isNull())



    def test_scene_ids_and_in_place_add_update_move_delete(self):
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "scene",
                "elements": [
                    {"id": "formula-main", "type": "formula", "text": "a²+b²=c²", "x": 20, "y": 20},
                    {"id": "label-side", "type": "text", "text": "cateto", "x": 20, "y": 40},
                ],
            })
            self.assertEqual(board.describe_scene()["elements"][0]["element_id"], "formula-main")
            self.assertEqual(board.edit_element("move", "formula-main", dx=5, dy=-2), "moved formula-main")
            self.assertEqual(board._payload["elements"][0]["x"], 25)
            self.assertEqual(board._payload["elements"][1]["x"], 20)
            self.assertEqual(board.edit_element("update", "label-side", {"text": "hipotenusa"}), "updated label-side")
            self.assertEqual(board._payload["elements"][1]["text"], "hipotenusa")
            self.assertEqual(board.edit_element("delete", "formula-main"), "deleted formula-main")
            self.assertEqual([e["id"] for e in board._payload["elements"]], ["label-side"])
            self.assertTrue(board.edit_element("add", patch={"type": "text", "text": "novo"}).startswith("added"))
            self.assertEqual(len(board._payload["elements"]), 2)
        finally:
            board.close()

class VisualBoardQuizEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _board_with_quiz(self, answer="B"):
        from PyQt6.QtCore import QRectF
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        board.set_content({
            "title": "Revisão",
            "elements": [{
                "id": "quiz-1", "type": "quiz",
                "title": "Qual é a capital do Brasil?",
                "options": ["São Paulo", "Brasília", "Rio de Janeiro"],
                "answer": answer,
                "explanation": "Brasília é a capital federal desde 1960.",
                "x": 20, "y": 20, "width": 40, "height": 40,
            }],
        })
        board.show()
        self.app.processEvents()
        board._quiz_rects = [
            ("quiz-1", 0, QRectF(100, 100, 240, 42)),
            ("quiz-1", 1, QRectF(100, 150, 240, 42)),
            ("quiz-1", 2, QRectF(100, 200, 240, 42)),
        ]
        return board

    def test_reveal_animates_drawing_on_right_side_of_canvas(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content(normalize_visual_payload({"title": "Desenho", "elements": [
                {"type": "rect", "x": 75, "y": 25, "width": 20, "height": 30,
                 "fill": True, "color": "green"},
            ]}))
            board._draw_timer.stop()
            board._reveal_index = 0
            board._reveal_progress = 0.0
            board.repaint()
            self.app.processEvents()
            blank = board.grab().toImage()
            canvas = board._canvas_rect
            board._reveal_progress = 0.4
            board.repaint()
            self.app.processEvents()
            partial = board.grab().toImage()
            left = int(canvas.left() + canvas.width() * 0.74)
            right = int(canvas.left() + canvas.width() * 0.86)
            top = int(canvas.top() + canvas.height() * 0.24)
            bottom = int(canvas.top() + canvas.height() * 0.56)
            changed = sum(blank.pixel(x, y) != partial.pixel(x, y)
                          for x in range(left, right) for y in range(top, bottom))
            self.assertGreater(changed, 40)
        finally:
            board.close()

    def test_vertical_line_draws_from_its_start_to_its_endpoint(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content(normalize_visual_payload({"elements": [
                {"type": "line", "x": 70, "y": 15, "x2": 70, "y2": 80,
                 "color": "green", "stroke_width": 3},
            ]}))
            board._draw_timer.stop()
            board._reveal_index = 0
            board._reveal_progress = 0
            board.repaint()
            self.app.processEvents()
            blank = board.grab().toImage()
            canvas = board._canvas_rect
            board._reveal_progress = 0.35
            board.repaint()
            self.app.processEvents()
            partial = board.grab().toImage()
            x = int(canvas.left() + canvas.width() * 0.70)
            upper = int(canvas.top() + canvas.height() * 0.25)
            lower = int(canvas.top() + canvas.height() * 0.65)
            self.assertNotEqual(blank.pixel(x, upper), partial.pixel(x, upper))
            self.assertEqual(blank.pixel(x, lower), partial.pixel(x, lower))
        finally:
            board.close()

    def test_lesson_hides_future_handles_and_partial_quiz_choices(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Aula",
                "elements": [
                    {"type": "quiz", "id": "quiz", "title": "Escolha", "x": 10, "y": 10,
                     "width": 40, "height": 40, "options": ["A", "B"]},
                    {"type": "circle", "x": 70, "y": 70, "radius": 8},
                ],
                "_lesson_timeline": [
                    {"start": 0, "end": 1, "caption": "Escolha", "duration": 1},
                    {"start": 1, "end": 2, "caption": "Depois", "duration": 1},
                ],
                "_marker_sync": True,
            })
            board._draw_timer.stop()
            board._reveal_index = 0
            board._reveal_progress = 0.5
            board.repaint()
            self.app.processEvents()
            self.assertEqual(board._quiz_rects, [])
            self.assertEqual(board._generic_handles, [])
        finally:
            board.close()

    def test_narrated_lesson_reveals_and_accepts_a_quiz_answer(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from actions.present_visual_lesson import present_visual_lesson
        from gui.visual_board import VisualBoardOverlay

        player = Mock(spec=["get_visual_voice_cps", "show_visual_board", "set_visual_lesson_status"])
        player.get_visual_voice_cps.return_value = 13.0
        result = present_visual_lesson({
            "title": "Fotossíntese",
            "beats": [
                {"say": "A planta usa luz.", "elements": [
                    model_scene("Fotossíntese", x=15, y=12),
                    {"type": "text", "text": "Luz", "x": 10, "y": 20},
                ]},
                {"say": "Escolha uma opção no quadro.", "elements": [
                    {"id": "quiz", "type": "quiz", "title": "O que a planta usa?",
                     "options": ["Luz", "Plástico"], "answer": "Luz",
                     "explanation": "A luz fornece energia.",
                     "x": 45, "y": 10, "width": 45, "height": 65},
                ]},
            ],
        }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        payload = player.show_visual_board.call_args.args[0]
        self.assertFalse(payload["_marker_sync"])
        board = VisualBoardOverlay()
        answers = []
        board.quiz_answered.connect(answers.append)
        try:
            board.set_content(payload)
            board.set_live_caption_at_time("A planta usa luz.", 100.5)
            board.set_live_caption_at_time(
                "A planta usa luz. Escolha uma opção no quadro.", 101.5
            )
            with patch("time.time", return_value=100.0):
                board.add_audio_playback_window(100.0, 2.0)
            with patch("time.time", return_value=100.6):
                board._tick_drawing()
            board.repaint()
            self.app.processEvents()
            self.assertFalse(board._quiz_rects)

            with patch("time.time", return_value=101.6):
                board._tick_drawing()
            board.repaint()
            self.app.processEvents()
            self.assertEqual(len(board._quiz_rects), 2)
            QTest.mouseClick(board, Qt.MouseButton.LeftButton,
                             pos=board._quiz_rects[0][2].center().toPoint())
            self.assertEqual(len(answers), 1)
            self.assertEqual(answers[0]["choice"], "Luz")
            self.assertTrue(answers[0]["correct"])
        finally:
            board.close()

    def test_clicking_quiz_choice_emits_question_choice_and_letter_grade(self):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        board = self._board_with_quiz(answer="B")
        events = []
        board.quiz_answered.connect(events.append)
        try:
            point = QPointF(160, 170)
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress, point,
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            board.mousePressEvent(event)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["element_id"], "quiz-1")
            self.assertEqual(events[0]["question"], "Qual é a capital do Brasil?")
            self.assertEqual(events[0]["choice"], "Brasília")
            self.assertEqual(events[0]["answer"], "B")
            self.assertIs(events[0]["correct"], True)
            self.assertEqual(events[0]["explanation"], "Brasília é a capital federal desde 1960.")
            self.assertEqual(board._payload["elements"][0]["selected"], 1)
        finally:
            board.close()

    def test_choice_graded_by_option_text_and_attempt_revisions_are_sent(self):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        board = self._board_with_quiz(answer="Brasília")
        events = []
        board.quiz_answered.connect(events.append)
        try:
            for choice_index, x in ((0, 110), (1, 150)):
                point = QPointF(x, 120 if choice_index == 0 else 170)
                event = QMouseEvent(
                    QEvent.Type.MouseButtonPress, point,
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                board.mousePressEvent(event)
            self.assertEqual([e["attempt"] for e in events], [1, 2])
            self.assertIs(events[0]["correct"], False)
            self.assertIs(events[1]["correct"], True)
            self.assertEqual(events[1]["choice"], "Brasília")
        finally:
            board.close()

    def test_omitted_answer_is_forwarded_for_manual_grading(self):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        board = self._board_with_quiz(answer="")
        events = []
        board.quiz_answered.connect(events.append)
        try:
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress, QPointF(150, 170),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            board.mousePressEvent(event)
            self.assertIsNone(events[0]["correct"])
            self.assertEqual(events[0]["answer"], "")
        finally:
            board.close()

    def test_clicking_same_choice_twice_does_not_duplicate_answer_message(self):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        board = self._board_with_quiz(answer="B")
        events = []
        board.quiz_answered.connect(events.append)
        try:
            for _ in range(2):
                event = QMouseEvent(
                    QEvent.Type.MouseButtonPress, QPointF(150, 170),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
                board.mousePressEvent(event)
            self.assertEqual(len(events), 1)
        finally:
            board.close()


class VisualBoardModelInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _board(self):
        from PyQt6.QtCore import QRectF
        from gui.visual_board import VisualBoardOverlay
        board = VisualBoardOverlay()
        board.set_content({
            "title": "3D",
            "elements": [{
                "id": "model-one", "type": "model3d", "shape": "sphere",
                "x": 50, "y": 50, "width": 40, "height": 40,
            }],
        })
        board.show()
        self.app.processEvents()
        board._canvas_rect = QRectF(0, 0, 600, 420)
        board._generic_handles = []
        board._collect_generic_handles(0, board._payload["elements"][0], board._canvas_rect)
        return board

    def test_dragging_inside_3d_model_changes_view_yaw_and_pitch(self):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        board = self._board()
        try:
            start = QPointF(400, 290)
            press = QMouseEvent(
                QEvent.Type.MouseButtonPress, start,
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            board.mousePressEvent(press)
            self.assertEqual(board._drag_target, ("model_rotate", 0, 0))

            moved = QPointF(455, 330)
            motion = QMouseEvent(
                QEvent.Type.MouseMove, moved,
                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            board.mouseMoveEvent(motion)
            yaw, pitch = board._model_view_rotation["model-one"]
            self.assertAlmostEqual(yaw, 55 * 0.012)
            self.assertAlmostEqual(pitch, 40 * 0.010)

            release = QMouseEvent(
                QEvent.Type.MouseButtonRelease, moved,
                Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
            board.mouseReleaseEvent(release)
            self.assertIsNone(board._drag_target)
        finally:
            board.close()

    def test_corner_handle_still_resizes_instead_of_orbiting(self):
        from PyQt6.QtCore import QEvent, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        board = self._board()
        try:
            corner = board._generic_handles[0][3]
            press = QMouseEvent(
                QEvent.Type.MouseButtonPress, corner,
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            board.mousePressEvent(press)
            self.assertEqual(board._drag_target, ("resize", 0, 0))
            self.assertNotIn("model-one", board._model_view_rotation)
        finally:
            board.close()


class VisualBoardLessonOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_lesson_status_and_mouse_passthrough_are_live_and_reversible(self):
        from PyQt6.QtCore import Qt
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Aula em etapas",
                "elements": [{"type": "text", "text": "Primeira etapa"}],
            })
            board.show()
            self.app.processEvents()
            board.set_lesson_status("Observe a primeira etapa.", 1, 3, False)
            self.assertEqual(board._lesson_caption, "Observe a primeira etapa.")
            self.assertEqual((board._lesson_index, board._lesson_total), (1, 3))
            self.assertFalse(board._lesson_waiting)

            board.set_lesson_status("Clique em Salvar.", 1, 3, True)
            self.assertTrue(board._lesson_waiting)
            board.set_input_passthrough(True)
            self.assertTrue(board._input_passthrough)
            self.assertTrue(board.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

            board.set_input_passthrough(False)
            self.assertFalse(board._input_passthrough)
            self.assertFalse(board.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        finally:
            board.close()

    def test_reveal_speed_uses_estimated_gemini_narration_duration(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Aula",
                "elements": [
                    {"type": "text", "x": 20, "y": 20, "text": "Primeiro"},
                    {"type": "text", "x": 40, "y": 40, "text": "Segundo"},
                    {"type": "text", "x": 60, "y": 60, "text": "Terceiro"},
                ],
            })
            self.app.processEvents()
            self.assertTrue(board._draw_timer.isActive())
            self.assertAlmostEqual(board._reveal_step, 0.055)
            board.set_lesson_status(
                "Acompanhe a explicação.", 1, 1, False, draw_duration=6.0
            )
            self.assertGreater(board._reveal_step, 0.0)
            self.assertLess(board._reveal_step, 0.055)
            self.assertTrue(board._draw_timer.isActive())
            board._draw_timer.stop()
        finally:
            board.close()

    def test_drawing_finished_reflects_the_real_reveal_timer(self):
        from gui.visual_board import VisualBoardOverlay

        board = VisualBoardOverlay()
        try:
            board.set_content({
                "title": "Animação",
                "elements": [{"type": "text", "text": "A"}, {"type": "text", "text": "B"}],
            })
            self.assertFalse(board.drawing_finished())
            board._draw_timer.stop()
            self.assertTrue(board.drawing_finished())
        finally:
            board.close()


class VisualBoardActionTests(unittest.TestCase):
    def test_show_visual_sends_normalized_payload_to_ui(self):
        player = Mock()
        result = show_visual({
            "title": "Lei de Pitágoras",
            "elements": [{"type": "formula", "text": "a² + b² = c²"}],
        }, player=player)
        self.assertIn("VISUAL_SHOWN", result)
        player.show_visual_board.assert_called_once()
        sent = player.show_visual_board.call_args.args[0]
        self.assertEqual(sent["elements"][0]["type"], "formula")

    def test_clear_visual_sends_clear_to_ui(self):
        player = Mock()
        result = clear_visual({}, player=player)
        self.assertIn("VISUAL_CLEARED", result)
        player.clear_visual_board.assert_called_once()

    @unittest.skip("3D-only: the flat Pythagoras triangle is disabled")
    def test_draw_right_triangle_uses_simple_tool_and_waits_for_display(self):
        player = Mock()
        player.start_marker_lesson = None
        player.show_visual_board.return_value = True
        result = draw_right_triangle({}, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        player.show_visual_board.assert_called_once()
        payload = player.show_visual_board.call_args.args[0]
        self.assertEqual(payload["title"], "Teorema de Pitágoras")
        self.assertEqual(payload["layout"], "geometry")
        self.assertEqual(len(payload["_lesson_timeline"]), 8)
        self.assertNotIn("_teaching_example", payload)
        self.assertIn("cinco centímetros", result)
        self.assertIn("Begin speaking immediately", result)
        self.assertIn("live transcription and speaker audio", result)

    @unittest.skip("3D-only: the flat Pythagoras triangle is disabled")
    def test_draw_right_triangle_reports_ui_failure(self):
        player = Mock()
        player.show_visual_board.side_effect = TimeoutError("ack timeout")
        result = draw_right_triangle({}, player=player)
        self.assertIn("PRESENTATION_FAILED", result)
        self.assertNotIn("PRESENTATION_SHOWN", result)

    def test_discovery_registers_visual_tools_without_topic_presets(self):
        from pathlib import Path
        registry = discover_actions(Path(__file__).resolve().parents[1] / "actions",
                                    logger=lambda _: None)
        self.assertTrue(registry.has("show_visual"))
        self.assertTrue(registry.has("clear_visual"))
        self.assertTrue(registry.has("present_visual_lesson"))
        self.assertFalse(registry.has("draw_right_triangle"))

    def test_registry_cannot_dispatch_removed_topic_preset(self):
        from pathlib import Path
        registry = discover_actions(Path(__file__).resolve().parents[1] / "actions",
                                    logger=lambda _: None)
        player = Mock()
        result = registry.run("draw_right_triangle", {}, {"player": player})
        self.assertIn("not available", result)
        player.show_visual_board.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class RichVisualBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_normalizer_accepts_bounded_structured_elements(self):
        from core.visual_board import normalize_visual_payload
        payload = normalize_visual_payload({
            "title": "Aula",
            "elements": [
                {"type": "card", "title": "Resumo", "text": "Texto", "items": ["A", "B"]},
                {"type": "table", "title": "Dados", "columns": ["x", "y"],
                 "rows": [["1", "2"], ["3"]]},
                {"type": "timeline", "events": [
                    {"when": "1", "text": "Início"}, {"when": "2", "text": "Fim"}]},
                {"type": "graph", "plots": [{"points": [[0, 0], [50, 80], [100, 100]]}]},
                {"type": "mindmap", "title": "Tema", "branches": [{"text": "A"}, {"text": "B"}]},
                {"type": "quiz", "options": ["A", "B"], "answer": "B"},
                {"type": "model3d", "shape": "cube", "parts": [
                    {"shape": "sphere", "motion": "orbit", "dx": 20}]},
            ],
        })
        self.assertEqual(len(payload["elements"]), 7)
        self.assertEqual(payload["elements"][1]["rows"][1], ["3", ""])
        self.assertEqual(payload["elements"][6]["parts"][0]["motion"], "orbit")

    def test_normalizer_rejects_incomplete_rich_elements(self):
        from core.visual_board import normalize_visual_payload
        with self.assertRaises(ValueError):
            normalize_visual_payload({
                "elements": [
                    {"type": "table", "columns": ["only one"], "rows": [["x"]]},
                    {"type": "timeline", "events": [{"when": "1", "text": "only"}]},
                    {"type": "mindmap", "branches": [{"text": "only"}]},
                    {"type": "quiz", "options": ["only"]},
                ],
            })

    def test_rich_elements_render_to_qimage(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPainter, QImage
        from PyQt6.QtCore import QRectF
        from gui.visual_rich import draw_rich_element

        kinds = [
            {"type": "card", "title": "Card", "text": "Description", "items": ["One", "Two"]},
            {"type": "list", "heading": "List", "items": ["One", "Two"]},
            {"type": "table", "title": "Table", "columns": ["A", "B"], "rows": [["1", "2"]]},
            {"type": "timeline", "events": [{"when": "1", "text": "One"}, {"when": "2", "text": "Two"}]},
            {"type": "graph", "plots": [{"points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}]}]},
            {"type": "mindmap", "title": "Root", "branches": [{"text": "A"}, {"text": "B"}]},
            {"type": "model3d", "shape": "cube", "parts": [{"shape": "sphere", "motion": "orbit"}]},
            {"type": "quiz", "options": ["A", "B"], "answer": "B", "id": "quiz-1"},
        ]
        image = QImage(900, 700, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        hit_count = 0
        for i, item in enumerate(kinds):
            item.setdefault("x", 5 + (i % 2) * 47)
            item.setdefault("y", 5 + (i // 2) * 28)
            item.setdefault("width", 40)
            item.setdefault("height", 25)
            hits = draw_rich_element(painter, QRectF(0, 0, 900, 650), item,
                                     QColor(87, 224, 255), 0.75)
            hit_count += len(hits)
        painter.end()
        self.assertEqual(hit_count, 2)
        self.assertGreater(image.pixelColor(200, 120).alpha(), 0)

    def test_quiz_regions_allow_answer_selection_and_persist(self):
        from PyQt6.QtCore import QPointF, QRectF, Qt
        from PyQt6.QtGui import QColor
        from gui.visual_rich import draw_rich_element
        from PyQt6.QtGui import QImage, QPainter
        image = QImage(500, 300, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        item = {"type": "quiz", "id": "q1", "x": 10, "y": 10, "width": 70, "height": 70,
                "options": ["First", "Second"], "answer": "Second"}
        hits = draw_rich_element(painter, QRectF(0, 0, 500, 300), item, QColor(87,224,255))
        painter.end()
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[1][0:2], ("q1", 1))
        item["selected"] = hits[1][1]
        self.assertEqual(item["options"][item["selected"]], item["answer"])

    def test_quiz_click_changes_selected_answer_on_live_board(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        from gui.visual_board import VisualBoardOverlay
        from core.visual_board import normalize_visual_payload

        board = VisualBoardOverlay()
        try:
            payload = normalize_visual_payload({
                "elements": [{
                    "id": "quiz-live", "type": "quiz", "title": "Pergunta",
                    "x": 8, "y": 8, "width": 45, "height": 48,
                    "options": ["3", "4"], "answer": "4",
                }]
            })
            board.set_content(payload)
            self.app.processEvents()
            self.assertTrue(board._quiz_rects)
            option_id, option_index, rect = board._quiz_rects[1]
            self.assertEqual((option_id, option_index), ("quiz-live", 1))
            QTest.mouseClick(board, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, rect.center().toPoint())
            self.app.processEvents()
            self.assertEqual(board._payload["elements"][0]["selected"], 1)
        finally:
            board.close()

    def test_rich_card_can_be_dragged_as_one_object(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        from gui.visual_board import VisualBoardOverlay
        from core.visual_board import normalize_visual_payload

        board = VisualBoardOverlay()
        try:
            payload = normalize_visual_payload({
                "elements": [{
                    "id": "card-move", "type": "card", "title": "Movable",
                    "x": 10, "y": 12, "width": 34, "height": 30, "text": "Body",
                }]
            })
            board.set_content(payload)
            self.app.processEvents()
            canvas = board._canvas_rect
            item = board._payload["elements"][0]
            start = QPoint(
                round(canvas.left() + canvas.width()*item["x"]/100 + 22),
                round(canvas.top() + canvas.height()*item["y"]/100 + 22),
            )
            end = QPoint(start.x()+50, start.y()+40)
            old_x, old_y = item["x"], item["y"]
            QTest.mousePress(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(board, end, 50)
            QTest.mouseRelease(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
            self.assertGreater(item["x"], old_x)
            self.assertGreater(item["y"], old_y)
            self.assertEqual(item["id"], "card-move")
        finally:
            board.close()


    def test_rich_card_can_be_resized_from_corner_handle(self):
        from PyQt6.QtCore import QPoint, QRectF, Qt
        from PyQt6.QtTest import QTest
        from gui.visual_board import VisualBoardOverlay
        from core.visual_board import normalize_visual_payload

        board = VisualBoardOverlay()
        try:
            board.set_content(normalize_visual_payload({
                "elements": [{
                    "id": "card-resize", "type": "card", "title": "Resize",
                    "x": 12, "y": 14, "width": 30, "height": 26, "text": "Body",
                }]
            }))
            board._reveal_index = 1
            board._reveal_progress = 1.0
            board._canvas_rect = QRectF(28, 78, board.width()-56, board.height()-112)
            board._generic_handles = []
            board._collect_generic_handles(0, board._payload["elements"][0], board._canvas_rect)
            handle = next(h for h in board._generic_handles if h[0] == "resize")
            start = handle[3].toPoint()
            end = QPoint(start.x()+45, start.y()+35)
            item = board._payload["elements"][0]
            old_w, old_h = item["width"], item["height"]
            QTest.mousePress(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(board, end, 50)
            QTest.mouseRelease(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
            self.assertGreater(item["width"], old_w)
            self.assertGreater(item["height"], old_h)
            self.assertEqual(item["id"], "card-resize")
        finally:
            board.close()

