"""Pictorial scenes with ordered narration and a final interactive question."""
from __future__ import annotations


def _t(x, y, text, color="white", size=15, width=30, height=8):
    return {"type": "text", "x": x, "y": y, "text": text, "color": color,
            "font_size": size, "width": width, "height": height}


def _arrow(x, y, x2, y2, color="cyan", width=2.4):
    return {"type": "arrow", "x": x, "y": y, "x2": x2, "y2": y2,
            "color": color, "stroke_width": width}


def _line(x, y, x2, y2, color="white", width=1.6):
    return {"type": "line", "x": x, "y": y, "x2": x2, "y2": y2,
            "color": color, "stroke_width": width}


def _circle(x, y, radius, color="cyan", fill=True, width=2.2):
    return {"type": "circle", "x": x, "y": y, "radius": radius,
            "color": color, "fill": fill, "stroke_width": width}


def _poly(points, color="green", fill=True, width=2.4, closed=True):
    return {"type": "polygon" if closed else "polyline",
            "points": [{"x": x, "y": y} for x, y in points],
            "color": color, "fill": fill, "stroke_width": width}


def _formula(x, y, text, color="green", width=34, height=12, size=17):
    return {"type": "formula", "x": x, "y": y, "text": text, "color": color,
            "width": width, "height": height, "font_size": size}


def _quiz(x, y, title, options, answer, explanation, width=34, height=26):
    return {"type": "quiz", "x": x, "y": y, "title": title, "options": options,
            "answer": answer, "explanation": explanation,
            "width": width, "height": height, "color": "cyan"}


# --- Fotossíntese -----------------------------------------------------------
_LEAF = [(34, 24), (39, 28), (44, 33), (48, 39), (51, 46), (52, 54),
         (50, 63), (46, 71), (40, 77), (34, 82), (28, 78), (23, 72),
         (19, 64), (17, 56), (17, 48), (19, 40), (24, 33), (29, 28)]


def _fotossintese() -> dict:
    return {
        "title": "Fotossíntese",
        "subtitle": "Como a planta transforma luz em alimento",
        "layout": "science",
        "beats": [
            {"say": "A fotossíntese acontece dentro da folha, onde a planta captura a luz do sol.",
             "cue_words": ["folha", "luz"],
             "elements": [
                 _poly(_LEAF, "green", fill=True),
                 _line(34, 28, 34, 80, "green", 1.6),
                 _circle(80, 18, 8, "amber", fill=True),
                 _t(24, 86, "Folha", "green", 16, 20),
             ]},
            {"say": "A luz do sol viaja até a folha e é absorvida pela clorofila, o pigmento que deixa a planta verde.",
             "cue_words": ["luz", "clorofila"],
             "elements": [
                 _arrow(74, 24, 50, 42, "amber", 2.8),
                 _t(60, 26, "Luz", "amber", 16, 16),
                 _t(22, 60, "Clorofila", "green", 15, 26),
             ]},
            {"say": "As raízes absorvem água do solo, e essa água sobe pelo caule até chegar à folha.",
             "cue_words": ["raízes", "água", "caule"],
             "elements": [
                 _poly([(34, 82), (34, 92), (26, 97), (42, 97)], "blue", fill=False, width=2.2),
                 _arrow(20, 90, 20, 60, "cyan", 2.4),
                 _t(6, 78, "Água", "cyan", 15, 14),
             ]},
            {"say": "O gás carbônico do ar entra na folha por pequenos poros chamados estômatos.",
             "cue_words": ["gás carbônico", "estômatos"],
             "elements": [
                 _arrow(96, 44, 54, 50, "muted", 2.4),
                 _t(84, 36, "CO₂", "muted", 16, 14),
                 _circle(50, 52, 1.6, "cyan", fill=True),
                 _circle(48, 58, 1.6, "cyan", fill=True),
             ]},
            {"say": "Usando luz, água e gás carbônico, a folha produz glicose, o açúcar que alimenta a planta.",
             "cue_words": ["glicose", "açúcar"],
             "elements": [
                 _formula(62, 84, "6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂", "green", 36, 10, 15),
                 _t(22, 50, "Glicose", "pink", 15, 14),
             ]},
            {"say": "Como resultado, a planta libera oxigênio no ar, que é justamente o gás que nós respiramos.",
             "cue_words": ["oxigênio", "respiramos"],
             "elements": [
                 _arrow(46, 34, 66, 12, "cyan", 2.6),
                 _circle(70, 10, 2.4, "cyan", fill=True),
                 _t(60, 4, "O₂", "cyan", 17, 12),
             ]},
            {"say": "Agora é com você: o que a planta libera para o ar durante a fotossíntese?",
             "elements": [
                 _quiz(62, 52, "O que a planta libera no ar?",
                       ["Glicose", "Oxigênio", "Gás carbônico"], "Oxigênio",
                       "Isso! A fotossíntese libera oxigênio, que nós respiramos.", 36, 28),
             ]},
        ],
    }


