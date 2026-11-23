"""Sequenced visual lessons with progressive drawing, captions and guided waits."""
from __future__ import annotations

import copy
import threading
import time
from typing import Any

from core.visual_board import MAX_ELEMENTS, normalize_visual_payload
from actions.visual_board import _ELEMENT_SCHEMA

_LESSON_ELEMENT_SCHEMA = copy.deepcopy(_ELEMENT_SCHEMA)
_LESSON_ELEMENT_SCHEMA["properties"]["type"]["enum"] = [
    "model3d", "text", "formula", "quiz",
]

_MAX_BEATS = 12
_MAX_BEAT_ELEMENTS = 18
_POSITIONED_TYPES = {
    "text", "formula", "card", "list", "table", "timeline", "graph", "mindmap",
    "model3d", "quiz", "photo", "map", "molecule", "bar",
}
_DIAGRAM_TYPES = {
    "line", "arrow", "circle", "rect", "polygon", "polyline", "angle",
    "dimension", "bar", "table", "timeline", "graph", "mindmap", "model3d",
    "photo", "map", "molecule",
}


def _layout_missing_positions(elements: list[dict], raw_elements: list[dict]) -> None:
    pending = []
    occupied = []
    text_positions = set()
    for item, raw in zip(elements, raw_elements):
        if item["type"] not in _POSITIONED_TYPES:
            continue
        missing_x = raw.get("x") is None
        missing_y = raw.get("y") is None
        position = (item["x"], item["y"])
        if item["type"] in {"text", "formula"} and not missing_x and not missing_y:
            if position in text_positions:
                missing_y = True
            text_positions.add(position)
        if missing_x or missing_y:
            pending.append((item, raw, missing_x, missing_y))
        else:
            occupied.append((item["x"], item["y"], item["width"], item["height"]))

    rows = max(4, (len(pending) + 1) // 2)
    for item, raw, missing_x, missing_y in pending:
        if raw.get("width") is None and missing_x:
            item["width"] = 42 if item["type"] in {"text", "formula"} else min(42, item["width"])
        if raw.get("height") is None:
            max_height = 90 / max(1, (len(pending) + 1) // 2) - 2
            item["height"] = min(item["height"], max(3, max_height))
        xs = (5, 53) if missing_x else (item["x"],)
        ys = [5 + 90 * row / rows for row in range(rows)] if missing_y else [item["y"]]
        candidates = []
        for y in ys:
            for x in xs:
                x = min(x, 100 - item["width"]) if missing_x else x
                y = min(y, 100 - item["height"]) if missing_y else y
                overlap = sum(
                    max(0, min(x + item["width"], ox + ow) - max(x, ox))
                    * max(0, min(y + item["height"], oy + oh) - max(y, oy))
                    for ox, oy, ow, oh in occupied
                )
                candidates.append((overlap, y, x))
        _, item["y"], item["x"] = min(candidates)
        occupied.append((item["x"], item["y"], item["width"], item["height"]))


def _cue_fractions(say: str, cue_words, units: int) -> list:
    """Where in the caption each element should appear (0..1), or None for 'auto'.

    ``cue_words`` holds one optional word/phrase per element. The fraction is
    applied to the beat's exact audible duration, so it only has to be right
    within one sentence, not across the whole lesson.
    """
    out: list = []
    folded = str(say or "").casefold()
    for j in range(max(0, int(units))):
        word = ""
        if isinstance(cue_words, (list, tuple)) and j < len(cue_words):
            word = str(cue_words[j] or "").strip().casefold()
        position = folded.find(word) if word else -1
        out.append(None if position < 0 else position / max(1, len(folded)))
    return out


def _prepare_assets(payload: dict, notes: list[str]) -> None:
    """Resolve image bytes before the Qt painter sees a photo element."""
    for item in payload.get("elements", []):
        if item.get("type") != "photo":
            continue
        try:
            from core.visual_assets import fetch_photo
            photo = fetch_photo(item.get("photo_query", ""), item.get("photo_url", ""))
            item["photo_data"] = photo["data"]
            item["photo_mime"] = photo["mime_type"]
            item["photo_title"] = photo.get("title") or item.get("photo_query") or "Imagem"
            item["credit"] = item.get("credit") or photo.get("credit") or ""
            item["title"] = item.get("title") or item["photo_title"]
            item["caption"] = item.get("caption") or item["photo_title"]
        except Exception as exc:
            item["photo_error"] = f"Imagem indisponível: {type(exc).__name__}"
            item["title"] = item.get("title") or item.get("photo_query") or "Fotografia"
            notes.append("Uma fotografia ficou indisponível; o restante da etapa foi preservado.")


def _wait_for_drawing(player, timeout: float = 60.0) -> bool:
    """Wait for Qt's real progressive reveal timer, not an estimated animation delay."""
    deadline = time.monotonic() + max(1.0, min(float(timeout), 60.0))
    while time.monotonic() < deadline:
        if player.visual_animation_done():
            return True
        time.sleep(0.05)
    return bool(player.visual_animation_done())


def _wait_for_click(target: str, role: str, step: int, timeout: float,
                    expect_text: str, player, mode: str = "click") -> tuple[bool, str]:
    """Reuse the existing verified UIA highlight + physical-click path."""
    from actions.highlight_screen_target import highlight_screen_target
    from actions.wait_for_guidance_click import wait_for_guidance_click

    highlighted = highlight_screen_target(
        {"target": target, "role": role, "step": step}, player=player
    )
    if not highlighted.startswith("TARGET_HIGHLIGHTED:"):
        return False, highlighted

    player.set_visual_input_passthrough(True)
    try:
        result = wait_for_guidance_click(
            {"mode": mode, "timeout": timeout, "expect_text": expect_text}, player=player
        )
    finally:
        player.set_visual_input_passthrough(False)

    if result.startswith("GUIDANCE_CANCELLED:"):
        return False, result
    if result.startswith(("GUIDANCE_TIMEOUT:", "GUIDANCE_HOVER_TIMEOUT:")):
        return False, result
    if mode == "hover" and result.startswith("GUIDANCE_HOVERED:"):
        return True, result
    if result.startswith(("TARGET_WINDOW_CHANGED:", "TARGET_NOT_RECHECKED:",
                          "TARGET_NO_LONGER_UNIQUE:", "TARGET_NO_LONGER_ACTIONABLE:",
                          "GUIDANCE_WAIT_FAILED:")):
        return False, result
    if result.startswith("CLICK_TARGET_MOVED:"):
        return False, result
    # A physical click is enough to advance only when no explicit postcondition
    # was requested. When expect_text is supplied, missing text keeps us here.
    if result.startswith("CLICK_SEEN_NOT_VERIFIED:"):
        return (not bool(expect_text)), result
    if result.startswith("CLICK_AND_POSTCONDITION_VERIFIED:"):
        return True, result
    return False, result


def present_visual_lesson(parameters: dict, player=None, speak=None) -> str:
    """Present up to twelve ordered visual beats, optionally gated by real UI clicks."""
    params = parameters or {}
    if player is None or not callable(getattr(player, "show_visual_board", None)):
        return "PRESENTATION_UNAVAILABLE: the visual board is not connected."

    title = str(params.get("title") or "Explicação visual").strip()[:72] or "Explicação visual"
    subtitle = str(params.get("subtitle") or "").strip()[:150]
    deep = bool(params.get("deep", False))
    raw_beats = params.get("beats")
    layout = str(params.get("layout", "diagram"))
    if params.get("scene"):
        return "PRESENTATION_INVALID: generate beats for the actual question; preset scenes are not supported."
    if not isinstance(raw_beats, list) or not 1 <= len(raw_beats) <= _MAX_BEATS:
        return f"PRESENTATION_INVALID: provide 1 to {_MAX_BEATS} beats."

    # Validate every beat before the first one is drawn, avoiding half-started lessons.
    prepared: list[dict[str, Any]] = []
    try:
        for index, beat in enumerate(raw_beats, start=1):
            if not isinstance(beat, dict):
                raise ValueError(f"beat {index} must be an object")
            say = " ".join(str(beat.get("say") or "").split())[:180]
            if not say:
                raise ValueError(f"beat {index} needs a short say caption")
            elements = beat.get("elements")
            if not isinstance(elements, list) or not 1 <= len(elements) <= _MAX_BEAT_ELEMENTS:
                raise ValueError(f"beat {index} needs 1 to {_MAX_BEAT_ELEMENTS} visual elements")
            wait = str(beat.get("wait") or "").strip().lower()
            if wait not in {"", "click", "hover"}:
                raise ValueError(f"beat {index}: wait must be click, hover or omitted")
            target = str(beat.get("target") or "").strip()[:120]
            role = str(beat.get("role") or "").strip().lower()[:32]
            if wait in {"click", "hover"} and not target:
                raise ValueError(f"beat {index}: wait={wait} requires an exact target label")
            if wait == "hover" and str(beat.get("expect_text") or "").strip():
                raise ValueError(f"beat {index}: expect_text can only verify a click result")
            timeout = max(1.0, min(300.0, float(beat.get("timeout", 120) or 120)))
            expect_text = str(beat.get("expect_text") or "").strip()[:120]
            for element in elements:
                if not isinstance(element, dict):
                    raise ValueError(f"beat {index}: each element must be an object")
                kind = str(element.get("type") or "").lower()
                needed = {"line": ("x", "y", "x2", "y2"),
                          "arrow": ("x", "y", "x2", "y2"),
                          "dimension": ("x", "y", "x2", "y2"),
                          "angle": ("x", "y", "x2", "y2", "x3", "y3"),
                          "circle": ("x", "y"), "rect": ("x", "y")}.get(kind, ())
                if any(element.get(key) is None for key in needed):
                    raise ValueError(f"beat {index}: {kind} needs coordinates {', '.join(needed)}")
            try:
                payload = normalize_visual_payload({
                    "title": title,
                    "subtitle": subtitle,
                    "layout": layout,
                    "elements": elements,
                })
            except ValueError as exc:
                raise ValueError(f"beat {index}: {exc}") from exc
            if len(payload["elements"]) != len(elements):
                raise ValueError(
                    f"beat {index}: an element is invalid; check its type and required geometry, "
                    "then retry the complete lesson"
                )
            prepared.append({
                "say": say, "wait": wait, "target": target, "role": role,
                "timeout": timeout, "expect_text": expect_text, "payload": payload,
                "raw_elements": elements, "cue_words": beat.get("cue_words"),
            })
    except (TypeError, ValueError, OverflowError) as exc:
        return f"PRESENTATION_INVALID: {exc}"

    notes: list[str] = []
    total = len(prepared)
    captions = " | ".join(f"{i}. {beat['say']}" for i, beat in enumerate(prepared, 1))

    # Ordinary explanations are assembled in one board update and returned
    # immediately. Gemini then speaks these captions in its selected Live voice
    # while Qt continues the progressive reveal on the desktop.
    guided = any(beat["wait"] for beat in prepared)
    if not guided:
        combined = dict(prepared[0]["payload"])
        combined_elements = []
        combined_raw_elements = []
        lesson_timeline = []
        # Measured speech pace bridges gaps between transcript checkpoints.
        voice_cps = 13.0
        get_voice_cps = getattr(player, "get_visual_voice_cps", None)
        if callable(get_voice_cps):
            try:
                measured_cps = float(get_voice_cps())
                if 8.0 <= measured_cps <= 30.0:
                    voice_cps = measured_cps
            except (TypeError, ValueError, RuntimeError):
                pass
        voice_cursor = 0.0
        for beat_index, beat in enumerate(prepared, start=1):
            payload = beat["payload"]
            _prepare_assets(payload, notes)
            first_element = len(combined_elements)
            for item_index, raw_item in enumerate(payload.get("elements") or [], start=1):
                item = dict(raw_item)
                original_id = str(item.get("id") or f"element-{item_index}")
                item["id"] = f"b{beat_index}-{original_id}"[:64]
                combined_elements.append(item)
            combined_raw_elements.extend(beat["raw_elements"])
            # JARVIS-native voice clock: beat starts and durations use the
            # learned rate of the voice that will actually narrate this lesson.
            # Qt advances only while the corresponding PCM is audible.
            # Keep the audio-side pacing conservative: transcription can arrive
            # slightly ahead of the corresponding speaker output on a buffered device.
            beat_duration = max(1.2, len(beat["say"]) / voice_cps) * 1.12
            beat_start_seconds = voice_cursor
            beat_end_seconds = beat_start_seconds + beat_duration
            lesson_timeline.append({
                "index": beat_index,
                "start": first_element,
                "end": len(combined_elements),
                "caption": beat["say"],
                "duration": beat_duration,
                "start_seconds": beat_start_seconds,
                "end_seconds": beat_end_seconds,
                "voice_cps": voice_cps,
                "cues": _cue_fractions(
                    beat["say"], beat.get("cue_words"),
                    len(combined_elements) - first_element,
                ),
            })
            voice_cursor = beat_end_seconds + (1.0 / voice_cps)
        if len(combined_elements) > MAX_ELEMENTS:
            return (
                f"PRESENTATION_INVALID: the whole lesson can contain at most "
                f"{MAX_ELEMENTS} visual elements; this lesson has {len(combined_elements)}."
            )
        if total > 1 and not any(item["type"] in _DIAGRAM_TYPES for item in combined_elements):
            return (
                "PRESENTATION_INVALID: the lesson contains only text or cards. "
                "Retry with a meaningful subject-specific diagram: draw shapes and arrows "
                "or use a graph, map, molecule or timeline, with short labels."
            )
        try:
            from core.visual_board import enforce_3d
            enforce_3d(combined_elements, require_model=True)
        except ValueError as exc:
            return f"PRESENTATION_INVALID: {exc}"
        for _item in combined_elements:
            if _item.get("type") == "model3d":
                _item["id"] = "scene3d"
        _layout_missing_positions(combined_elements, combined_raw_elements)
        combined["elements"] = combined_elements
        combined["_lesson_timeline"] = lesson_timeline
        combined["_voice_cps"] = voice_cps
        start_audio = getattr(player, "start_marker_lesson", None)
        combined["_marker_sync"] = callable(start_audio)

        reveal_seconds = min(120.0, max(1.2, voice_cursor))
        try:
            player.show_visual_board(combined, operation="replace")
            player.set_visual_lesson_status(
                f"{title} — acompanhe as etapas", 1, total, False,
                draw_duration=reveal_seconds,
            )
        except Exception as exc:
            return (
                f"PRESENTATION_FAILED: could not display the visual lesson "
                f"({type(exc).__name__}: {str(exc)[:120]})."
            )

        extra = " " + " ".join(notes) if notes else ""
        if callable(start_audio):
            if not start_audio([beat["say"] for beat in prepared], title):
                player.set_visual_lesson_status("Narração indisponível", 0, total, True)
                return "PRESENTATION_UNAVAILABLE: the lesson audio could not be registered."
            return (
                f"PRESENTATION_SHOWN: {total} generated beats displayed; audio preparation started "
                "in the selected Gemini Live voice. Do not narrate these captions again: "
                "the speaker queue will play each prepared sentence with measured beat boundaries. "
                "Wait for the user's next question. Captions: " + captions + "." + extra
            )
        return (
            f"PRESENTATION_SHOWN: all {total} beats are on the editable progressive board. "
            "Begin speaking immediately in one continuous response. The board starts blank "
            "and follows your live transcription and speaker audio. Use your currently "
            "selected Gemini Live voice (never Windows/SAPI or another local system voice). "
            "Speak each caption verbatim in Brazilian Portuguese, exactly in order, with "
            "no paraphrase, no mentioning a later beat early, and no introduction beyond "
            "the one short opening sentence you already said. Captions: "
            + captions + "." + extra
        )

    # A guided walkthrough deliberately waits for the user's physical action.
    # Gemini cannot narrate during a blocking tool call, so the captions stay on
    # the board and the selected Live voice explains the completed sequence when
    # control returns to the model.
    shown = 0
    for index, beat in enumerate(prepared, start=1):
        payload = beat["payload"]
        _layout_missing_positions(payload["elements"], beat["raw_elements"])
        _prepare_assets(payload, notes)
        operation = "replace" if index == 1 or deep else "append"
        try:
            player.show_visual_board(payload, operation=operation)
            player.set_visual_lesson_status(beat["say"], index, total, False)
        except Exception as exc:
            return (
                f"PRESENTATION_FAILED: could not display beat {index}/{total} "
                f"({type(exc).__name__}: {str(exc)[:120]})."
            )

        if not _wait_for_drawing(player):
            return f"PRESENTATION_PAUSED: visual animation for beat {index}/{total} did not finish."
        shown = index
        if not beat["wait"]:
            continue

        waiting_action = "clique" if beat["wait"] == "click" else "passagem do cursor"
        waiting_caption = f"{beat['say']} — Aguardando {waiting_action} em {beat['target']}"
        try:
            player.set_visual_lesson_status(waiting_caption, index, total, True)
            completed, outcome = _wait_for_click(
                beat["target"], beat["role"], index, beat["timeout"],
                beat["expect_text"], player, beat["wait"]
            )
        except Exception as exc:
            completed, outcome = False, f"{type(exc).__name__}: {str(exc)[:120]}"
        if not completed:
            player.set_visual_lesson_status(
                f"Etapa {index} pausada — {beat['target']}", index, total, True
            )
            return (
                f"PRESENTATION_PAUSED: beat {index}/{total}; "
                f"{outcome} The lesson remains on this step."
            )
        if outcome.startswith(("CLICK_SEEN_NOT_VERIFIED:", "CLICK_TARGET_MOVED:")):
            notes.append(
                f"Beat {index}: click observed but not verified; the next target was re-read from the live screen."
            )

    try:
        player.set_visual_lesson_status("Etapas concluídas", total, total, False)
    except Exception:
        pass
    extra = " " + " ".join(notes) if notes else ""
    return (
        f"PRESENTATION_SHOWN: guided walkthrough displayed {shown}/{total} beats. "
        "The user completed the on-screen interactions. Now explain the captions in "
        "Brazilian Portuguese using your currently selected Gemini Live voice. Captions: "
        + captions + "." + extra
    )

TOOL = {
    "name": "present_visual_lesson",
    "description": (
        "Present an educational explanation as ordered visual beats on the real desktop. "
        "Use this by default for teaching a process, multi-step explanation, comparison or "
        "connected concepts; do not wait for the user to explicitly request a drawing. "
        "Generate the explanation, examples and visuals afresh for the actual question, including geometry. "
        "Say one short sentence naming the subject so the user hears you immediately, "
        "then call this tool in the same turn. The audio pipeline narrates your supplied captions; "
        "do not repeat them after the tool returns. Use show_visual only for one "
        "standalone diagram or a small visual addition. "
        "Always provide custom beats: there are no saved topic scenes or lesson scripts. "
        "Adapt the depth and illustration to this question and the user's follow-ups. "
        "For unfamiliar or changing facts, use the available research tools first rather than inventing facts. "
        "Each beat is {say, elements, wait?, "
        "target?, role?, timeout?, expect_text?}. say is the exact short caption that Gemini "
        "must narrate. IMPORTANT: narration always uses the currently selected Gemini Live "
        "voice. Never invoke Windows SAPI, the Windows narrator, Edge TTS, Piper or another "
        "local/system TTS voice. For an ordinary lesson with no click/hover waits, the tool "
        "stores each beat in its own visual range on one editable board and returns "
        "immediately. The board begins blank and follows your live transcription and "
        "speaker audio. Short audio segments are prepared concurrently and played in order; "
        "their actual sample counts determine stage boundaries, not character-rate estimates. "
        "Follow its result: never duplicate the prepared narration. "
        "Everything is a real-time holographic 3D scene; flat 2D elements are rejected. Each beat holds ONE model3d element in the same box "
        "(x=2, y=3, width=62, height=88), CUMULATIVE: it contains every part from earlier beats plus what this beat "
        "introduces, so the newest beat replaces the previous one and the camera and user rotation are kept. The first "
        "beat starts with a large recognizable subject body. model3d fields: shape (none or main body), parts[] (shape "
        "sphere/cube/cylinder/cone/torus/capsule/disc/pyramid/ring/plane, size, color, short label, dx/dy/dz, motion "
        "orbit/spin/pulse/bob/slide, parent, orbit_radius, tilt, node, count+arrange, opacity, glow, render_style "
        "solid/glass/hologram/glow) and links [{from,to,color,flow}] for animated flows. Abstract subjects (history, "
        "economy, code) become spatial 3D metaphors of labelled bodies. Short text/formula captions or a quiz go in "
        "the right column (x 67-98), never over the model. "
        "If PRESENTATION_INVALID is returned, fix the indicated "
        "elements and retry before speaking. Optional cue_words gives, per element, "
        "the word in say at which that element should appear. A lesson is limited to 48 visual "
        "elements total and 18 per beat. deep=true is for guided walkthroughs where one "
        "focused stage is intentionally shown at a time. For a real application walkthrough, "
        "set wait='click' or 'hover' and give target as the exact accessible label of one "
        "enabled control currently visible in the foreground Windows app. The tool highlights "
        "that real control, lets the user interact through the transparent visual overlay, "
        "and waits for a physical left click or a fresh hover held over the control. It "
        "re-reads the screen before resolving the next step. Since user interaction pauses "
        "the tool, keep captions visible; Gemini narrates after the walkthrough returns. "
        "Never guess the next target; give its exact label in that next beat. Escape or "
        "timeout pauses the lesson without claiming completion. A click is not proof that "
        "the application accepted it; provide expect_text only when a specific visible "
        "result must be verified. Speech preparation uses short sessions with the same Gemini Live model and selected voice; no extra service or local voice is used."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Short title for the whole lesson."},
            "subtitle": {"type": "STRING", "description": "Optional context line."},
            "layout": {"type": "STRING", "enum": [
                "diagram", "geometry", "graph", "formula", "steps",
                "comparison", "timeline", "science", "freeform"
            ]},
            "deep": {"type": "BOOLEAN", "description": "For a guided click/hover walkthrough, replace the previous stage with one focused card. Leave false for narrated lessons so all stages remain visible."},
            "beats": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "say": {"type": "STRING", "description": "A complete spoken sentence of at most 180 characters, explaining this visual step."},
                "cue_words": {"type": "ARRAY", "items": {"type": "STRING"}},
                "elements": {
                    "type": "ARRAY", "items": _LESSON_ELEMENT_SCHEMA,
                    "description": (
                        "One cumulative model3d scene with labelled parts and links, "
                        "plus optional short text/formula captions or one quiz. "
                        "Never use flat 2D primitives. Each beat preserves all earlier "
                        "parts and adds only the new ones."
                    ),
                },
                "wait": {"type": "STRING", "enum": ["click", "hover"]},
                "target": {"type": "STRING"},
                "role": {"type": "STRING"},
                "timeout": {"type": "NUMBER"},
                "expect_text": {"type": "STRING"},
            }, "required": ["say", "elements"]}},
        },
        "required": ["title", "beats"],
    },
    "handler": present_visual_lesson,
    "tier": "core",
    "brief": "Show a visual lesson one animated step at a time, with optional real desktop click waits.",
}
