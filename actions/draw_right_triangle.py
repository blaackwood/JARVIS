"""JARVIS-native, voice-clocked Pythagoras lesson in JARVIS's own visual language."""
from __future__ import annotations

from actions.present_visual_lesson import present_visual_lesson


def draw_right_triangle(parameters: dict | None = None, player=None, speak=None) -> str:
    return ("VISUAL_INVALID: 3D_ONLY - flat triangles are disabled. Call present_visual_lesson "
            "with beats whose model3d builds the triangle from labelled 3D bodies and links.")
    """Teach the right triangle as ordered voice-and-visual beats.

    No worked-example object is sent to the board until the example-introduction
    beat. Every equation is a separate later beat, so it cannot be pre-rendered.
    """
    beats = [
        {
            "say": "Este é um triângulo retângulo. Repare que ele possui um ângulo de noventa graus.",
            "cue_words": ["", "noventa"],
            "elements": [
                {"id": "triangle-outline", "type": "polygon", "points": [
                    {"x": 14, "y": 82}, {"x": 14, "y": 20}, {"x": 66, "y": 82},
                ], "color": "cyan", "stroke_width": 3.0, "fill": True},
                {"id": "right-angle", "type": "angle", "x": 14, "y": 82,
                 "x2": 14, "y2": 20, "x3": 66, "y3": 82,
                 "label": "90°", "color": "amber", "radius": 7, "stroke_width": 2.4},
            ],
        },
        {
            "say": "Os dois lados que formam esse ângulo reto recebem o nome de catetos.",
            "cue_words": ["dois lados", "formam", "catetos", "catetos"],
            "elements": [
                {"id": "vertical-cathetus", "type": "line", "x": 14, "y": 82,
                 "x2": 14, "y2": 20, "color": "green", "stroke_width": 5.0},
                {"id": "horizontal-cathetus", "type": "line", "x": 14, "y": 82,
                 "x2": 66, "y2": 82, "color": "blue", "stroke_width": 5.0},
                {"id": "cathetus-a-label", "type": "text", "x": 17, "y": 50,
                 "text": "CATETO", "color": "green", "font_size": 17},
                {"id": "cathetus-b-label", "type": "text", "x": 35, "y": 86,
                 "text": "CATETO", "color": "blue", "font_size": 17},
            ],
        },
        {
            "say": "O lado inclinado, que fica na frente do ângulo de noventa graus, é a hipotenusa.",
            "elements": [
                {"id": "hypotenuse-highlight", "type": "line", "x": 14, "y": 20,
                 "x2": 66, "y2": 82, "color": "pink", "stroke_width": 5.2},
                {"id": "hypotenuse-label", "type": "text", "x": 43, "y": 42,
                 "text": "HIPOTENUSA", "color": "pink", "font_size": 17},
            ],
        },
        {
            "say": "Agora vamos ao exemplo: os catetos medem três centímetros e quatro centímetros. Queremos descobrir a hipotenusa.",
            "elements": [
                {"id": "example-data", "type": "card", "x": 70, "y": 10,
                 "width": 27, "height": 29, "color": "cyan",
                 "heading": "EXEMPLO • DADOS",
                 "items": ["Cateto a = 3 cm", "Cateto b = 4 cm", "Hipotenusa c = ?"]},
            ],
        },
        {
            "say": "Para isso, usamos o teorema de Pitágoras: a ao quadrado mais b ao quadrado é igual a c ao quadrado.",
            "elements": [
                {"id": "pythagoras-formula", "type": "formula", "x": 69, "y": 45,
                 "width": 29, "height": 10, "font_size": 20,
                 "text": "a² + b² = c²", "color": "cyan"},
            ],
        },
        {
            "say": "Agora substituímos a e b pelos valores conhecidos: três ao quadrado mais quatro ao quadrado é igual a c ao quadrado.",
            "elements": [
                {"id": "substitution", "type": "formula", "x": 69, "y": 59,
                 "width": 29, "height": 10, "font_size": 18,
                 "text": "3² + 4² = c²", "color": "blue"},
            ],
        },
        {
            "say": "Três ao quadrado é nove, quatro ao quadrado é dezesseis. Nove mais dezesseis é vinte e cinco.",
            "elements": [
                {"id": "arithmetic", "type": "formula", "x": 69, "y": 73,
                 "width": 29, "height": 10, "font_size": 18,
                 "text": "9 + 16 = 25", "color": "amber"},
            ],
        },
        {
            "say": "Extraímos a raiz quadrada dos dois lados e encontramos c igual a cinco centímetros. Essa é a hipotenusa.",
            "elements": [
                {"id": "final-answer", "type": "formula", "x": 69, "y": 87,
                 "width": 29, "height": 10, "font_size": 20,
                 "text": "c = √25 = 5 cm", "color": "green"},
            ],
        },
    ]
    return present_visual_lesson(
        {
            "title": "Teorema de Pitágoras",
            "subtitle": "Acompanhe cada conceito e cada cálculo no momento em que são explicados",
            "layout": "geometry",
            "beats": beats,
        },
        player=player,
        speak=speak,
    )