# --- Ciclo da água ----------------------------------------------------------
def _ciclo_da_agua() -> dict:
    return {
        "title": "Ciclo da água",
        "subtitle": "A viagem contínua da água pela natureza",
        "layout": "science",
        "beats": [
            {"say": "O sol aquece a água dos rios, lagos e oceanos, dando início ao ciclo da água.",
             "cue_words": ["sol", "água"],
             "elements": [
                 _circle(14, 14, 7, "amber", fill=True),
                 _poly([(6, 80), (30, 76), (55, 80), (80, 76), (96, 80)], "blue", fill=False, width=2.6),
                 _poly([(6, 80), (30, 76), (55, 80), (80, 76), (96, 80), (96, 96), (6, 96)],
                       "blue", fill=True, width=1.4),
                 _t(30, 88, "Oceanos e rios", "cyan", 15, 34),
             ]},
            {"say": "Com o calor, a água evapora e sobe para o céu em forma de vapor invisível.",
             "cue_words": ["evapora", "vapor"],
             "elements": [
                 _arrow(30, 74, 30, 40, "cyan", 2.6),
                 _arrow(48, 74, 48, 40, "cyan", 2.6),
                 _t(4, 44, "Evaporação", "cyan", 15, 24),
             ]},
            {"say": "Lá no alto, o vapor esfria e se condensa em gotículas, formando as nuvens.",
             "cue_words": ["condensa", "nuvens"],
             "elements": [
                 _circle(44, 24, 6, "white", fill=True),
                 _circle(50, 21, 8, "white", fill=True),
                 _circle(56, 24, 6, "white", fill=True),
                 _t(62, 36, "Condensação", "white", 15, 28),
             ]},
            {"say": "Quando as gotículas ficam pesadas demais, caem como chuva, neve ou granizo.",
             "cue_words": ["chuva", "neve"],
             "elements": [
                 _arrow(46, 32, 42, 64, "blue", 2.4),
                 _arrow(54, 32, 58, 64, "blue", 2.4),
                 _circle(42, 68, 1.6, "cyan", fill=True),
                 _circle(58, 68, 1.6, "cyan", fill=True),
                 _t(62, 48, "Precipitação", "blue", 15, 28),
             ]},
            {"say": "Parte da água infiltra no solo; outra parte escoa até rios e oceanos. O ciclo recomeça.",
             "cue_words": ["escorre", "volta"],
             "elements": [
                 _poly([(90, 56), (94, 66), (90, 74)], "cyan", fill=False, width=2.4),
                 _arrow(90, 74, 66, 78, "cyan", 2.4),
                 _t(62, 60, "Escoamento", "cyan", 15, 26),
             ]},
            {"say": "Teste rápido: qual é a etapa em que a água vira vapor e sobe para o céu?",
             "elements": [
                 _quiz(64, 6, "A água vira vapor e sobe. Que etapa é essa?",
                       ["Precipitação", "Evaporação", "Infiltração"], "Evaporação",
                       "Correto! O calor do sol faz a água evaporar e subir.", 34, 26),
             ]},
        ],
    }


