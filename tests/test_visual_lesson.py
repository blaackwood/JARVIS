import unittest
from unittest.mock import Mock, patch

from actions.present_visual_lesson import (
    TOOL, _wait_for_click, _wait_for_drawing, present_visual_lesson,
)
from actions.draw_right_triangle import draw_right_triangle


def beat(text, x=20):
    return {
        "say": text,
        "elements": [{"type": "text", "x": x, "y": 25, "text": text}],
    }



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

def diagram_beat(text, x=20):
    result = beat(text, x)
    result["elements"].append(model_scene(text[:24], x=2, y=3))
    return result


class VisualLessonActionTests(unittest.TestCase):
    def player(self):
        p = Mock()
        p.start_marker_lesson = None
        p.visual_animation_done.return_value = True
        p.get_visual_voice_cps.return_value = 12.0
        return p

    def test_two_beats_are_prepared_together_for_gemini_narration(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Fotossíntese",
            "beats": [diagram_beat("A luz chega à folha.", 20), beat("A planta produz glicose.", 70)],
        }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        self.assertIn("Gemini Live voice", result)
        self.assertIn("A luz chega à folha.", result)
        self.assertIn("A planta produz glicose.", result)
        player.show_visual_board.assert_called_once()
        payload = player.show_visual_board.call_args.args[0]
        self.assertEqual(len(payload["elements"]), 3)
        self.assertEqual(
            [item["text"] for item in payload["elements"] if item["type"] == "text"],
            ["A luz chega à folha.", "A planta produz glicose."],
        )
        self.assertEqual(player.show_visual_board.call_args.kwargs["operation"], "replace")
        timeline = payload["_lesson_timeline"]
        self.assertEqual([item["index"] for item in timeline], [1, 2])
        self.assertEqual([(item["start"], item["end"]) for item in timeline], [(0, 2), (2, 3)])
        self.assertEqual([item["caption"] for item in timeline],
                         ["A luz chega \u00e0 folha.", "A planta produz glicose."])
        self.assertTrue(all(item["duration"] > 0 for item in timeline))
        self.assertTrue(all(item["voice_cps"] == 12.0 for item in timeline))
        self.assertAlmostEqual(timeline[0]["duration"], max(1.2, len(timeline[0]["caption"]) / 12.0) * 1.12)
        self.assertAlmostEqual(timeline[0]["start_seconds"], 0.0)
        self.assertAlmostEqual(
            timeline[1]["start_seconds"],
            timeline[0]["end_seconds"] + (1.0 / 12.0),
        )
        self.assertAlmostEqual(
            timeline[1]["end_seconds"] - timeline[1]["start_seconds"],
            timeline[1]["duration"],
        )
        player.set_visual_lesson_status.assert_called_once()
        self.assertGreater(player.set_visual_lesson_status.call_args.kwargs["draw_duration"], 0)
        # Return to Gemini immediately; Qt continues its reveal while Live speaks.
        player.visual_animation_done.assert_not_called()

    def test_screen_only_bridge_returns_captions_without_a_preparation_handler(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Fotossíntese",
            "beats": [diagram_beat("A luz chega à folha."), beat("A planta produz glicose.")],
        }, player=player)

        self.assertIn("PRESENTATION_SHOWN", result)
        self.assertIn("Begin speaking immediately in one continuous response", result)
        self.assertNotIn("[AULA", result)
        self.assertIn("1. A luz chega à folha.", result)
        self.assertIn("2. A planta produz glicose.", result)
        player.show_visual_board.assert_called_once()
        self.assertFalse(player.show_visual_board.call_args.args[0].get("_marker_sync", False))

    def test_schema_requires_generated_beats_and_does_not_offer_presets(self):
        self.assertNotIn("scene", TOOL["parameters"]["properties"])
        self.assertIn("beats", TOOL["parameters"]["required"])

    def test_generated_lesson_registers_exact_audio_before_narration(self):
        player = self.player()
        player.start_marker_lesson = Mock(return_value=True)
        captions = ["A onda se propaga.", "A frequência conta as oscilações."]
        result = present_visual_lesson({
            "title": "Ondas", "beats": [diagram_beat(text) for text in captions],
        }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        self.assertIn("Do not narrate", result)
        player.start_marker_lesson.assert_called_once_with(captions, "Ondas")
        self.assertTrue(player.show_visual_board.call_args.args[0]["_marker_sync"])

    def test_audio_registration_failure_does_not_request_estimated_narration(self):
        player = self.player()
        player.start_marker_lesson = Mock(return_value=False)
        result = present_visual_lesson({
            "title": "Ondas", "beats": [diagram_beat("A onda se propaga.")],
        }, player=player)
        self.assertIn("PRESENTATION_UNAVAILABLE", result)
        self.assertNotIn("Begin speaking immediately", result)

    def test_unknown_scene_and_scene_with_custom_beats_are_rejected(self):
        for params in [
            {"title": "Aula", "scene": "unknown"},
            {"title": "Aula", "scene": "atomo", "beats": [diagram_beat("Pergunta específica.")]},
            {"title": "Aula"},
        ]:
            with self.subTest(params=params):
                player = self.player()
                result = present_visual_lesson(params, player=player)
                self.assertIn("PRESENTATION_INVALID", result)
                player.show_visual_board.assert_not_called()

    def test_specific_question_is_not_replaced_by_a_curated_overview(self):
        player = self.player()
        caption = "Frações equivalentes representam a mesma quantidade."
        result = present_visual_lesson({
            "title": "Frações equivalentes", "beats": [diagram_beat(caption)],
        }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        payload = player.show_visual_board.call_args.args[0]
        self.assertEqual(payload["title"], "Frações equivalentes")
        self.assertEqual([item["caption"] for item in payload["_lesson_timeline"]], [caption])

    def test_supported_topic_preserves_real_application_click_waits(self):
        player = self.player()
        first = diagram_beat("Abra a simulação de fotossíntese.")
        first.update({"wait": "click", "target": "Iniciar", "role": "button"})
        with patch("actions.present_visual_lesson._wait_for_click",
                   return_value=(True, "CLICK_AND_POSTCONDITION_VERIFIED")) as wait:
            result = present_visual_lesson({
                "title": "Fotossíntese", "beats": [first],
            }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        wait.assert_called_once_with("Iniciar", "button", 1, 120.0, "", player, "click")

    def test_realistic_gemini_lesson_accepts_text_annotations_with_omitted_type(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Demonstração do Teorema de Pitágoras",
            "beats": [
                {
                    "say": "Este é um triângulo retângulo, com um ângulo de noventa graus.",
                    "elements": [model_scene("Triângulo")],
                },
                {
                    "say": "Os lados menores são os catetos. O lado oposto é a hipotenusa.",
                    "elements": [
                        model_scene("Lados"),
                        {"id": "label_a", "text": "Cateto A", "anchor": "triangle_a_label"},
                        {"id": "label_b", "text": "Cateto B", "anchor": "triangle_b_label"},
                        {"id": "label_c", "text": "Hipotenusa", "anchor": "triangle_hypotenuse_label"},
                    ],
                },
                {
                    "say": "O teorema diz que a soma dos quadrados dos catetos é igual ao quadrado da hipotenusa.",
                    "elements": [
                        model_scene("Teorema"),
                        {"type": "formula", "id": "formula_card", "title": "Teorema de Pitágoras",
                         "text": "A² + B² = C²", "x": 70, "y": 20},
                    ],
                },
                {
                    "say": "Se os catetos medem três e quatro centímetros, vamos calcular a hipotenusa.",
                    "elements": [
                        model_scene("Exemplo"),
                        {"id": "example_a", "x": 20, "y": 40, "text": "3 cm"},
                        {"id": "example_b", "x": 45, "y": 65, "text": "4 cm"},
                        {"id": "example_c", "x": 50, "y": 35, "text": "5 cm?"},
                    ],
                },
                {
                    "say": "Três ao quadrado mais quatro ao quadrado é igual a vinte e cinco; a raiz é cinco.",
                    "elements": [
                        model_scene("Cálculo"),
                        {"type": "text", "id": "calc_card", "title": "Cálculo da Hipotenusa",
                         "text": "3² + 4² = C² · 9 + 16 = 25 · C = √25 = 5", "x": 70, "y": 50},
                    ],
                },
            ],
        }, player=player)

        self.assertIn("PRESENTATION_SHOWN", result)
        player.show_visual_board.assert_called_once()
        payload = player.show_visual_board.call_args.args[0]
        self.assertEqual(len(payload["_lesson_timeline"]), 5)
        models = [item for item in payload["elements"] if item["type"] == "model3d"]
        self.assertEqual(len(models), 5)
        self.assertTrue(all(len(item["parts"]) == 5 for item in models))
        self.assertEqual(
            [item["text"] for item in payload["elements"] if item["type"] == "text"
             and any(str(item.get("id") or "").endswith(suffix) for suffix in ("label_a", "label_b", "label_c"))],
            ["Cateto A", "Cateto B", "Hipotenusa"],
        )

    @unittest.skip("3D-only: the flat Pythagoras triangle is disabled")
    def test_pythagoras_example_and_calculations_exist_only_in_their_own_beats(self):
        player = self.player()
        result = draw_right_triangle({}, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        payload = player.show_visual_board.call_args.args[0]
        timeline = payload["_lesson_timeline"]
        elements = payload["elements"]

        self.assertEqual(len(timeline), 8)
        self.assertIn("noventa graus", timeline[0]["caption"])
        self.assertIn("catetos", timeline[1]["caption"])
        self.assertIn("hipotenusa", timeline[2]["caption"])
        self.assertIn("Agora vamos ao exemplo", timeline[3]["caption"])

        def beat_elements(index):
            beat = timeline[index]
            return elements[beat["start"]:beat["end"]]

        concept_elements = beat_elements(0) + beat_elements(1) + beat_elements(2)
        self.assertFalse(any(
            item.get("text") in {"a² + b² = c²", "3² + 4² = c²", "9 + 16 = 25", "c = √25 = 5 cm"}
            for item in concept_elements
        ))
        example_elements = beat_elements(3)
        self.assertEqual(len(example_elements), 1)
        self.assertEqual(example_elements[0]["type"], "card")
        self.assertIn("Cateto a = 3 cm", example_elements[0]["items"])
        self.assertIn("Cateto b = 4 cm", example_elements[0]["items"])

        equations = [
            beat_elements(i)[0].get("text")
            for i in range(4, 8)
        ]
        self.assertEqual(equations, [
            "a² + b² = c²", "3² + 4² = c²",
            "9 + 16 = 25", "c = √25 = 5 cm",
        ])
        self.assertEqual(
            [item["index"] for item in timeline],
            list(range(1, 9)),
        )
        self.assertTrue(all(
            timeline[i]["start_seconds"] >= timeline[i - 1]["end_seconds"]
            for i in range(1, len(timeline))
        ))

    def test_deep_flag_does_not_discard_beats_before_gemini_can_narrate(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Máquina",
            "deep": True,
            "beats": [diagram_beat("Visão geral."), beat("Detalhe do motor.")],
        }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        player.show_visual_board.assert_called_once()
        self.assertEqual(len(player.show_visual_board.call_args.args[0]["elements"]), 3)

    def test_missing_positions_are_arranged_across_beats_without_moving_geometry(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Fotossíntese",
            "beats": [
                {"say": "A luz chega à folha.", "elements": [
                    model_scene("Luz", x=25, y=30),
                    {"type": "text", "text": "Luz solar"},
                ]},
                {"say": "A planta usa água.", "elements": [
                    {"type": "text", "text": "Água"},
                    {"type": "text", "text": "Dióxido de carbono"},
                ]},
            ],
        }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        elements = player.show_visual_board.call_args.args[0]["elements"]
        self.assertEqual((elements[0]["x"], elements[0]["y"]), (25, 30))
        labels = elements[1:]
        self.assertEqual(len({(item["x"], item["y"]) for item in labels}), 3)
        for item in labels:
            self.assertLessEqual(item["x"] + item["width"], 100)
            self.assertLessEqual(item["y"] + item["height"], 100)

    def test_duplicate_text_positions_are_separated_without_moving_other_shapes(self):
        player = self.player()
        result = present_visual_lesson({"title": "Ciclo", "beats": [
            {"say": "Primeiro.", "elements": [
                model_scene("Primeiro", x=40, y=40),
                {"type": "text", "x": 50, "y": 20, "text": "Primeiro"},
            ]},
            {"say": "Depois.", "elements": [
                {"type": "text", "x": 50, "y": 20, "text": "Depois"},
            ]},
        ]}, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        first, label1, label2 = player.show_visual_board.call_args.args[0]["elements"]
        self.assertEqual((first["x"], first["y"]), (40, 40))
        self.assertEqual((label1["x"], label1["y"]), (50, 20))
        self.assertNotEqual((label1["x"], label1["y"]), (label2["x"], label2["y"]))

    def test_lesson_rejects_invalid_elements_instead_of_silently_dropping_them(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Fotossíntese",
            "beats": [{"say": "A folha recebe luz.", "elements": [
                {"type": "polygon", "points": [{"x": 10, "y": 10}]},
                {"type": "text", "text": "Luz"},
            ]}],
        }, player=player)
        self.assertIn("PRESENTATION_INVALID", result)
        self.assertIn("beat 1", result)
        player.show_visual_board.assert_not_called()

    def test_lesson_without_visual_diagram_asks_the_model_to_retry(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Fotossíntese",
            "beats": [beat("A luz chega à folha."), beat("A planta produz glicose.")],
        }, player=player)
        self.assertIn("PRESENTATION_INVALID", result)
        self.assertIn("diagram", result.lower())
        player.show_visual_board.assert_not_called()

    def test_lessons_over_48_total_elements_are_rejected_before_display(self):
        player = self.player()
        beats = [beat(f"Etapa {i}") for i in range(3)]
        for item in beats:
            item["elements"] = [{"type": "text", "x": 20, "y": 20, "text": "A"}] * 18
        result = present_visual_lesson({"title": "Grande", "beats": beats}, player=player)
        self.assertIn("at most 48 visual elements", result)
        player.show_visual_board.assert_not_called()

    def test_invalid_later_beat_is_rejected_before_any_drawing(self):
        player = self.player()
        result = present_visual_lesson({
            "title": "Aula",
            "beats": [beat("Primeiro."), {"say": "Segundo", "elements": []}],
        }, player=player)
        self.assertIn("PRESENTATION_INVALID", result)
        player.show_visual_board.assert_not_called()

    def test_click_wait_requires_exact_target_and_validates_timeout(self):
        player = self.player()
        bad = beat("Clique aqui.")
        bad["wait"] = "click"
        result = present_visual_lesson({"title": "Tutorial", "beats": [bad]}, player=player)
        self.assertIn("requires an exact target", result)
        player.show_visual_board.assert_not_called()

    def test_successful_click_wait_uses_guidance_tools_and_resumes_next_beat(self):
        player = self.player()
        first = beat("Abra as configurações.")
        first.update({"wait": "click", "target": "Settings", "role": "button"})
        with patch("actions.present_visual_lesson._wait_for_click",
                   return_value=(True, "CLICK_AND_POSTCONDITION_VERIFIED")) as wait:
            result = present_visual_lesson({
                "title": "Tutorial", "beats": [first, beat("Agora escolha Sistema.")],
            }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        wait.assert_called_once_with("Settings", "button", 1, 120.0, "", player, "click")
        player.set_visual_input_passthrough.assert_not_called()  # managed inside the wait helper

    def test_hover_wait_is_dispatched_as_a_real_hover_interaction(self):
        player = self.player()
        first = beat("Passe o mouse sobre Ferramentas.")
        first.update({"wait": "hover", "target": "Ferramentas", "role": "menu item"})
        with patch("actions.present_visual_lesson._wait_for_click",
                   return_value=(True, "GUIDANCE_HOVERED")) as wait:
            result = present_visual_lesson({
                "title": "Menu", "beats": [first, beat("Agora escolha Exportar.")],
            }, player=player)
        self.assertIn("PRESENTATION_SHOWN", result)
        wait.assert_called_once_with("Ferramentas", "menu item", 1, 120.0, "", player, "hover")

    def test_moved_target_pauses_instead_of_advancing(self):
        player = self.player()
        first = beat("Clique em Continuar.")
        first.update({"wait": "click", "target": "Continuar"})
        with patch("actions.present_visual_lesson._wait_for_click",
                   return_value=(False, "CLICK_TARGET_MOVED")):
            result = present_visual_lesson({
                "title": "Tutorial", "beats": [first, beat("Próxima etapa")],
            }, player=player)
        self.assertIn("PRESENTATION_PAUSED", result)
        self.assertEqual(player.show_visual_board.call_count, 1)

    def test_explicit_postcondition_failure_pauses(self):
        player = self.player()
        first = beat("Clique em Salvar.")
        first.update({"wait": "click", "target": "Salvar", "expect_text": "Arquivo salvo"})
        with patch("actions.present_visual_lesson._wait_for_click",
                   return_value=(False, "CLICK_SEEN_NOT_VERIFIED: expected text missing")):
            result = present_visual_lesson({
                "title": "Tutorial", "beats": [first, beat("Concluído")],
            }, player=player)
        self.assertIn("PRESENTATION_PAUSED", result)
        self.assertEqual(player.show_visual_board.call_count, 1)

    def test_timeout_pauses_without_claiming_lesson_complete(self):
        player = self.player()
        first = beat("Clique em continuar.")
        first.update({"wait": "click", "target": "Continuar"})
        with patch("actions.present_visual_lesson._wait_for_click",
                   return_value=(False, "GUIDANCE_TIMEOUT")):
            result = present_visual_lesson({"title": "Tutorial", "beats": [first]}, player=player)
        self.assertIn("PRESENTATION_PAUSED", result)
        self.assertNotIn("PRESENTATION_SHOWN", result)
        from core.i18n import app_language
        expected_prefix = "Step 1 paused" if app_language() == "en-US" else "Etapa 1 pausada"
        self.assertTrue(player.set_visual_lesson_status.call_args.args[0].startswith(expected_prefix))

    def test_click_wait_always_restores_board_input_mode(self):
        player = self.player()
        with patch("actions.highlight_screen_target.highlight_screen_target",
                   return_value="TARGET_HIGHLIGHTED:") as highlight, \
             patch("actions.wait_for_guidance_click.wait_for_guidance_click",
                   return_value="CLICK_SEEN_NOT_VERIFIED:") as wait:
            ok, note = _wait_for_click("Salvar", "button", 1, 15, "", player)
        self.assertTrue(ok)
        highlight.assert_called_once()
        wait.assert_called_once()
        player.set_visual_input_passthrough.assert_has_calls([
            unittest.mock.call(True), unittest.mock.call(False)
        ])

    def test_click_wait_restores_input_mode_when_wait_raises(self):
        player = self.player()
        with patch("actions.highlight_screen_target.highlight_screen_target",
                   return_value="TARGET_HIGHLIGHTED:"), \
             patch("actions.wait_for_guidance_click.wait_for_guidance_click",
                   side_effect=RuntimeError("mouse poll failed")):
            with self.assertRaises(RuntimeError):
                _wait_for_click("Salvar", "button", 1, 15, "", player)
        player.set_visual_input_passthrough.assert_has_calls([
            unittest.mock.call(True), unittest.mock.call(False)
        ])

    def test_animation_wait_uses_real_qt_completion_state(self):
        player = self.player()
        player.visual_animation_done.side_effect = [False, False, True]
        self.assertTrue(_wait_for_drawing(player, timeout=2.0))
        self.assertEqual(player.visual_animation_done.call_count, 3)

    def test_tool_schema_and_discovery_are_registered(self):
        self.assertEqual(TOOL["name"], "present_visual_lesson")
        allowed = TOOL["parameters"]["properties"]["beats"]["items"]["properties"]["elements"]["items"]
        self.assertEqual(allowed["properties"]["type"]["enum"],
                         ["model3d", "text", "formula", "quiz"])
        self.assertIn("Never use flat 2D primitives",
                      TOOL["parameters"]["properties"]["beats"]["items"]["properties"]["elements"]["description"])
        from pathlib import Path
        from core.action_loader import discover_actions
        registry = discover_actions(Path(__file__).resolve().parents[1] / "actions",
                                    logger=lambda _: None)
        self.assertTrue(registry.has("present_visual_lesson"))


if __name__ == "__main__":
    unittest.main()
