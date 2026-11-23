"""Lesson director: the app (not the live voice model) creates every lesson on the spot.

A text model describes the lesson SEMANTICALLY (what each thing is and where it sits
relative to the others, never coordinates). core.lesson_layout compiles that into the
cumulative 3D beats that present_visual_lesson plays in sync with the voice.
"""
from __future__ import annotations

_RULES = (
    "You are the most didactic teacher in the world, explaining to a curious beginner who is looking at a "
    "3D picture that grows piece by piece while you speak. Write in the selected JARVIS app language. Return ONLY JSON: "
    '{"title": string, "archetype": "anatomy"|"chain"|"cycle"|"compare", '
    '"beats": [{"say": string, "add": [part], "focus": id, "links": [{"from": id, "to": id, "label": string}]}]}. '
    "Never write coordinates. The code positions everything. "
    "TEACHING SCRIPT (6 to 8 beats, follow this order): "
    "(1) HOOK + DEFINITION: the main subject alone in the center; say what it is in one everyday sentence, "
    "using a familiar analogy ('é como um ralo gigante no espaço'). "
    "(2-4) ONE NEW PART PER BEAT, from most important to least: say its name, what it is in plain words, and WHY it "
    "matters, connecting to the previous beat ('por isso', 'agora', 'e o que acontece em volta?'). "
    "(5) HOW IT WORKS: no new part; use links (arrows with a 1-2 word label such as 'cai', 'gira', 'vira') and narrate the "
    "cause and effect in the exact order the arrows show, step by step. "
    "(6) COMMON MISTAKE: no new part; set 'focus' to the part involved and correct a popular misconception "
    "('muita gente acha que..., mas na verdade...'). "
    "(LAST) SUMMARY: no new part; one sentence that ties the whole picture together, plus one fun fact or a sense of scale. "
    "RULES FOR 'say': one natural spoken sentence, max 170 characters, short simple words, no jargon without explaining it, "
    "address the listener ('olhe', 'repare'), point to what is on screen ('esse anel brilhante aqui'). "
    "'add' has at most ONE part per beat (use [] for beats that add nothing); 3 to 7 parts in total. "
    "'focus' (optional) = id of an already shown part to highlight in that beat. "
    'part = {"id": short_snake_case, "label": under 20 chars, "role": one of '
    "core|dark|shell|disk|body|small|container|stack|energy|flow|living|danger, "
    '"place": center|around|ring|orbit|above|below|left|right|front|back|inside, "of": id of the part it sits '
    'relative to}. archetype "anatomy" = a thing and its real parts (use place/of so the layout mirrors reality: '
    "a shell goes AROUND the core, a disk is a RING, moons ORBIT, an input comes from the LEFT, an output goes RIGHT). "
    'archetype "chain" = steps of a process or a timeline (history, algorithms, economics) in order, '
    'archetype "cycle" = something that repeats, archetype "compare" = two sides (add "group":"a" or "b" to each part). '
    "Choose roles that look like what they are (core=hot energy source, dark=dark/empty thing, living=plants/cells, "
    "flow=water/fluid, energy=light/heat, danger=risk). Abstract subjects become simple physical metaphors "
    "(events as stack pillars along a chain, ideas as bodies, cause->effect as labelled links). "
    "Facts must be correct. Example for 'o que é um buraco negro' (anatomy): "
    "beat1 add singularity (dark, center): 'Um buraco negro é como um ralo gigante no espaço, e no centro dele fica a singularidade, um ponto onde tudo é esmagado.'; "
    "beat2 add horizon (shell, around, of singularity): 'Em volta dela existe o horizonte de eventos, a fronteira sem volta: passou dela, nem a luz escapa.'; "
    "beat3 add disk (disk, ring, of singularity): 'Fora dessa fronteira, gás gira em alta velocidade num disco e fica tão quente que brilha.'; "
    "beat4 add star (core, orbit, of singularity): 'Se uma estrela passa perto, a gravidade a puxa, como a água sendo puxada para o ralo.'; "
    "beat5 links star->disk 'espirala', disk->singularity 'cai': 'Repare no caminho: a estrela se desfaz, vira disco e cai aos poucos no centro.'; "
    "beat6 focus horizon: 'Muita gente acha que ele é um buraco vazio, mas é uma região de massa enorme concentrada num espaço minúsculo.'; "
    "beat7: 'Resumindo: centro denso, fronteira sem volta e um disco brilhante em volta. Se o Sol virasse um, teria só uns 6 km de largura.' "
    "Question: "
)


def generate_lesson(question: str, error: str = "") -> dict | None:
    """Blocking model call; run it in a worker thread. None on any failure."""
    try:
        from core import gemini
        from core.lesson_layout import compile_lesson
        question = " ".join(str(question or "").split())[:400]
        if not question:
            return None
        from core.i18n import language_instruction, language_name
        prompt = (
            _RULES
            + "\n\n" + language_instruction()
            + f"\nLANGUAGE RULE: Every human-readable string in the entire 3D lesson (title, subtitle, all 3D labels, part/model labels, link labels, captions, annotations, and spoken 'say') must be written in {language_name()}. "
            "No mixed-language content is allowed: every human-readable field, including all labels and narration, must follow the selected app language. The Portuguese examples in the fixed template illustrate structure only; do not copy their language "
            "when English is selected."
            + "\nQUESTION: " + question
        )
        if error:
            prompt += " . The previous attempt was rejected: " + error[:400] + " Fix it."
        data = gemini.as_json(prompt, default=None)
        if isinstance(data, list):
            data = {"title": question[:60], "beats": data}
        if not isinstance(data, dict) or not isinstance(data.get("beats"), list) or not data["beats"]:
            return None
        data.setdefault("title", question[:60])
        lesson = compile_lesson(data)
        if lesson is None:
            print("[Director] semantic lesson unusable (needs 3+ parts, 3+ beats, each with 'say').")
        return lesson
    except Exception as exc:  # network, quota, parsing...
        print(f"[Director] lesson generation failed: {exc!r}")
        return None