# --- Respiração celular -----------------------------------------------------
def _respiracao_celular() -> dict:
    return {
        "title": "Respiração celular",
        "subtitle": "Respiração aeróbia em células eucarióticas",
        "layout": "science",
        "beats": [
            {"say": "Na respiração aeróbia de células eucarióticas, a energia dos nutrientes ajuda a produzir ATP.",
             "cue_words": ["células", "ATP"],
             "elements": [
                 _circle(32, 52, 24, "cyan", fill=True, width=2.6),
                 _circle(32, 52, 7, "purple", fill=True),
                 _t(20, 80, "Célula", "cyan", 16, 20),
                 _t(26, 64, "Núcleo", "purple", 13, 16),
             ]},
            {"say": "A glicose, um açúcar, entra na célula junto com o oxigênio que respiramos.",
             "cue_words": ["glicose", "oxigênio"],
             "elements": [
                 _circle(8, 30, 3, "pink", fill=True),
                 _arrow(11, 32, 21, 42, "pink", 2.4),
                 _t(2, 20, "Glicose", "pink", 14, 18),
                 _circle(8, 70, 2.4, "cyan", fill=True),
                 _arrow(11, 68, 21, 60, "cyan", 2.4),
                 _t(2, 76, "O₂", "cyan", 15, 12),
             ]},
            {"say": "No citosol, a glicólise divide a glicose em piruvato e produz um pouco de ATP.",
             "cue_words": ["glicólise", "piruvato"],
             "elements": [
                 _t(23, 34, "Glicólise", "pink", 11, 18),
                 _circle(28, 43, 1.7, "pink", fill=True),
                 _circle(32, 43, 1.7, "pink", fill=True),
             ]},
            {"say": "Na mitocôndria, o piruvato é processado. O oxigênio recebe elétrons no fim da cadeia, permitindo produzir mais ATP.",
             "cue_words": ["mitocôndria", "ATP"],
             "elements": [
                 _poly([(36, 46), (41, 44), (43, 50), (41, 56), (36, 54), (39, 50)],
                       "amber", fill=False, width=2.4),
                 _t(48, 34, "Mitocôndria", "amber", 15, 26),
                 _t(48, 42, "usina de energia", "amber", 12, 26),
             ]},
            {"say": "A energia liberada é guardada numa molécula chamada ATP, a moeda de energia da célula.",
             "cue_words": ["ATP", "moeda"],
             "elements": [
                 _formula(62, 60, "Glicose + O₂ → CO₂ + H₂O + energia", "amber", 34, 11, 14),
                 _circle(70, 78, 3, "amber", fill=True),
                 _t(75, 74, "ATP", "amber", 17, 14),
             ]},
            {"say": "O processo libera gás carbônico e forma água. Nosso corpo transporta esses produtos; o gás carbônico sai pela respiração.",
             "cue_words": ["gás carbônico", "água"],
             "elements": [
                 _arrow(43, 64, 60, 88, "muted", 2.4),
                 _t(62, 88, "CO₂ + H₂O", "muted", 15, 24),
             ]},
            {"say": "Pergunta rápida: qual molécula guarda a energia que a célula acabou de liberar?",
             "elements": [
                 _quiz(62, 6, "Qual molécula guarda a energia liberada?",
                       ["Glicose", "ATP", "Oxigênio"], "ATP",
                       "Exato! O ATP é a moeda de energia que a célula usa.", 34, 24),
             ]},
        ],
    }


# --- Átomo ------------------------------------------------------------------
def _atomo() -> dict:
    return {
        "title": "Estrutura do átomo",
        "subtitle": "Núcleo e camadas de energia — modelo simplificado",
        "layout": "science",
        "beats": [
            {"say": "Toda matéria é feita de átomos, partículas incrivelmente pequenas.",
             "cue_words": ["átomos", "pequenas"],
             "elements": [
                 _circle(40, 52, 26, "cyan", fill=False, width=1.6),
                 _t(24, 84, "Átomo", "cyan", 17, 22),
             ]},
            {"say": "No centro fica o núcleo, muito pequeno e denso, concentrando quase toda a massa.",
             "cue_words": ["núcleo", "massa"],
             "elements": [
                 _circle(40, 52, 5, "red", fill=True),
                 _t(45, 60, "Núcleo", "red", 15, 16),
             ]},
            {"say": "O núcleo contém prótons, de carga positiva, e nêutrons, que não têm carga.",
             "cue_words": ["prótons", "nêutrons"],
             "elements": [
                 _circle(40, 50, 1.5, "amber", fill=True),
                 _circle(40, 54, 1.5, "amber", fill=True),
                 _circle(41.5, 52, 1.5, "white", fill=True),
                 _t(60, 34, "Próton (+)", "amber", 14, 24),
                 _t(60, 42, "Nêutron (0)", "white", 14, 24),
             ]},
            {"say": "Os elétrons têm carga negativa. Estes círculos representam camadas de energia, não trajetórias reais.",
             "cue_words": ["elétrons", "camadas"],
             "elements": [
                 _circle(40, 52, 16, "blue", fill=False, width=1.2),
                 _circle(40, 36, 1.8, "cyan", fill=True),
                 _circle(40, 68, 1.8, "cyan", fill=True),
                 _t(60, 52, "Elétron (−)", "cyan", 14, 26),
             ]},
            {"say": "Um átomo neutro tem o mesmo número de prótons e de elétrons, equilibrando as cargas.",
             "cue_words": ["neutro", "equilibrando"],
             "elements": [
                 _formula(62, 66, "prótons (+) = elétrons (−)", "green", 34, 11, 15),
                 _t(62, 80, "átomo neutro", "green", 14, 26),
             ]},
            {"say": "Vamos conferir: qual partícula tem carga negativa e fica ao redor do núcleo?",
             "elements": [
                 _quiz(62, 6, "Qual partícula tem carga negativa?",
                       ["Próton", "Nêutron", "Elétron"], "Elétron",
                       "Isso! O elétron tem carga negativa e fica na região ao redor do núcleo.", 34, 24),
             ]},
        ],
    }


# --- Sistema solar ----------------------------------------------------------
def _sistema_solar() -> dict:
    _planets = [
        (24, 2.0, "muted", "Mercúrio"), (32, 2.6, "amber", "Vênus"),
        (40, 2.8, "blue", "Terra"), (48, 2.4, "red", "Marte"),
        (60, 5.0, "amber", "Júpiter"), (72, 4.4, "amber", "Saturno"),
        (84, 3.4, "cyan", "Urano"), (93, 3.2, "blue", "Netuno"),
    ]
    beats = [
        {"say": "O sistema solar tem o Sol ao centro, uma estrela que concentra quase toda a massa.",
         "cue_words": ["Sol", "estrela"],
         "elements": [
             _circle(10, 50, 8, "amber", fill=True),
             _t(4, 64, "Sol", "amber", 17, 14),
         ]},
        {"say": "Ao redor do Sol, oito planetas giram em órbitas, presos pela gravidade da estrela.",
         "cue_words": ["oito planetas", "gravidade"],
         "elements": [
             _line(18, 50, 97, 50, "muted", 1.0),
         ] + [_circle(x, 50, r, c, fill=True) for x, r, c, _n in _planets]},
        {"say": "Os quatro planetas de dentro são rochosos e menores: Mercúrio, Vênus, Terra e Marte.",
         "cue_words": ["rochosos", "Terra"],
         "elements": [_t(x - 4, 60, n, c, 11, 10) for x, _r, c, n in _planets[:4]]},
        {"say": "Júpiter e Saturno são gigantes gasosos; Urano e Netuno são gigantes de gelo.",
         "cue_words": ["gasosos", "gelo"],
         "elements": [_t(x - 4, 38, n, c, 11, 10) for x, _r, c, n in _planets[4:]] +
                     [_line(66, 50, 78, 50, "amber", 1.2)]},
        {"say": "A Terra é o terceiro planeta, na distância certa do Sol para existir água líquida e vida.",
         "cue_words": ["Terra", "água líquida"],
         "elements": [
             _circle(40, 50, 4.4, "cyan", fill=False, width=1.6),
             _t(30, 72, "Zona habitável", "green", 14, 24),
         ]},
        {"say": "Quiz: qual é o terceiro planeta a partir do Sol, onde existe vida?",
         "elements": [
             _quiz(60, 66, "Qual é o terceiro planeta a partir do Sol?",
                   ["Vênus", "Terra", "Marte"], "Terra",
                   "Correto! A Terra é o terceiro planeta e abriga vida.", 36, 26),
         ]},
    ]
    return {"title": "Sistema solar", "subtitle": "O Sol e os oito planetas em órbita",
            "layout": "science", "beats": beats}


# --- Frações ----------------------------------------------------------------
def _fracoes() -> dict:
    return {
        "title": "Frações",
        "subtitle": "Entender partes de um todo, visualmente",
        "layout": "geometry",
        "beats": [
            {"say": "Uma fração representa uma parte de um todo que foi dividido em partes iguais.",
             "cue_words": ["parte", "iguais"],
             "elements": [
                 {"type": "rect", "x": 10, "y": 30, "width": 40, "height": 40,
                  "color": "cyan", "fill": False, "stroke_width": 2.4},
                 _t(16, 78, "Um inteiro", "cyan", 16, 26),
             ]},
            {"say": "Imagine uma barra de chocolate dividida em quatro pedaços iguais. Cada pedaço vale um quarto.",
             "cue_words": ["quatro", "um quarto"],
             "elements": [
                 _line(10, 50, 50, 50, "white", 1.6),
                 _line(30, 30, 30, 70, "white", 1.6),
                 _poly([(30, 30), (50, 30), (50, 50), (30, 50)], "amber", fill=True, width=1.4),
                 _t(14, 20, "1 de 4 pedaços", "amber", 15, 26),
             ]},
            {"say": "Escrevemos um quarto como 1 sobre 4: o número de baixo conta as partes totais.",
             "cue_words": ["1 sobre 4", "baixo"],
             "elements": [
                 _formula(60, 58, "1 / 4", "amber", 22, 12, 24),
                 _t(60, 72, "4 = partes totais", "white", 14, 30),
             ]},
            {"say": "O número de cima, o numerador, conta quantas partes nós pegamos.",
             "cue_words": ["cima", "numerador"],
             "elements": [
                 _t(60, 42, "1 = partes pegas", "amber", 14, 30),
                 _arrow(70, 50, 70, 56, "amber", 2.0),
             ]},
            {"say": "Se pegarmos três dos quatro pedaços, temos três quartos, ou 3 sobre 4 da barra.",
             "cue_words": ["três", "3 sobre 4"],
             "elements": [
                 _poly([(10, 30), (30, 30), (30, 50), (10, 50)], "green", fill=True, width=1.4),
                 _poly([(10, 50), (30, 50), (30, 70), (10, 70)], "green", fill=True, width=1.4),
                 _formula(60, 84, "3 / 4", "green", 22, 10, 22),
             ]},
            {"say": "Sua vez: numa barra de oito pedaços iguais, você come dois. Que fração você comeu?",
             "elements": [
                 _quiz(60, 6, "Barra com 8 pedaços: você come 2. Que fração?",
                       ["2 / 8", "8 / 2", "2 / 2"], "2 / 8",
                       "Isso! 2 partes de 8 = 2/8, que simplificado é 1/4.", 36, 26),
         ]},
        ],
    }


_SCENES = {
    "fotossintese": _fotossintese,
    "ciclo_da_agua": _ciclo_da_agua,
    "respiracao_celular": _respiracao_celular,
    "atomo": _atomo,
    "sistema_solar": _sistema_solar,
    "fracoes": _fracoes,
}


def get_lesson_scene(name: str) -> dict | None:
    builder = _SCENES.get(name)
    return builder() if builder is not None else None