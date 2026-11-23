"""Always-on-top interactive vector board for visual explanations."""
from __future__ import annotations

import copy
import logging
import math
import re

from PyQt6.QtCore import QTimer, pyqtSignal

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPainterPathStroker, QPen, QBrush, QPicture, QPolygonF
from PyQt6.QtWidgets import QApplication, QMenu, QWidget
from gui.visual_rich import draw_rich_element
from gui.style import hud_font
from gui.theme import C


_COLORS = {
    "cyan": QColor(87, 224, 255),
    "blue": QColor(100, 158, 255),
    "purple": QColor(185, 139, 255),
    "green": QColor(105, 230, 172),
    "amber": QColor(255, 194, 104),
    "red": QColor(255, 112, 128),
    "white": QColor(238, 246, 255),
    "muted": QColor(149, 177, 195),
    "pink": QColor(255, 143, 203),
}


class VisualBoardOverlay(QWidget):
    """Interactive floating drawing surface; it never takes keyboard focus."""

    quiz_answered = pyqtSignal(object)

    def __init__(self):
        super().__init__(None)
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self._base_window_flags = flags
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self._payload: dict = {}
        self._draw_errors: set[int] = set()
        self._board_rect = QRectF()
        self._canvas_rect = QRectF()
        self._drag_target = None
        self._generic_handles = []
        self._hover_position = None
        self._interactive_kind = ""
        self._triangle_a = 3.0
        self._triangle_b = 4.0
        self._initial_a = 3.0
        self._initial_b = 4.0
        self._animation_phase = 0.0
        self._animating = False
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._draw_timer = QTimer(self)
        self._draw_timer.setInterval(22)
        self._draw_timer.timeout.connect(self._tick_drawing)
        self._reveal_index = 0
        self._reveal_progress = 0.0
        self._reveal_step = 0.055
        self._triangle_reveal = 0.0
        self._close_rect = QRectF()
        self._model_phase = 0.0
        self._model_view_rotation: dict[str, tuple[float, float]] = {}
        self._model_drag_origin = None
        self._model_drag_initial = (0.0, 0.0)
        self._model_timer = QTimer(self)
        self._model_timer.setInterval(16)
        self._model_timer.timeout.connect(self._tick_models)
        self._quiz_rects = []
        self._lesson_caption = ""
        self._lesson_index = 0
        self._lesson_total = 0
        self._lesson_waiting = False
        self._lesson_timeline: list[dict] = []
        self._lesson_timeline_index = -1
        self._lesson_audio_elapsed = 0.0
        self._lesson_last_tick_at: float | None = None
        self._lesson_transcript_tokens: list[str] = []
        self._lesson_transcript_progress: list[float] = []
        self._lesson_uses_audio_checkpoints = False
        self._lesson_transcript_checkpoints: list[tuple[float, list[int]]] = []
        self._lesson_caption_checkpoints: list[tuple[float, str]] = []
        self._lesson_checkpoint_has_onset = False
        self._lesson_reveal_fractions = {}
        self._lesson_sample_timing = False
        self._sample_audio_windows = []
        self._lesson_sample_onset = None
        self._lesson_script_origin = None
        self._lesson_sample_end = None
        self._live_caption = ""
        self._audio_windows: list[tuple[float, float]] = []
        # Marker-synchronised lessons: beat boundaries come from the speech
        # stream itself (see core/pcm_clock.py), so no transcript matching or
        # speaking-rate estimate is involved.
        self._marker_mode = False
        self._playback_clock = None
        self._marks: dict[int, dict] = {}
        self._marker_frac: dict[int, float] = {}
        self._marker_started_at = 0.0
        self._semantic_focus = ""
        self._focus_phase = 0.0
        self._active_example_step = 0
        self._example_visible = False
        self._last_spoken_transcript = ""
        self._focus_timer = QTimer(self)
        self._focus_timer.setInterval(34)
        self._focus_timer.timeout.connect(self._tick_focus)
        self._input_passthrough = False

    @staticmethod
    def _wrapped_line_count(text: str, metrics: QFontMetrics, width: int) -> int:
        lines = 1
        current = ""
        for word in str(text or "").split():
            candidate = word if not current else current + " " + word
            if current and metrics.horizontalAdvance(candidate) > max(40, width):
                lines += 1
                current = word
            else:
                current = candidate
        return lines

    def copy_caption_text(self, mode: str = "both") -> str:
        """Copy the full live narration and/or current step caption."""
        parts = []
        if mode in {"live", "both"} and self._live_caption:
            parts.append(self._live_caption)
        if mode in {"step", "both"} and self._lesson_caption:
            parts.append(self._lesson_caption)
        text = "\n\n".join(parts)
        QApplication.clipboard().setText(text)
        return text

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        live_action = menu.addAction("Copy full live narration")
        step_action = menu.addAction("Copy current activity step")
        both_action = menu.addAction("Copy narration + activity step")
        live_action.setEnabled(bool(self._live_caption))
        step_action.setEnabled(bool(self._lesson_caption))
        both_action.setEnabled(bool(self._live_caption or self._lesson_caption))
        chosen = menu.exec(event.globalPos())
        if chosen is live_action:
            self.copy_caption_text("live")
        elif chosen is step_action:
            self.copy_caption_text("step")
        elif chosen is both_action:
            self.copy_caption_text("both")

    def set_lesson_status(self, caption: str, index: int = 0,
                          total: int = 0, waiting: bool = False,
                          draw_duration: float | None = None) -> None:
        self._lesson_caption = str(caption or "")
        self._lesson_index = max(0, int(index or 0))
        self._lesson_total = max(0, int(total or 0))
        self._lesson_waiting = bool(waiting)
        if self._lesson_timeline and not waiting:
            # Never announce the first teaching beat before its words arrive.
            if self._lesson_timeline_index < 0:
                self._lesson_caption = "Aguardando a fala do JARVIS..."
                self._lesson_index = 0
                self._lesson_total = len(self._lesson_timeline)
            else:
                self._sync_lesson_timeline(force=True)
        elif draw_duration is not None and not waiting:
            elements = self._payload.get("elements", [])
            total_elements = len(elements)
            remaining_units = (
                max(0.0, 1.0 - float(self._reveal_progress))
                + max(0, total_elements - int(self._reveal_index) - 1)
            )
            seconds = max(0.25, min(45.0, float(draw_duration)))
            if remaining_units > 0:
                self._reveal_step = max(0.0006, min(0.055, 0.022 * remaining_units / seconds))
            if elements and not self._draw_timer.isActive():
                self._draw_timer.start()
        self.update()

    @staticmethod
    def _spoken_key(text: str) -> str:
        import unicodedata
        value = unicodedata.normalize("NFKD", str(text or "").casefold())
        return "".join(ch for ch in value if not unicodedata.combining(ch))

    @classmethod
    def _spoken_tokens(cls, text: str) -> list[str]:
        """Tokenize captions like Gemini's transcript, ignoring punctuation/accents."""
        tokens = re.findall(r"[a-z0-9]+", cls._spoken_key(text))
        number_words = {
            "0": "zero", "1": "um", "2": "dois", "3": "tres",
            "4": "quatro", "5": "cinco", "6": "seis", "7": "sete",
            "8": "oito", "9": "nove", "10": "dez", "90": "noventa",
        }
        return [number_words.get(token, token) for token in tokens]

    @staticmethod
    def _find_ordered_caption(caption_tokens: list[str], live_tokens: list[str],
                              cursor: int, max_gap: int = 3) -> tuple[int, int, int]:
        """Find an ordered caption while tolerating a few dropped ASR words."""
        best_count = 0
        best_start = cursor
        best_end = cursor
        if not caption_tokens:
            return best_count, best_start, best_end

        for start in range(max(0, cursor), len(live_tokens)):
            seed = next((i for i, token in enumerate(caption_tokens[:3])
                         if live_tokens[start] == token and (i == 0 or len(token) >= 4)), None)
            if seed is None:
                continue
            count = seed + 1
            last = start
            skipped = seed
            hits = 1
            for expected_index, expected in enumerate(caption_tokens[seed + 1:], seed + 1):
                stop = min(len(live_tokens), last + max_gap + 2)
                found = None
                for pos in range(last + 1, stop):
                    token = live_tokens[pos]
                    if token == expected:
                        found = pos
                        break
                    if pos + 1 < len(live_tokens) and token + live_tokens[pos + 1] == expected:
                        found = pos + 1
                        break
                if found is None:
                    if skipped < 2:
                        skipped += 1
                        continue
                    break
                last = found
                hits += 1
                count = expected_index + 1
            if hits >= min(2, len(caption_tokens)) and count > best_count:
                best_count = count
                best_start = start
                best_end = last + 1
            if best_count == len(caption_tokens):
                break
        if best_count < 2:
            from difflib import SequenceMatcher
            window = live_tokens[cursor:cursor + len(caption_tokens) * 2 + max_gap]
            blocks = SequenceMatcher(None, caption_tokens, window, autojunk=False).get_matching_blocks()
            content_positions = [position for block in blocks
                                 for position in range(block.a, block.a + block.size)
                                 if len(caption_tokens[position]) >= 4
                                 and caption_tokens[position] not in {"para", "como", "essa", "esta"}]
            if len(content_positions) >= 2 and content_positions[0] < 3:
                matches = [block for block in blocks if block.size]
                best_count = matches[-1].a + matches[-1].size
                best_start = cursor + matches[0].b
                best_end = cursor + matches[-1].b + matches[-1].size
        return best_count, best_start, best_end

    def _refresh_lesson_transcript_progress(self, transcript: str) -> None:
        """Match ordered captions; tolerate small ASR omissions without skipping ahead."""
        live_tokens = self._spoken_tokens(transcript)
        self._lesson_transcript_tokens = live_tokens
        progress = [0] * len(self._lesson_timeline)
        cursor = 0
        for beat_index, beat in enumerate(self._lesson_timeline):
            caption_tokens = beat.get("_caption_tokens") or self._spoken_tokens(
                beat.get("caption", "")
            )
            if not caption_tokens:
                continue

            matched, _start, end = self._find_ordered_caption(
                caption_tokens, live_tokens, cursor
            )
            progress[beat_index] = matched
            if matched == len(caption_tokens):
                cursor = end
                continue

            # Live transcription occasionally drops the tail of a sentence.
            # When the next caption's first two words are present after the
            # current partial match, the previous beat has audibly moved on.
            # Mark that previous caption complete, then let the next iteration
            # independently match its full wording and PCM playhead.
            if beat_index + 1 < len(self._lesson_timeline) and matched >= 2:
                next_beat = self._lesson_timeline[beat_index + 1]
                next_tokens = next_beat.get("_caption_tokens") or self._spoken_tokens(
                    next_beat.get("caption", "")
                )
                next_matched, _next_start, _next_end = self._find_ordered_caption(
                    next_tokens, live_tokens, end
                )
                if next_matched >= min(2, len(next_tokens)):
                    progress[beat_index] = len(caption_tokens)
                    cursor = end
                    continue
            break
        self._lesson_transcript_progress = progress

    def set_live_caption(self, caption: str, *, _from_audio_checkpoint: bool = False) -> None:
        """Show live speech and use its latest concept to focus the teaching diagram."""
        if self._marker_mode and self._lesson_timeline:
            return  # marker lessons caption from their own script, never from ASR
        value = " ".join(str(caption or "").split())
        if not value and (self._payload.get("elements") or self._interactive_kind):
            value = "Aguardando a fala do JARVIS..."
        self._live_caption = value

        # In a timed lesson, incoming subtitles may be ahead of the speakers.
        # Their visible text, semantic focus and ink unlocks all wait for the
        # corresponding PCM checkpoint to become audible.
        if (self._lesson_timeline and self._lesson_uses_audio_checkpoints
                and not _from_audio_checkpoint):
            self.update()
            return

        spoken_full = self._spoken_key(caption)
        if self._lesson_timeline and not _from_audio_checkpoint:
            self._refresh_lesson_transcript_progress(caption)
        previous = self._last_spoken_transcript
        if spoken_full.startswith(previous):
            spoken_delta = spoken_full[len(previous):].strip()
        else:
            # Some Live transcript updates replace the partial hypothesis.
            spoken_delta = spoken_full
        self._last_spoken_transcript = spoken_full
        # Focus the diagram from newly spoken words. Narrated beats also require
        # ordered matches in this actual transcript; the speaker PCM clock is a
        # second independent gate, so neither estimate nor transcript alone can draw.
        focus_text = spoken_delta or spoken_full[-180:]
        focus_phrases = (
            (("hipotenusa",), "hypotenuse"),
            (("cateto a", "cateto vertical", "lado vertical"), "cateto_a"),
            (("cateto b", "cateto horizontal", "lado horizontal"), "cateto_b"),
            (("catetos", "cateto"), "catheti"),
            (("angulo reto", "angulo de 90", "noventa graus", "90 graus"), "right_angle"),
            (("formula", "equacao", "teorema de pitagoras"), "formula"),
        )
        latest_focus = (-1, "")
        for phrases, semantic in focus_phrases:
            for phrase in phrases:
                pos = focus_text.rfind(phrase)
                if pos > latest_focus[0]:
                    latest_focus = (pos, semantic)
        # When one sentence defines a side by relating it to the right angle,
        # illuminate both parts together rather than letting the final noun hide
        # the concept the sentence is actually teaching.
        angle_pos = max(
            focus_text.rfind("angulo reto"),
            focus_text.rfind("angulo de 90"),
            focus_text.rfind("noventa graus"),
            focus_text.rfind("90 graus"),
        )
        hypotenuse_pos = focus_text.rfind("hipotenusa")
        catheti_pos = max(focus_text.rfind("catetos"), focus_text.rfind("cateto"))
        concept_pos = max(hypotenuse_pos, catheti_pos)
        if (angle_pos >= 0 and concept_pos >= 0
                and 0 <= angle_pos - concept_pos <= 110):
            latest_focus = (
                angle_pos,
                "hypotenuse_and_right_angle"
                if hypotenuse_pos >= catheti_pos
                else "catheti_and_right_angle",
            )
        if latest_focus[0] >= 0 and self._interactive_kind == "right_triangle":
            self._semantic_focus = latest_focus[1]
            if not self._focus_timer.isActive():
                self._focus_timer.start()

        self.update()

    def set_live_caption_at_sample(self, caption: str, at: float) -> None:
        self._lesson_sample_timing = True
        self.set_live_caption_at_time(caption, at)

    def add_sample_audio_window(self, start: float, duration: float) -> None:
        if self._lesson_sample_end is not None:
            return
        self._lesson_sample_timing = True
        if self._lesson_timeline and not self._marker_mode:
            # PCM windows can arrive before the first transcript checkpoint.
            self._lesson_uses_audio_checkpoints = True
        start = float(start)
        if self._lesson_sample_onset is None or start < self._lesson_sample_onset:
            self._lesson_sample_onset = start
        self._sample_audio_windows.append((start, start + float(duration)))
        self._sample_audio_windows = self._sample_audio_windows[-120:]
        self._add_lesson_audio_onset()

    def set_live_caption_at_time(self, caption: str, audible_at: float) -> None:
        """Queue a transcript snapshot at the time its associated PCM reaches the speaker."""
        if self._marker_mode and self._lesson_timeline:
            return
        if not self._lesson_timeline:
            self.set_live_caption(caption)
            return
        try:
            boundary = float(audible_at)
            if not math.isfinite(boundary):
                return
        except (TypeError, ValueError, OverflowError):
            return

        if (self._lesson_sample_timing and self._lesson_sample_end is not None
                and boundary > self._lesson_sample_end):
            return
        self._lesson_uses_audio_checkpoints = True
        self._refresh_lesson_transcript_progress(caption)
        progress = list(self._lesson_transcript_progress)
        if self._lesson_transcript_checkpoints:
            previous_at, previous_progress = self._lesson_transcript_checkpoints[-1]
            # ASR corrections must never make spoken words disappear from the board.
            progress = [
                max(previous_progress[i] if i < len(previous_progress) else 0, value)
                for i, value in enumerate(progress)
            ]
            if boundary <= previous_at:
                if self._lesson_sample_timing:
                    self._lesson_transcript_checkpoints[-1] = (previous_at, progress)
                    self._lesson_caption_checkpoints[-1] = (previous_at, str(caption or ""))
                    self.update()
                    return
                boundary = previous_at + 0.001
            if progress == previous_progress:
                # The transcript text may stay unchanged while the final PCM for
                # that phrase is still being scheduled. Extend both the visual
                # and subtitle boundaries so neither gets ahead of the speaker.
                self._lesson_transcript_checkpoints[-1] = (boundary, previous_progress)
                self._lesson_caption_checkpoints[-1] = (boundary, str(caption or ""))
                self.update()
                return
        self._lesson_transcript_checkpoints.append((boundary, progress))
        self._lesson_caption_checkpoints.append((boundary, str(caption or "")))
        self._add_lesson_audio_onset()
        if len(self._lesson_transcript_checkpoints) > 512:
            # Keep the latest baseline plus enough recent checkpoints to interpolate smoothly.
            self._lesson_transcript_checkpoints = self._lesson_transcript_checkpoints[-384:]
            self._lesson_caption_checkpoints = self._lesson_caption_checkpoints[-384:]
        self.update()

    def _add_lesson_audio_onset(self) -> None:
        if (self._lesson_checkpoint_has_onset or not self._lesson_uses_audio_checkpoints
                or not self._lesson_transcript_checkpoints):
            return
        first_boundary = self._lesson_transcript_checkpoints[0][0]
        windows = self._sample_audio_windows if self._lesson_sample_timing else self._audio_windows
        starts = [start for start, _end in windows if start < first_boundary]
        if not starts:
            return
        onset = min(starts)
        self._lesson_transcript_checkpoints.insert(0, (onset, [0] * len(self._lesson_timeline)))
        self._lesson_caption_checkpoints.insert(0, (onset, ""))
        self._lesson_checkpoint_has_onset = True

    def _apply_audible_transcript_checkpoints(self) -> None:
        """Interpolate recognized words only across their scheduled speaker-time interval."""
        checkpoints = self._lesson_transcript_checkpoints
        if not checkpoints:
            self._lesson_transcript_progress = [0] * len(self._lesson_timeline)
            if self._live_caption != "Aguardando a fala do JARVIS...":
                self.set_live_caption("Aguardando a fala do JARVIS...", _from_audio_checkpoint=True)
            return
        # A small guard offsets subtitle/ASR delivery and output-device scheduling jitter.
        now = (float(self._playback_clock.audible_seconds()) if self._lesson_sample_timing
               and self._playback_clock is not None else __import__("time").time() - 0.045)
        if self._lesson_sample_timing and self._lesson_sample_end is not None:
            now = min(now, self._lesson_sample_end)
        prior_index = -1
        for index, (boundary, _progress) in enumerate(checkpoints):
            if boundary <= now:
                prior_index = index
            else:
                break
        if prior_index < 0:
            self._lesson_transcript_progress = [0] * len(self._lesson_timeline)
            if self._live_caption != "Aguardando a fala do JARVIS...":
                self.set_live_caption("Aguardando a fala do JARVIS...", _from_audio_checkpoint=True)
            return

        prior_at, prior_progress = checkpoints[prior_index]
        audible_caption = (
            self._lesson_caption_checkpoints[prior_index][1]
            if prior_index < len(self._lesson_caption_checkpoints) else ""
        )
        if prior_index + 1 < len(checkpoints):
            next_at, next_progress = checkpoints[prior_index + 1]
            fraction = max(0.0, min(1.0, (now - prior_at) / max(0.001, next_at - prior_at)))
            count = max(len(prior_progress), len(next_progress), len(self._lesson_timeline))
            self._lesson_transcript_progress = [
                (prior_progress[i] if i < len(prior_progress) else 0) * (1.0 - fraction)
                + (next_progress[i] if i < len(next_progress) else 0) * fraction
                for i in range(count)
            ][:len(self._lesson_timeline)]

            # The subtitle advances over the same audible interval as the ink.
            # When the next cumulative transcript adds words, expose those words
            # progressively instead of either showing the future sentence early
            # or freezing the caption on the previous beat.
            if prior_index + 1 < len(self._lesson_caption_checkpoints):
                next_caption = self._lesson_caption_checkpoints[prior_index + 1][1]
                prior_words = str(audible_caption or "").split()
                next_words = str(next_caption or "").split()
                common = 0
                while common < min(len(prior_words), len(next_words)):
                    if self._spoken_key(prior_words[common]) != self._spoken_key(next_words[common]):
                        break
                    common += 1
                if common == len(prior_words) and len(next_words) > common:
                    added = next_words[common:]
                    visible = min(len(added), int(round(fraction * len(added))))
                    audible_caption = " ".join(prior_words + added[:visible])
                elif fraction >= 1.0:
                    audible_caption = next_caption
        else:
            self._lesson_transcript_progress = list(prior_progress)

        if audible_caption != self._live_caption:
            self.set_live_caption(audible_caption, _from_audio_checkpoint=True)

    def _tick_focus(self) -> None:
        if not self.isVisible() or not self._semantic_focus:
            self._focus_timer.stop()
            return
        self._focus_phase = (self._focus_phase + 0.12) % (math.tau)
        self.update()

    def add_audio_playback_window(self, start: float, duration: float) -> None:
        """Record when a PCM batch is scheduled to be audible at the speakers."""
        import math
        start = float(start)
        duration = float(duration)
        if not math.isfinite(start) or not math.isfinite(duration) or duration <= 0:
            return
        end = start + min(2.0, duration)
        now = __import__("time").time()
        windows = [(a, b) for a, b in self._audio_windows if b >= now - 0.08]
        windows.append((start, end))
        windows.sort()
        merged: list[tuple[float, float]] = []
        for a, b in windows:
            if merged and a <= merged[-1][1] + 0.04:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        self._audio_windows = merged[-120:]
        self._add_lesson_audio_onset()
        self.update()

    def clear_audio_playback(self) -> None:
        self._audio_windows.clear()
        self._sample_audio_windows.clear()
        self._lesson_sample_onset = None
        self._lesson_script_origin = None
        self._lesson_sample_end = None
        self._lesson_transcript_checkpoints.clear()
        self._lesson_caption_checkpoints.clear()
        self._lesson_checkpoint_has_onset = False
        self._lesson_last_tick_at = None
        self.update()

    def _audio_is_playing(self) -> bool:
        import time as _time
        now = _time.time()
        # The transcript gate prevents future concepts from appearing early;
        # PCM still provides the audible-time gate. Keep this onset margin small:
        # 80 ms per short window repeatedly discarded real speech time on devices
        # that submit PCM in separated chunks.
        return any(start + 0.012 <= now <= end + 0.020
                   for start, end in self._audio_windows)

    def _sync_lesson_timeline(self, force: bool = False) -> None:
        """Advance the footer caption and reveal rate with the current beat range."""
        if not self._lesson_timeline:
            return
        index = int(self._reveal_index)
        beat = next((item for item in self._lesson_timeline
                     if int(item.get("start", 0)) <= index < int(item.get("end", 0))), None)
        if beat is None:
            if index >= len(self._payload.get("elements", [])):
                self._lesson_timeline_index = len(self._lesson_timeline)
                self._lesson_caption = "Etapas conclu\u00eddas"
                self._lesson_index = self._lesson_total = len(self._lesson_timeline)
                self._lesson_waiting = False
            return
        beat_index = int(beat.get("index", 1))
        if force or beat_index != self._lesson_timeline_index:
            self._lesson_timeline_index = beat_index
            self._lesson_caption = str(beat.get("caption") or "")
            self._lesson_index = beat_index
            self._lesson_total = len(self._lesson_timeline)
            self._lesson_waiting = False
            units = max(1, int(beat.get("end", 0)) - int(beat.get("start", 0)))
            seconds = max(0.6, min(30.0, float(beat.get("duration", 2.0) or 2.0)))
            # Keep the drawing moving with almost the full spoken line.
            # The previous 80% window made every visual finish noticeably early.
            draw_window = max(0.35, seconds * 0.94)
            self._reveal_step = max(0.0006, min(0.055, 0.022 * units / draw_window))

    def set_input_passthrough(self, enabled: bool) -> None:
        """Let a guided click reach the real Windows application under this board."""
        import platform
        import ctypes

        enabled = bool(enabled)
        self._input_passthrough = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if platform.system() == "Windows" and self.isVisible():
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            ex_style_index = -20  # GWL_EXSTYLE
            transparent_style = 0x00000020  # WS_EX_TRANSPARENT
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t
            style = int(get_style(ctypes.c_void_p(hwnd), ex_style_index))
            style = (style | transparent_style) if enabled else (style & ~transparent_style)
            set_style(ctypes.c_void_p(hwnd), ex_style_index, style)
            # Tell DWM/User32 to re-evaluate hit testing without moving or raising the window.
            set_pos = user32.SetWindowPos
            set_pos.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint
            ]
            set_pos.restype = ctypes.c_int
            set_pos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
                    0x0001 | 0x0002 | 0x0004 | 0x0020)
        self.update()

    def drawing_finished(self) -> bool:
        return not self._draw_timer.isActive()

    def hideEvent(self, event) -> None:
        self._model_timer.stop()
        self._anim_timer.stop()
        self._draw_timer.stop()
        self._focus_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if any(item.get("type") == "model3d"
               for group in (self._payload.get("elements", []), self._payload.get("_annotation_elements", []))
               for item in group):
            self._model_timer.start()
        if self._interactive_kind == "right_triangle" and self._animating:
            self._anim_timer.start()
        if self._semantic_focus:
            self._focus_timer.start()

    def set_content(self, payload: dict) -> None:
        self._payload = copy.deepcopy(payload or {})
        self._draw_errors.clear()
        raw_timeline = self._payload.get("_lesson_timeline") or []
        self._lesson_timeline = [dict(item) for item in raw_timeline
                                 if isinstance(item, dict)
                                 and int(item.get("end", 0)) > int(item.get("start", 0))]
        self._lesson_timeline_index = -1
        self._lesson_audio_elapsed = 0.0
        self._lesson_last_tick_at = None
        self._lesson_transcript_tokens = []
        self._lesson_transcript_progress = [0] * len(self._lesson_timeline)
        self._lesson_uses_audio_checkpoints = False
        self._lesson_transcript_checkpoints = []
        self._lesson_caption_checkpoints = []
        self._lesson_checkpoint_has_onset = False
        self._lesson_reveal_fractions = {}
        self._lesson_sample_timing = False
        self._sample_audio_windows = []
        self._lesson_sample_onset = None
        self._lesson_script_origin = None
        self._lesson_sample_end = None
        self._last_spoken_transcript = ""
        self._semantic_focus = ""
        self._live_caption = (
            "Aguardando a fala do JARVIS..." if self._lesson_timeline else ""
        )
        for beat in self._lesson_timeline:
            beat["_caption_tokens"] = self._spoken_tokens(beat.get("caption", ""))
        # Accept old saved lessons too: synthesize missing voice-clock offsets
        # from their caption lengths using the stored voice pace (13 chars/s fallback).
        voice_cps = max(8.0, min(30.0, float(self._payload.get("_voice_cps", 13.0) or 13.0)))
        voice_cursor = 0.0
        for beat in self._lesson_timeline:
            duration = max(1.2, float(beat.get("duration", 1.2) or 1.2))
            beat.setdefault("start_seconds", voice_cursor)
            beat.setdefault("end_seconds", float(beat["start_seconds"]) + duration)
            voice_cursor = max(voice_cursor, float(beat["end_seconds"])) + (1.0 / voice_cps)
        self._ensure_element_ids(self._payload.get("elements") or [])
        self._ensure_element_ids(self._payload.get("_annotation_elements") or [])
        interactive = self._payload.get("interactive") or {}
        self._interactive_kind = str(interactive.get("kind") or "")
        if self._interactive_kind == "right_triangle":
            self._triangle_a = max(0.5, min(10.0, float(interactive.get("a", 3.0))))
            self._triangle_b = max(0.5, min(10.0, float(interactive.get("b", 4.0))))
            self._initial_a = self._triangle_a
            self._initial_b = self._triangle_b
        self._drag_target = None
        self._hover_position = None
        self._animation_phase = 0.0
        self._animating = False
        self._anim_timer.stop()
        # Do not expose even the first mark until narration and speaker audio agree.
        self._reveal_index = -1 if self._lesson_timeline else 0
        self._reveal_progress = 0.0
        self._reveal_step = 0.055
        self._triangle_reveal = 0.0
        self._draw_timer.stop()
        self._semantic_focus = ""
        self._focus_phase = 0.0
        self._active_example_step = 0
        self._example_visible = False
        self._last_spoken_transcript = ""
        self._focus_timer.stop()
        self._model_phase = 0.0
        self._model_view_rotation.clear()
        self._model_drag_origin = None
        if any(item.get("type") == "model3d" for item in self._payload.get("elements", [])):
            self._model_timer.start()
        else:
            self._model_timer.stop()
        self._quiz_rects = []
        self._lesson_caption = ""
        self._lesson_index = 0
        self._lesson_total = 0
        self._lesson_waiting = False
        self._live_caption = (
            "Aguardando a fala do JARVIS..."
            if self._payload.get("elements") else ""
        )
        self._audio_windows.clear()
        self._marker_mode = bool(self._payload.get("_marker_sync")) and bool(self._lesson_timeline)
        self._marks = {}
        self._marker_frac = {}
        self._marker_started_at = __import__("time").monotonic()
        # Teaching diagrams always open on the Windows primary monitor.
        # The cursor may be on a secondary display; it must not choose the target.
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        # Teaching should have room for a readable diagram and a full worked
        # example. Use almost all of the primary display, not a small floating card.
        width = max(360, int(area.width() * 0.96))
        height = max(320, int(area.height() * 0.94))
        width = min(width, max(360, area.width() - 12))
        height = min(height, max(320, area.height() - 12))
        x = area.x() + (area.width() - width) // 2
        y = area.y() + (area.height() - height) // 2
        self.setGeometry(x, y, width, height)
        self._board_rect = QRectF(1, 1, width - 2, height - 2)
        self.update()
        self.show()
        self.raise_()
        if self._interactive_kind == "right_triangle" or self._payload.get("elements"):
            self._draw_timer.start()

    @staticmethod
    def _ensure_element_ids(elements: list) -> None:
        for index, item in enumerate(elements):
            if isinstance(item, dict):
                item.setdefault("id", f"element_{index + 1}")

    def append_content(self, payload: dict) -> None:
        """Append annotations without rebuilding or resetting the existing board."""
        incoming = copy.deepcopy(payload or {})
        if not incoming:
            return
        target = self._payload.setdefault("_annotation_elements", []) if self._interactive_kind == "right_triangle" else self._payload.setdefault("elements", [])
        start = len(target)
        added = list(incoming.get("elements") or [])
        for i, item in enumerate(added):
            item["id"] = str(item.get("id") or f"element_{start + i + 1}")
        target.extend(added)
        # A later manual annotation is not part of the original narrated beat
        # schedule, so return the footer to ordinary board mode.
        self._lesson_timeline = []
        self._lesson_timeline_index = -1
        if any(item.get("type") == "model3d" for item in added):
            self._model_timer.start()
        if self._interactive_kind != "right_triangle":
            self._reveal_index = start
            self._reveal_progress = 0.0
            self._reveal_step = 0.055
            if target:
                self._draw_timer.start()
        self.update()

    def describe_scene(self) -> dict:
        elements = list(self._payload.get("elements") or [])
        elements += list(self._payload.get("_annotation_elements") or [])
        return {
            "title": self._payload.get("title", ""),
            "interactive": self._interactive_kind,
            "elements": [
                {"element_id": item.get("id"), "type": item.get("type"),
                 "text": item.get("text") or item.get("label") or "",
                 "x": item.get("x"), "y": item.get("y"),
                 "x2": item.get("x2"), "y2": item.get("y2")}
                for item in elements
            ],
        }

    def edit_element(self, operation: str, element_id: str = "", patch: dict | None = None,
                     dx: float = 0.0, dy: float = 0.0) -> str:
        """Mutate one scene object by stable ID; never rebuild unrelated objects."""
        operation = str(operation or "").lower()
        collections = [self._payload.get("_annotation_elements", [])]
        if self._interactive_kind != "right_triangle":
            collections.append(self._payload.get("elements", []))
        pairs = [(items, item) for items in collections for item in items]
        if operation == "add":
            item = copy.deepcopy(patch or {})
            item["id"] = str(element_id or item.get("id") or f"element_{sum(len(x) for x in collections) + 1}")
            (collections[0] if self._interactive_kind == "right_triangle" else collections[-1]).append(item)
            self._ensure_element_ids(collections[-1])
            self._draw_timer.start()
            self.update()
            return f"added {item['id']}"
        found = next(((items, item) for items, item in pairs if str(item.get("id")) == str(element_id)), None)
        if found is None:
            return f"not_found: {element_id}"
        items, item = found
        if operation == "delete":
            items.remove(item)
        elif operation == "update":
            for key, value in (patch or {}).items():
                if key != "id":
                    item[key] = value
        elif operation == "move":
            dx, dy = float(dx), float(dy)
            for key in ("x", "x2", "x3"):
                if key in item: item[key] = max(0.0, min(100.0, float(item[key]) + dx))
            for key in ("y", "y2", "y3"):
                if key in item: item[key] = max(0.0, min(100.0, float(item[key]) + dy))
            for point in item.get("points", []):
                point["x"] = max(0.0, min(100.0, float(point.get("x", 50)) + dx))
                point["y"] = max(0.0, min(100.0, float(point.get("y", 50)) + dy))
        else:
            return "invalid_operation"
        self.update()
        return f"{operation}d {element_id}"

    def paintEvent(self, event):
        if not self._payload:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Nothing is painted behind the lesson. Only the ink, labels and subtle
        # text shadow are visible over the user's actual desktop.
        r = self._board_rect
        # The board must be visible on both bright and dark desktop backgrounds.
        # Use a restrained translucent glass surface rather than a fully invisible layer.
        panel = QRectF(5, 5, r.width() - 10, r.height() - 10)
        painter.setPen(QPen(QColor(132, 190, 220, 105), 1.2))
        surface = QColor(C.PANEL)
        surface.setAlpha(250 if self._lesson_timeline else 218)
        painter.setBrush(surface)
        painter.drawRoundedRect(panel, 22, 22)
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(panel.adjusted(5, 5, -5, -5), 18, 18)
        # Reserve a separate subtitle band only when live speech text is available.
        # This keeps the original board composition unchanged outside narrated lessons.
        canvas_bottom_gap = 148 if self._live_caption else 112
        canvas = QRectF(28, 78, r.width() - 56, max(120.0, r.height() - 78 - canvas_bottom_gap))
        self._canvas_rect = canvas

        title = str(self._payload.get("title") or "Explicação visual")
        subtitle = str(self._payload.get("subtitle") or "")
        painter.setPen(QColor(0, 0, 0, 150))
        painter.setFont(hud_font(18, QFont.Weight.DemiBold))
        painter.drawText(QRectF(31, 15, r.width() - 60, 34),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title[:72])
        painter.setPen(QColor(244, 250, 255))
        painter.drawText(QRectF(28, 12, r.width() - 60, 34),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title[:72])
        if subtitle:
            painter.setPen(QColor(0, 0, 0, 145))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRectF(29, 49, r.width() - 60, 22),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitle[:150])
            painter.setPen(QColor(194, 215, 229))
            painter.drawText(QRectF(27, 47, r.width() - 60, 22),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitle[:150])

        self._close_rect = QRectF(r.width() - 48, 12, 30, 30)
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 95), 1))
        painter.setBrush(QColor(120, 35, 48, 155))
        painter.drawEllipse(self._close_rect)
        painter.setPen(QPen(QColor(255, 225, 230), 2))
        cx, cy = self._close_rect.center().x(), self._close_rect.center().y()
        painter.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
        painter.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
        painter.restore()

        self._quiz_rects = []
        if self._interactive_kind == "right_triangle":
            examples = self._payload.get("_annotation_elements", [])
            guided_example = self._payload.get("_teaching_example") or {}
            has_side_panel = bool(guided_example or examples)
            self._draw_pencil_triangle(
                painter, canvas, show_formula=not has_side_panel
            )
            # The worked calculation occupies a dedicated full-height column;
            # free-form model coordinates are never painted over the triangle.
            if guided_example and self._example_visible:
                self._draw_guided_example_panel(painter, canvas, guided_example)
            elif examples:
                self._draw_triangle_example_panel(painter, canvas, examples)
            self._draw_interaction_controls(painter, r)
        else:
            self._generic_handles = []
            elements = self._payload.get("elements", [])
            for index, item in enumerate(elements):
                if self._lesson_timeline and (index > self._reveal_index or
                        (index == self._reveal_index and self._reveal_progress < 1.0)):
                    break
                self._collect_generic_handles(index, item, canvas)
            _models = [i for i, e in enumerate(elements)
                       if e.get("type") == "model3d" and i <= self._reveal_index]
            _superseded_3d = set(_models[:-1])
            for index, item in enumerate(elements):
                if index > self._reveal_index:
                    break
                if index in _superseded_3d:
                    continue
                painter.save()
                try:
                    if (item.get("type") == "arrow" and self._lesson_sample_timing
                            and self._playback_clock is not None):
                        beat = next((beat for beat in self._lesson_timeline
                                     if beat.get("index") == self._lesson_timeline_index), {})
                        if int(beat.get("start", 0)) <= index < int(beat.get("end", 0)):
                            item = dict(item, _flow_phase=float(self._playback_clock.audible_seconds()) % 1.4 / 1.4)
                    reveal = (max(0.0, min(1.0, self._reveal_progress))
                              if index == self._reveal_index else 1.0)
                    if item.get("type") == "model3d":
                        # Never wipe/fade a GPU scene: recording it into a QPicture every frame
                        # (and re-wiping the whole cumulative scene at each beat) dropped the
                        # lesson to ~20 fps. New parts already pop in inside the 3D engine.
                        self._draw_element(painter, canvas, item)
                    elif reveal < 1.0 and item.get("type") in {"line", "arrow", "dimension"}:
                        if reveal > 0:
                            partial = dict(item)
                            partial["x2"] = item["x"] + (item["x2"] - item["x"]) * reveal
                            partial["y2"] = item["y"] + (item["y2"] - item["y"]) * reveal
                            painter.setOpacity(0.18 + 0.82 * reveal)
                            self._draw_element(painter, canvas, partial)
                    elif reveal < 1.0 and item.get("type") in {"circle", "rect", "polygon", "polyline", "curve"}:
                        self._draw_revealing_shape(painter, canvas, item, reveal)
                    elif reveal < 1.0:
                        picture = QPicture()
                        picture_painter = QPainter(picture)
                        quiz_count = len(self._quiz_rects)
                        try:
                            picture_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                            picture_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                            self._draw_element(picture_painter, canvas, item)
                        finally:
                            picture_painter.end()
                            if self._lesson_timeline:
                                del self._quiz_rects[quiz_count:]
                        bounds = QRectF(picture.boundingRect())
                        painter.setClipRect(QRectF(bounds.left(), bounds.top(),
                                                   bounds.width() * reveal, bounds.height()))
                        painter.setOpacity(0.18 + 0.82 * reveal)
                        painter.drawPicture(0, 0, picture)
                    else:
                        self._draw_element(painter, canvas, item)
                except Exception:
                    if index not in self._draw_errors:
                        self._draw_errors.add(index)
                        logging.getLogger(__name__).exception("Failed to draw visual element %s", index)
                painter.restore()
            if self._reveal_index >= len(elements):
                self._draw_generic_handles(painter)
        # Live subtitles are visually distinct from the lesson-step footer.
        # They are fed by Gemini's output transcription, not a second TTS engine.
        if self._live_caption:
            painter.save()
            subtitle_width = max(160, int(r.width() - 56))
            text_width = max(100, subtitle_width - 96)
            caption_font = QFont("Segoe UI", 10, QFont.Weight.Medium)
            caption_metrics = QFontMetrics(caption_font)
            caption_lines = self._wrapped_line_count(self._live_caption, caption_metrics, text_width)
            max_caption_height = max(64, int(r.height() - 230))
            while caption_lines * caption_metrics.lineSpacing() + 14 > max_caption_height and caption_font.pointSizeF() > 8.0:
                caption_font.setPointSizeF(caption_font.pointSizeF() - 0.5)
                caption_metrics = QFontMetrics(caption_font)
                caption_lines = self._wrapped_line_count(self._live_caption, caption_metrics, text_width)
            panel_height = min(max_caption_height, max(46, caption_lines * caption_metrics.lineSpacing() + 14))
            subtitle_panel = QRectF(
                28, r.height() - 142 - (panel_height - 42), subtitle_width, panel_height
            )
            painter.setPen(QPen(QColor(87, 224, 255, 85), 1))
            painter.setBrush(QColor(12, 34, 49, 232))
            painter.drawRoundedRect(subtitle_panel, 11, 11)
            painter.setPen(QColor(133, 231, 255))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(
                QRectF(subtitle_panel.left() + 12, subtitle_panel.top() + 4,
                       70, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "AO VIVO",
            )
            painter.setPen(QColor(244, 250, 255))
            painter.setFont(caption_font)
            painter.drawText(
                QRectF(subtitle_panel.left() + 82, subtitle_panel.top() + 5,
                       subtitle_panel.width() - 96, subtitle_panel.height() - 10),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                self._live_caption,
            )
            painter.restore()

        # One shared footer retains the step indicator beneath the live subtitles.
        painter.save()
        footer = QRectF(28, r.height() - 48, r.width() - 56, 34)
        if self._lesson_caption:
            painter.setPen(QColor(230, 242, 251, 238))
            footer_font = QFont("Segoe UI", 9, QFont.Weight.Medium)
            footer_metrics = QFontMetrics(footer_font)
            footer_text_width = max(120, int(footer.width() - 128))
            footer_lines = self._wrapped_line_count(
                self._lesson_caption, footer_metrics, footer_text_width
            )
            footer_height = max(34, min(90, footer_lines * footer_metrics.lineSpacing() + 8))
            footer = QRectF(28, r.height() - 48 - (footer_height - 34),
                          r.width() - 56, footer_height)
            painter.setFont(footer_font)
            painter.drawText(
                QRectF(footer.left(), footer.top(), footer.width() - 128, footer.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap,
                self._lesson_caption,
            )
            if self._lesson_waiting:
                progress_text = "AGUARDANDO CLIQUE"
                progress_color = QColor(255, 205, 112)
            else:
                progress_text = (
                    f"ETAPA {self._lesson_index:02d}/{self._lesson_total:02d}"
                    if self._lesson_total else "JARVIS"
                )
                progress_color = QColor(133, 231, 255)
            painter.setPen(progress_color)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(
                QRectF(footer.right() - 124, footer.top(), 124, footer.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                progress_text,
            )
        else:
            painter.setPen(QColor(210, 228, 239, 190))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(
                footer, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Arraste os pontos para explorar • ESC para limpar",
            )
        painter.restore()
        painter.end()

    def _tick_drawing(self) -> None:
        # A narrated lesson is a queue of independent beats. Its playhead moves
        # only while PCM is audible, and each beat owns a closed element range.
        if self._lesson_timeline:
            if self._marker_mode:
                self._tick_marker_lesson()
                self.update()
                return
            if self._lesson_sample_timing:
                self._tick_voice_lesson()
                self.update()
                return
            import time as _time
            if not self._audio_is_playing():
                # Let a just-ended final PCM window settle its last transcript
                # checkpoint (including the small speaker safety offset), but do
                # not keep advancing through genuine silence.
                latest_end = max((end for _start, end in self._audio_windows), default=0.0)
                if (self._lesson_uses_audio_checkpoints
                        and latest_end > 0.0
                        and _time.time() - latest_end <= 0.14):
                    self._tick_voice_lesson()
                    self.update()
                    return
                if (self._lesson_last_tick_at is not None
                        and _time.monotonic() - self._lesson_last_tick_at > 0.045):
                    self._lesson_last_tick_at = None
                return
            now = _time.monotonic()
            delta = 0.022 if self._lesson_last_tick_at is None else max(
                0.0, min(0.08, now - self._lesson_last_tick_at)
            )
            self._lesson_last_tick_at = now
            self._lesson_audio_elapsed += delta
            self._tick_voice_lesson()
            self.update()
            return

        if self._interactive_kind == "right_triangle" and not self._audio_is_playing():
            return
        if self._interactive_kind == "right_triangle":
            # Legacy interactive diagrams still animate against the speaker.
            self._triangle_reveal = min(1.0, self._triangle_reveal + 0.0035)
            done = self._triangle_reveal >= 1.0
        else:
            self._reveal_progress += self._reveal_step
            if self._reveal_progress >= 1.0:
                self._reveal_progress = 0.0
                self._reveal_index += 1
            done = self._reveal_index >= len(self._payload.get("elements", []))
        self.update()
        if done:
            self._draw_timer.stop()

    # ── marker-synchronised lessons ─────────────────────────────────────────
    def set_playback_clock(self, clock) -> None:
        """Real speaker clock (core.pcm_clock.PcmPlayer)."""
        self._playback_clock = clock

    def add_lesson_mark(self, kind: str, index: int, at: float) -> None:
        """Speech boundary measured in the stream's own timeline (seconds)."""
        try:
            value = float(at)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value):
            return
        if not self._marker_mode and self._lesson_timeline:
            if kind == "narration_start":
                self.clear_audio_playback()
                self._lesson_transcript_tokens = []
                self._lesson_transcript_progress = [0] * len(self._lesson_timeline)
                self._lesson_sample_timing = True
                self._lesson_uses_audio_checkpoints = True
                self._lesson_sample_onset = value
                if not self._draw_timer.isActive():
                    self._draw_timer.start()
                return
            if kind == "narration_end":
                if self._lesson_sample_onset is not None and value >= self._lesson_sample_onset:
                    self._lesson_sample_end = value
                return
        if not self._marker_mode or kind not in ("start", "end"):
            return
        self._marks.setdefault(int(index), {"start": None, "end": None})[kind] = value
        if not self._draw_timer.isActive():
            self._draw_timer.start()

    def cancel_marker_lesson(self) -> None:
        """Interrupted: keep what is already drawn, stop waiting for more beats."""
        self._marks = {}
        self._marker_frac = {}
        self._marker_mode = False
        self._lesson_timeline = []
        self._lesson_timeline_index = -1
        self._live_caption = ""
        self._draw_timer.stop()
        self.update()

    @staticmethod
    def _beat_cue_windows(beat: dict, units: int, onset: float = 0.04) -> list[tuple[float, float]]:
        """(start, span) of each element's reveal as fractions of the beat."""
        cues = beat.get("cues") or []
        starts: list[float] = []
        if cues and len(cues) >= units and any(c is not None for c in cues[:units]):
            previous = 0.0
            for j in range(units):
                raw = cues[j]
                value = previous if raw is None else max(0.0, float(raw) - 0.05)
                value = max(previous, min(0.85, value))
                starts.append(value)
                previous = value
        else:
            step = 0.84 / max(1, units)
            starts = [onset + j * step for j in range(units)]
        windows = []
        for j, begin in enumerate(starts):
            limit = starts[j + 1] if j + 1 < units else 0.92
            span = max(0.08, (limit - begin) * 0.97 if limit > begin else 0.12)
            windows.append((begin, span))
        return windows

    def _tick_marker_lesson(self) -> None:
        """Reveal each beat from where the speech stream is right now."""
        import time as _time
        elements = self._payload.get("elements", [])
        timeline = self._lesson_timeline
        clock = self._playback_clock
        if clock is None or not timeline:
            return
        if not self._marks:
            self._lesson_caption = "Aguardando a fala do JARVIS..."
            if _time.monotonic() - self._marker_started_at > 25.0:
                # A missing marker is a failed narration hand-off, not permission
                # to reveal the whole lesson. Keep the canvas blank and stop the
                # poll timer; the first real marker will restart it.
                self._lesson_caption = "A narração ainda não iniciou"
                self._lesson_waiting = True
                self._draw_timer.stop()
            return
        try:
            now = float(clock.audible_seconds())
            written = float(clock.written_seconds())
        except Exception:
            return

        total = len(timeline)
        reveal_index, reveal_progress = -1, 0.0
        caption_beat = None
        subtitle = ""
        finished = 0
        for position, beat in enumerate(timeline):
            idx = int(beat.get("index", position + 1))
            slot = self._marks.get(idx) or {}
            start, end = slot.get("start"), slot.get("end")
            first, last = int(beat.get("start", 0)), int(beat.get("end", 0))
            units = max(1, last - first)
            say = str(beat.get("caption") or "")
            # At the exact START sample the first frame has not reached the
            # DAC yet. Wait until the playback clock advances beyond the mark.
            if start is None or now <= start:
                break
            if end is not None and now >= end:
                frac = 1.0
            elif end is not None:
                frac = (now - start) / max(0.05, end - start)
            else:
                # END not received yet (PCM still arriving): never run ahead of
                # the audio that exists. Resolved the moment the END mark lands.
                frac = min(0.9, (now - start) / max(0.05, written - start) * 0.9)
            frac = max(self._marker_frac.get(idx, 0.0), min(1.0, frac))
            self._marker_frac[idx] = frac
            caption_beat = beat
            words = say.split()
            shown = len(words) if frac >= 0.97 else max(
                1, int(round(frac / 0.97 * len(words))))
            subtitle = " ".join(words[:shown])
            if frac >= 1.0:
                reveal_index, reveal_progress = last - 1, 1.0
                finished += 1
                continue
            reveal_index, reveal_progress = first - 1, 1.0 if first > 0 else 0.0
            active = -1
            windows = self._beat_cue_windows(beat, units)
            for j, (begin, _span) in enumerate(windows):
                if frac >= begin:
                    active = j
            if active >= 0:
                begin, span = windows[active]
                reveal_index = first + active
                reveal_progress = max(0.0, min(1.0, (frac - begin) / span))
            break

        self._reveal_index = reveal_index
        self._reveal_progress = reveal_progress
        if caption_beat is not None:
            idx = int(caption_beat.get("index", 1))
            self._lesson_timeline_index = idx
            self._lesson_caption = str(caption_beat.get("caption") or "")
            self._lesson_index = idx
            self._lesson_total = total
            self._lesson_waiting = False
            self._live_caption = subtitle
        if finished >= total:
            self._reveal_index = len(elements)
            self._reveal_progress = 0.0
            self._lesson_caption = "Etapas concluídas"
            self._lesson_index = self._lesson_total = total
            self._draw_timer.stop()

    def _tick_voice_lesson(self) -> None:
        """Pace the narration script and transcript on the speaker's sample clock."""
        if not self._lesson_timeline:
            return
        if (not self._lesson_uses_audio_checkpoints and not self._lesson_sample_timing
                and not self._audio_is_playing()):
            return
        if self._lesson_uses_audio_checkpoints:
            self._apply_audible_transcript_checkpoints()
        elapsed = self._lesson_audio_elapsed

        # Anchor to recognized narration, not to any acknowledgment preceding it.
        audible_now = (float(self._playback_clock.audible_seconds())
                       if self._lesson_sample_timing and self._playback_clock is not None
                       else None)
        if audible_now is not None and self._lesson_sample_end is not None:
            audible_now = min(audible_now, self._lesson_sample_end)
        onset = self._lesson_sample_onset
        if (self._lesson_script_origin is None and audible_now is not None
                and self._lesson_uses_audio_checkpoints):
            for pos, anchor_beat in enumerate(self._lesson_timeline):
                anchor_matched = (self._lesson_transcript_progress[pos]
                                  if pos < len(self._lesson_transcript_progress) else 0)
                anchor_tokens = len(anchor_beat.get("_caption_tokens")
                                    or self._spoken_tokens(anchor_beat.get("caption", "")))
                if anchor_matched < min(2, anchor_tokens):
                    continue
                anchor_frac = min(1.0, anchor_matched / max(1, anchor_tokens))
                anchor_start = float(anchor_beat.get("start_seconds", 0.0) or 0.0)
                anchor_dur = max(0.6, float(anchor_beat.get("duration", 1.2) or 1.2))
                self._lesson_script_origin = audible_now - (anchor_start + anchor_frac * anchor_dur)
                break
        # An unrelated spoken introduction must not unlock the script fallback.
        has_asr_words = bool(self._lesson_transcript_tokens)
        script_only = (self._lesson_sample_timing and audible_now is not None
                       and onset is not None and not has_asr_words
                       and (audible_now - onset) > 2.0)
        script_base = (self._lesson_script_origin
                       if self._lesson_script_origin is not None
                       else (onset if script_only else None))
        if script_only:
            self._live_caption = "Transcrição indisponível; acompanhe a etapa da aula."

        for position, beat in enumerate(self._lesson_timeline):
            caption_tokens = beat.get("_caption_tokens") or self._spoken_tokens(
                beat.get("caption", "")
            )
            token_count = len(caption_tokens)
            matched = (
                self._lesson_transcript_progress[position]
                if position < len(self._lesson_transcript_progress) else 0
            )
            # Ignore lone articles until narration has a reliable sample-clock anchor.
            evidence = max((progress[position] for _at, progress in
                            self._lesson_transcript_checkpoints), default=matched)
            if (self._lesson_script_origin is None and not script_only
                    and (evidence < min(2, token_count) or matched <= 0.0
                         or (not self._lesson_sample_timing and matched < min(2, token_count)))):
                return

            transcript_progress = max(0.0, min(1.0, matched / max(1, token_count)))
            if self._lesson_uses_audio_checkpoints:
                script_progress = 0.0
                if script_base is not None and audible_now is not None:
                    start_seconds = float(beat.get("start_seconds", 0.0) or 0.0)
                    duration = max(0.6, float(beat.get("duration", 1.2) or 1.2))
                    script_progress = max(0.0, min(
                        1.0, (audible_now - script_base - start_seconds) / duration))
                allowed_progress = max(transcript_progress, script_progress)
            else:
                duration = max(0.6, float(beat.get("duration", 1.2) or 1.2))
                start_seconds = float(beat.get("start_seconds", 0.0) or 0.0)
                audio_progress = max(0.0, min(1.0, (elapsed - start_seconds) / duration))
                # Compatibility path for old lessons without scheduled checkpoints.
                allowed_progress = min(audio_progress, transcript_progress)
            if allowed_progress <= 0.0:
                return
            allowed_progress = max(self._lesson_reveal_fractions.get(position, 0.0), allowed_progress)
            self._lesson_reveal_fractions[position] = allowed_progress

            start = int(beat.get("start", 0))
            end = int(beat.get("end", start + 1))
            units = max(1, end - start)
            beat_index = int(beat.get("index", position + 1))
            self._lesson_timeline_index = beat_index
            self._lesson_caption = str(beat.get("caption") or "")
            self._lesson_index = beat_index
            self._lesson_total = len(self._lesson_timeline)
            self._lesson_waiting = False

            if allowed_progress >= 1.0:
                self._reveal_index = end - 1
                self._reveal_progress = 1.0
                continue

            windows = self._beat_cue_windows(beat, units, onset=0.0)
            active = 0
            for j, (begin, _span) in enumerate(windows):
                if allowed_progress >= begin:
                    active = j
            begin, span = windows[active]
            self._reveal_index = start + active
            self._reveal_progress = max(0.0, min(1.0, (allowed_progress - begin) / span))
            return

        self._reveal_index = len(self._payload.get("elements", []))
        self._reveal_progress = 0.0
        self._lesson_caption = "Etapas concluídas"
        self._lesson_index = self._lesson_total = len(self._lesson_timeline)
        self._lesson_waiting = False
        self._draw_timer.stop()

    def _draw_guided_example_panel(self, painter: QPainter, canvas: QRectF,
                                    example: dict) -> None:
        """Large, readable worked-example column linked to live spoken narration."""
        panel = QRectF(
            canvas.left() + canvas.width() * 0.59,
            canvas.top() + 3,
            canvas.width() * 0.405,
            canvas.height() - 6,
        )
        painter.save()
        painter.setPen(QPen(QColor(87, 224, 255, 125), 1.2))
        painter.setBrush(QColor(8, 22, 36, 242))
        painter.drawRoundedRect(panel, 17, 17)

        heading = str(example.get("heading") or "EXEMPLO RESOLVIDO")
        painter.setPen(QColor(132, 230, 255))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            QRectF(panel.left() + 16, panel.top() + 10, panel.width() - 32, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            heading,
        )

        question = str(example.get("question") or "")
        question_rect = QRectF(
            panel.left() + 12, panel.top() + 42, panel.width() - 24, 64
        )
        painter.setPen(QPen(QColor(105, 174, 207, 105), 1))
        painter.setBrush(QColor(20, 49, 69, 225))
        painter.drawRoundedRect(question_rect, 10, 10)
        painter.setPen(QColor(236, 246, 253))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.drawText(
            question_rect.adjusted(11, 7, -11, -7),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            | Qt.TextFlag.TextWordWrap,
            question,
        )

        all_steps = [step for step in (example.get("steps") or [])[:6]
                     if isinstance(step, dict)]
        if not all_steps:
            painter.restore()
            return
        active = max(0, min(len(all_steps) - 1, int(self._active_example_step)))
        # Reveal the worked solution progressively. Future calculations do not
        # appear until Gemini actually says the corresponding step.
        steps = all_steps[:active + 1]
        gap = 7.0
        body_top = question_rect.bottom() + 12
        body_height = max(80.0, panel.bottom() - body_top - 12)
        card_height = (body_height - gap * (len(steps) - 1)) / len(steps)

        for index, step in enumerate(steps):
            top = body_top + index * (card_height + gap)
            card = QRectF(panel.left() + 10, top, panel.width() - 20, card_height)
            if index == active:
                pulse = 0.65 + 0.35 * (math.sin(self._focus_phase) + 1.0) / 2.0
                border = QColor(87, 224, 255, int(130 + 100 * pulse))
                fill = QColor(19, 57, 78, 248)
                title_color = QColor(142, 233, 255)
                equation_color = QColor(255, 255, 255)
            elif index < active:
                border = QColor(105, 230, 172, 95)
                fill = QColor(14, 43, 42, 205)
                title_color = QColor(142, 220, 183)
                equation_color = QColor(205, 238, 220)
            else:
                border = QColor(112, 145, 165, 48)
                fill = QColor(17, 34, 49, 175)
                title_color = QColor(155, 180, 197)
                equation_color = QColor(188, 205, 218)

            painter.setPen(QPen(border, 1.4 if index == active else 0.9))
            painter.setBrush(fill)
            painter.drawRoundedRect(card, 10, 10)

            title = str(step.get("title") or f"Etapa {index + 1}")
            equation = str(step.get("equation") or "")
            detail = str(step.get("detail") or "")
            painter.setPen(title_color)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(
                QRectF(card.left() + 11, card.top() + 5, card.width() - 22, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title,
            )
            painter.setPen(equation_color)
            equation_size = 14 if len(equation) < 29 else 11
            painter.setFont(QFont("Segoe UI", equation_size, QFont.Weight.Bold))
            painter.drawText(
                QRectF(card.left() + 11, card.top() + 22,
                       card.width() - 22, max(20, card.height() * 0.38)),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap,
                equation,
            )
            if detail:
                painter.setPen(QColor(174, 199, 215) if index >= active
                               else QColor(177, 219, 197))
                painter.setFont(QFont("Segoe UI", 9))
                painter.drawText(
                    QRectF(card.left() + 11, card.top() + card.height() * 0.62,
                           card.width() - 22, max(16, card.height() * 0.32)),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    | Qt.TextFlag.TextWordWrap,
                    detail,
                )
        painter.restore()

    def _draw_triangle_example_panel(self, painter: QPainter, canvas: QRectF,
                                     examples: list[dict]) -> None:
        """Render worked examples in a reserved column, never on top of the triangle."""
        panel = QRectF(
            canvas.left() + canvas.width() * 0.62,
            canvas.top() + 6,
            canvas.width() * 0.36,
            max(80.0, canvas.height() - 12),
        )
        painter.save()
        painter.setPen(QPen(QColor(87, 224, 255, 110), 1.1))
        painter.setBrush(QColor(8, 25, 39, 228))
        painter.drawRoundedRect(panel, 13, 13)
        painter.setPen(QColor(133, 231, 255))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(
            panel.adjusted(12, 8, -10, -panel.height() + 30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "EXEMPLO RESOLVIDO",
        )

        visible = [item for item in examples[:5] if isinstance(item, dict)]
        if not visible:
            painter.restore()
            return
        body = panel.adjusted(9, 36, -9, -9)
        slot_gap = 5.0
        slot_height = max(28.0, (body.height() - slot_gap * (len(visible) - 1)) / len(visible))
        for index, item in enumerate(visible):
            top = body.top() + index * (slot_height + slot_gap)
            slot = QRectF(body.left(), top, body.width(),
                          min(slot_height, body.bottom() - top))
            if slot.height() < 18:
                break
            kind = str(item.get("type") or "text").lower()
            is_formula = kind == "formula"
            accent = QColor(87, 224, 255) if is_formula else QColor(149, 177, 195)
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 85), 0.9))
            painter.setBrush(QColor(18, 43, 59, 205))
            painter.drawRoundedRect(slot, 8, 8)

            title = str(item.get("title") or item.get("heading") or "").strip()
            parts = []
            if title:
                parts.append(title)
            if kind in {"text", "formula"}:
                value = str(item.get("text") or item.get("label") or "").strip()
                if value:
                    parts.append(value)
            elif kind in {"card", "list"}:
                value = str(item.get("text") or "").strip()
                if value:
                    parts.append(value)
                parts.extend(str(value) for value in (item.get("items") or [])[:5] if str(value).strip())
            elif kind == "table":
                if item.get("columns"):
                    parts.append("  |  ".join(str(v) for v in item.get("columns", [])[:4]))
                for row in (item.get("rows") or [])[:3]:
                    parts.append("  |  ".join(str(v) for v in row[:4]))
            elif kind == "quiz":
                parts.append(str(item.get("text") or item.get("label") or ""))
                parts.extend(str(v) for v in (item.get("options") or [])[:3])
            else:
                value = str(item.get("text") or item.get("label") or "").strip()
                if value:
                    parts.append(value)

            content = "\n".join(part for part in parts if part).strip()
            if content:
                if is_formula:
                    font_size = max(10, min(14, int(item.get("font_size", 13))))
                    font = QFont("Segoe UI", font_size, QFont.Weight.Bold)
                    color = QColor(231, 248, 255)
                    alignment = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                else:
                    font_size = 9 if slot.height() < 54 or len(content) > 115 else 10
                    font = QFont("Segoe UI", font_size,
                                 QFont.Weight.DemiBold if title else QFont.Weight.Normal)
                    color = QColor(225, 239, 249)
                    alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                painter.setFont(font)
                painter.setPen(color)
                painter.drawText(
                    slot.adjusted(9, 5, -9, -5),
                    alignment | Qt.TextFlag.TextWordWrap,
                    content[:360],
                )
            else:
                # Preserve meaningful small diagrams, but constrain each one to
                # its own card-sized slot instead of using desktop-wide coordinates.
                local = dict(item)
                local["anchor"] = ""
                local["x"], local["y"] = 4, 4
                local["width"], local["height"] = 92, 92
                self._draw_element(painter, slot.adjusted(7, 5, -7, -5), local)
        painter.restore()

    def _draw_pencil_triangle(self, painter: QPainter, canvas: QRectF,
                              show_formula: bool = True) -> None:
        a_pt, b_pt, c_pt, scale = self._triangle_geometry(canvas)
        a, b = self._triangle_a, self._triangle_b
        c = math.hypot(a, b)
        progress = max(0.0, min(1.0, self._triangle_reveal))
        points = [(a_pt, b_pt), (b_pt, c_pt), (c_pt, a_pt)]
        # Draw each side in sequence, with a moving pencil tip.
        for idx, (p1, p2) in enumerate(points):
            local = max(0.0, min(1.0, progress * (3.0 / 0.56) - idx))
            if local <= 0:
                continue
            tip = QPointF(p1.x() + (p2.x() - p1.x()) * local,
                          p1.y() + (p2.y() - p1.y()) * local)
            self._glow_line(painter, p1, tip, QColor(87, 224, 255), 2.8)
            if local < 1.0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 230))
                painter.drawEllipse(tip, 4.0, 4.0)

        # Staged construction: right-angle marker, labels, then formula and
        # calculations. Every part is revealed progressively, never all at once.
        marker_t = max(0.0, min(1.0, (progress - 0.56) / 0.10))
        labels_t = max(0.0, min(1.0, (progress - 0.66) / 0.18))
        formula_t = (
            max(0.0, min(1.0, (progress - 0.84) / 0.16))
            if show_formula else 0.0
        )

        painter.save()
        if marker_t > 0:
            painter.setOpacity(marker_t)
            marker = 19
            painter.setPen(self._pen(QColor(255, 194, 104), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(a_pt.x(), a_pt.y() - marker, marker, marker))
            painter.setPen(QColor(255, 207, 131))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            painter.drawText(QRectF(a_pt.x()+22, a_pt.y()-28, 50, 22),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "90°")
        painter.restore()

        # Labels are written one after another, character by character.
        label_items = [
            (QRectF(a_pt.x() - 80, (a_pt.y()+b_pt.y())/2 - 13, 150, 26),
             f"Cateto a = {self._fmt(a)}", QColor(139, 244, 190)),
            (QRectF((a_pt.x()+c_pt.x())/2 - 65, a_pt.y()+9, 150, 26),
             f"Cateto b = {self._fmt(b)}", QColor(139, 244, 190)),
            (QRectF((b_pt.x()+c_pt.x())/2 - 15, (b_pt.y()+c_pt.y())/2 - 32, 205, 26),
             f"Hipotenusa c = {self._fmt(c)}", QColor(255, 143, 203)),
        ]
        if labels_t > 0:
            painter.save()
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            for idx, (rect, label, color) in enumerate(label_items):
                local = max(0.0, min(1.0, (labels_t * 3.0) - idx))
                if local <= 0:
                    continue
                count = max(1, int(len(label) * local))
                painter.setPen(color)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label[:count])
            painter.restore()

        if progress >= 0.66:
            self._draw_handle(painter, b_pt, "A")
            self._draw_handle(painter, c_pt, "B")

        self._draw_triangle_semantic_focus(painter, canvas)

        if formula_t > 0:
            painter.save()
            fx = canvas.left() + canvas.width() * 0.66
            fy = canvas.top() + 82
            formula = f"{a:.1f}² + {b:.1f}² = {c:.1f}²".replace(".", ",")
            painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
            count = max(1, int(len(formula) * formula_t))
            painter.setPen(QColor(0, 0, 0, 160))
            painter.drawText(QRectF(fx+2, fy+2, canvas.width()*0.32, 42),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, formula[:count])
            painter.setPen(QColor(222, 248, 255))
            painter.drawText(QRectF(fx, fy, canvas.width()*0.32, 42),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, formula[:count])
            if formula_t > 0.55:
                explain = "O quadrado da hipotenusa é igual à soma dos quadrados dos catetos."
                explain_t = min(1.0, (formula_t - 0.55) / 0.45)
                painter.setOpacity(explain_t)
                painter.setPen(QColor(184, 213, 229))
                painter.setFont(QFont("Segoe UI", 11))
                painter.drawText(QRectF(fx, fy+48, canvas.width()*0.30, 68),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                                 explain[:max(1, int(len(explain)*explain_t))])
            if formula_t >= 0.78:
                values_t = min(1.0, (formula_t - 0.78) / 0.22)
                painter.setOpacity(values_t)
                self._draw_live_triangle_values(painter, fx, fy+145, canvas)
            painter.restore()
        painter.restore()

    def _draw_triangle_semantic_focus(self, painter: QPainter, canvas: QRectF) -> None:
        """Pulse the exact side or angle currently being named by the narrator."""
        focus = self._semantic_focus
        if not focus:
            return
        a_pt, b_pt, c_pt, _ = self._triangle_geometry(canvas)
        segments = []
        if focus in {"catheti", "catheti_and_right_angle", "cateto_a"}:
            segments.append((a_pt, b_pt))
        if focus in {"catheti", "catheti_and_right_angle", "cateto_b"}:
            segments.append((c_pt, a_pt))
        if focus in {"hypotenuse", "hypotenuse_and_right_angle"}:
            segments.append((b_pt, c_pt))

        painter.save()
        pulse = 0.62 + 0.38 * (math.sin(self._focus_phase) + 1.0) / 2.0
        accent = QColor(255, 205, 112) if focus == "hypotenuse" else QColor(116, 238, 255)
        if segments:
            glow = QColor(accent)
            glow.setAlpha(int(48 + 70 * pulse))
            for start, end in segments:
                painter.setPen(self._pen(glow, 16))
                painter.drawLine(start, end)
                painter.setPen(self._pen(accent, 4.5))
                painter.drawLine(start, end)
                mid = QPointF((start.x() + end.x()) / 2,
                              (start.y() + end.y()) / 2)
                painter.setPen(QPen(QColor(255, 255, 255, int(150 * pulse)), 1.2))
                painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 42))
                painter.drawEllipse(mid, 8 + 2 * pulse, 8 + 2 * pulse)
        if focus in {"right_angle", "hypotenuse_and_right_angle",
                     "catheti_and_right_angle"}:
            marker = QRectF(a_pt.x() - 5, a_pt.y() - 43, 56, 56)
            painter.setPen(QPen(QColor(255, 205, 112, int(110 + 110 * pulse)), 3))
            painter.setBrush(QColor(255, 194, 104, 28))
            painter.drawRoundedRect(marker, 10, 10)
        painter.restore()

    def _draw_live_triangle_values(self, painter: QPainter, x: float, y: float,
                                   canvas: QRectF) -> None:
        a, b = self._triangle_a, self._triangle_b
        c = math.hypot(a, b)
        painter.setPen(QColor(145, 220, 255))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(QPointF(x, y), "MEDIDAS ATUALIZADAS AO ARRASTAR")
        painter.setPen(QColor(139, 244, 190))
        painter.drawText(QPointF(x, y+28), f"a = {self._fmt(a)}     a² = {self._fmt(a*a)}")
        painter.setPen(QColor(140, 184, 255))
        painter.drawText(QPointF(x, y+54), f"b = {self._fmt(b)}     b² = {self._fmt(b*b)}")
        painter.setPen(QColor(255, 143, 203))
        painter.drawText(QPointF(x, y+80), f"c = {self._fmt(c)}     c² = {self._fmt(c*c)}")

    def _point(self, canvas: QRectF, x, y) -> QPointF:
        return QPointF(canvas.left() + canvas.width() * float(x) / 100.0,
                       canvas.top() + canvas.height() * float(y) / 100.0)

    def _color(self, item: dict) -> QColor:
        return QColor(_COLORS.get(str(item.get("color") or "cyan"), _COLORS["cyan"]))

    def _pen(self, color: QColor, width: float, *, dashed=False) -> QPen:
        pen = QPen(color, width, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _glow_line(self, painter: QPainter, a: QPointF, b: QPointF,
                   color: QColor, width: float, arrow=False) -> None:
        glow = QColor(color)
        glow.setAlpha(52)
        painter.setPen(self._pen(glow, width * 4))
        painter.drawLine(a, b)
        painter.setPen(self._pen(color, width))
        painter.drawLine(a, b)
        if arrow:
            angle = math.atan2(b.y() - a.y(), b.x() - a.x())
            size = max(8.0, width * 4.0)
            for delta in (2.55, -2.55):
                tip = QPointF(b.x() + math.cos(angle + delta) * size,
                              b.y() + math.sin(angle + delta) * size)
                painter.drawLine(b, tip)

    def _draw_grid(self, painter: QPainter, canvas: QRectF, layout: str) -> None:
        if layout not in {"geometry", "graph", "science"}:
            return
        divisions = 10 if layout == "graph" else 8
        painter.save()
        painter.setPen(QPen(QColor(82, 157, 188, 24), 1))
        for i in range(1, divisions):
            x = canvas.left() + canvas.width() * i / divisions
            y = canvas.top() + canvas.height() * i / divisions
            painter.drawLine(QPointF(x, canvas.top()), QPointF(x, canvas.bottom()))
            painter.drawLine(QPointF(canvas.left(), y), QPointF(canvas.right(), y))
        painter.restore()

    def _curve_path(self, canvas: QRectF, item: dict) -> QPainterPath:
        points = [self._point(canvas, p["x"], p["y"]) for p in item.get("points", [])]
        path = QPainterPath()
        closed = bool(item.get("closed"))
        if len(points) < (3 if closed else 2):
            return path
        path.moveTo(points[0])
        count = len(points)
        for index in range(count if closed else count - 1):
            before = points[(index - 1) % count] if closed else points[max(0, index - 1)]
            start = points[index]
            end = points[(index + 1) % count]
            after = points[(index + 2) % count] if closed else points[min(count - 1, index + 2)]
            path.cubicTo(start + (end - before) / 6, end - (after - start) / 6, end)
        if closed:
            path.closeSubpath()
        return path

    def _draw_revealing_shape(self, painter: QPainter, canvas: QRectF,
                              item: dict, reveal: float) -> None:
        if reveal <= 0.0:
            return
        path = QPainterPath()
        a = self._point(canvas, item.get("x", 50), item.get("y", 50))
        kind = item.get("type")
        if kind == "curve":
            path = self._curve_path(canvas, item)
        elif kind == "circle":
            radius = min(canvas.width(), canvas.height()) * float(item.get("radius", 8)) / 100
            path.addEllipse(QRectF(a.x() - radius, a.y() - radius, radius * 2, radius * 2))
        elif kind == "rect":
            path.addRoundedRect(QRectF(a.x(), a.y(),
                canvas.width() * float(item.get("width", 20)) / 100,
                canvas.height() * float(item.get("height", 12)) / 100), 8, 8)
        else:
            points = [self._point(canvas, p["x"], p["y"]) for p in item.get("points", [])]
            if not points:
                return
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            if kind == "polygon":
                path.closeSubpath()
        length = path.length() * reveal
        stroke = QPainterPath()
        steps = max(2, int(length / 3))
        for i in range(steps + 1):
            point = path.pointAtPercent(path.percentAtLength(length * i / steps))
            if i == 0:
                stroke.moveTo(point)
            else:
                stroke.lineTo(point)
        color = self._color(item)
        painter.setPen(self._pen(color, float(item.get("stroke_width", 2))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(stroke)
        if item.get("fill") and reveal > 0.75:
            fill = QColor(color)
            fill.setAlpha(int(35 * (reveal - 0.75) / 0.25))
            painter.fillPath(path, fill)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(point, 3, 3)

    def _draw_element(self, painter: QPainter, canvas: QRectF, item: dict) -> None:
        kind = item.get("type")
        color = self._color(item)
        width = float(item.get("stroke_width", 2))
        a = self._point(canvas, item.get("x", 50), item.get("y", 50))
        b = self._point(canvas, item.get("x2", 75), item.get("y2", 50))
        anchor = str(item.get("anchor") or "")
        if self._interactive_kind == "right_triangle" and anchor:
            a_pt, b_pt, c_pt, _ = self._triangle_geometry(canvas)
            if anchor == "triangle_equation":
                a = QPointF(canvas.left() + canvas.width() * 0.66,
                            canvas.top() + 82 - 48)
            elif anchor == "triangle_a_label":
                a = QPointF(a_pt.x() - 80, (a_pt.y() + b_pt.y()) / 2 - 42)
            elif anchor == "triangle_b_label":
                a = QPointF((a_pt.x() + c_pt.x()) / 2 - 65, a_pt.y() - 38)
            elif anchor == "triangle_hypotenuse_label":
                a = QPointF((b_pt.x() + c_pt.x()) / 2 - 15,
                            (b_pt.y() + c_pt.y()) / 2 - 62)
            a = QPointF(a.x() + float(item.get("offset_x", 0)),
                        a.y() + float(item.get("offset_y", 0)))
        painter.save()
        if kind in {"card", "list", "table", "timeline", "graph", "mindmap", "model3d", "quiz", "photo", "map", "molecule"}:
            draw_item = item
            if kind == "model3d":
                rotation = self._model_view_rotation.get(str(item.get("id") or ""))
                if rotation is not None:
                    draw_item = dict(item, _view_rotation=rotation)
            self._quiz_rects.extend(
                draw_rich_element(painter, canvas, draw_item, color, self._model_phase)
            )
            painter.restore()
            return

        if kind in {"line", "arrow", "dimension"}:
            self._glow_line(painter, a, b, color, width, arrow=kind == "arrow")
            if kind == "arrow" and "_flow_phase" in item:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(C.WHITE))
                for offset in (0.0, 0.33, 0.66):
                    t = (float(item["_flow_phase"]) + offset) % 1.0
                    painter.drawEllipse(QPointF(a.x() + (b.x() - a.x()) * t,
                                               a.y() + (b.y() - a.y()) * t), 3, 3)
            if kind == "dimension":
                self._glow_line(painter, a, b, color, width, arrow=False)
                angle = math.atan2(b.y() - a.y(), b.x() - a.x())
                size = 7
                for pt, direction in ((a, angle), (b, angle + math.pi)):
                    for delta in (2.55, -2.55):
                        tip = QPointF(pt.x() + math.cos(direction + delta) * size,
                                      pt.y() + math.sin(direction + delta) * size)
                        painter.drawLine(pt, tip)
                label = str(item.get("label") or item.get("text") or "")
                if label:
                    painter.setPen(color)
                    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
                    painter.drawText(QRectF((a.x()+b.x())/2 - 70, (a.y()+b.y())/2 - 28, 140, 22),
                                     Qt.AlignmentFlag.AlignCenter, label[:70])

        elif kind == "circle":
            radius = min(canvas.width(), canvas.height()) * float(item.get("radius", 8)) / 100.0
            rect = QRectF(a.x() - radius, a.y() - radius, radius * 2, radius * 2)
            painter.setPen(self._pen(color, width))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 35) if item.get("fill") else Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

        elif kind == "rect":
            w = canvas.width() * float(item.get("width", 20)) / 100.0
            h = canvas.height() * float(item.get("height", 12)) / 100.0
            rect = QRectF(a.x(), a.y(), w, h)
            painter.setPen(self._pen(color, width))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 30) if item.get("fill") else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)

        elif kind == "curve":
            path = self._curve_path(canvas, item)
            fill = QColor(color)
            fill.setAlpha(48)
            painter.setBrush(QBrush(fill) if item.get("fill") and item.get("closed")
                             else Qt.BrushStyle.NoBrush)
            painter.setPen(self._pen(color, width))
            painter.drawPath(path)
        elif kind in {"polygon", "polyline"}:
            points = [self._point(canvas, p["x"], p["y"]) for p in item.get("points", [])]
            if len(points) >= (3 if kind == "polygon" else 2):
                poly = QPolygonF(points)
                painter.setPen(self._pen(color, width))
                if kind == "polygon" and item.get("fill"):
                    painter.setBrush(QColor(color.red(), color.green(), color.blue(), 32))
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                if kind == "polygon":
                    painter.drawPolygon(poly)
                else:
                    painter.drawPolyline(poly)

        elif kind == "angle":
            c = a
            p1 = b
            p2 = self._point(canvas, item.get("x3", 50), item.get("y3", 25))
            self._glow_line(painter, c, p1, color, width)
            self._glow_line(painter, c, p2, color, width)
            v1 = math.atan2(p1.y() - c.y(), p1.x() - c.x())
            v2 = math.atan2(p2.y() - c.y(), p2.x() - c.x())
            delta = (v2 - v1 + math.pi) % (2 * math.pi) - math.pi
            radius = min(canvas.width(), canvas.height()) * float(item.get("radius", 8)) / 100.0
            path = QPainterPath()
            steps = 24
            for i in range(steps + 1):
                ang = v1 + delta * i / steps
                pt = QPointF(c.x() + math.cos(ang) * radius,
                             c.y() + math.sin(ang) * radius)
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            painter.setPen(self._pen(color, max(1, width - 0.2)))
            painter.drawPath(path)
            label = str(item.get("label") or item.get("text") or "")
            if label:
                mid = v1 + delta / 2
                pt = QPointF(c.x() + math.cos(mid) * radius * 1.45,
                             c.y() + math.sin(mid) * radius * 1.45)
                painter.setPen(color)
                painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
                painter.drawText(QRectF(pt.x()-46, pt.y()-14, 92, 24),
                                 Qt.AlignmentFlag.AlignCenter, label[:50])

        elif kind == "grid":
            n = int(item.get("divisions", 8))
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 80), 1))
            for i in range(n + 1):
                x = canvas.left() + canvas.width() * i / n
                y = canvas.top() + canvas.height() * i / n
                painter.drawLine(QPointF(x, canvas.top()), QPointF(x, canvas.bottom()))
                painter.drawLine(QPointF(canvas.left(), y), QPointF(canvas.right(), y))

        elif kind == "bar":
            w = canvas.width() * float(item.get("width", 36)) / 100.0
            h = max(9, canvas.height() * float(item.get("height", 3)) / 100.0)
            rect = QRectF(a.x(), a.y(), w, h)
            painter.setPen(QPen(QColor(125, 164, 185, 80), 1))
            painter.setBrush(QColor(120, 153, 173, 45))
            painter.drawRoundedRect(rect, h/2, h/2)
            active = QRectF(rect.left(), rect.top(), rect.width() * float(item.get("value", 65)) / 100.0, h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(active, h/2, h/2)
            label = str(item.get("label") or item.get("text") or "")
            if label:
                painter.setPen(color)
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
                painter.drawText(QRectF(a.x(), a.y()-24, w, 20),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label[:70])

        elif kind in {"text", "formula"}:
            text = str(item.get("text") or item.get("label") or "")
            if text:
                if kind == "formula":
                    w = canvas.width() * float(item.get("width", 38)) / 100.0
                    h = max(42, canvas.height() * float(item.get("height", 10)) / 100.0)
                    card = QRectF(a.x(), a.y(), w, h)
                    painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 145), 1.2))
                    painter.setBrush(QColor(color.red(), color.green(), color.blue(), 24))
                    painter.drawRoundedRect(card, 10, 10)
                    painter.setPen(QColor(239, 248, 255))
                    painter.setFont(QFont("Segoe UI", int(item.get("font_size", 18)), QFont.Weight.DemiBold))
                    painter.drawText(card.adjusted(10, 4, -10, -4),
                                     Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
                else:
                    painter.setPen(color)
                    painter.setFont(QFont("Segoe UI", int(item.get("font_size", 15)), QFont.Weight.DemiBold))
                    text_width = canvas.width() * float(item.get("width", 32)) / 100.0
                    text_height = max(28, canvas.height() * float(item.get("height", 8)) / 100.0)
                    painter.drawText(QRectF(a.x(), a.y(), text_width, text_height),
                                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                                     text)

        painter.restore()


    @staticmethod
    def _fmt(value: float) -> str:
        return f"{value:.1f}".replace(".", ",")

    def _triangle_geometry(self, canvas: QRectF):
        # Reserve the right 40% for the guided worked example.
        left_zone = canvas.width() * 0.56
        max_w = max(180.0, left_zone - 105.0)
        max_h = max(180.0, canvas.height() - 145.0)
        scale = min(max_w / max(self._triangle_b, 0.5),
                    max_h / max(self._triangle_a, 0.5))
        scale = max(18.0, scale)
        origin = QPointF(canvas.left() + 62, canvas.bottom() - 60)
        a_pt = origin
        b_pt = QPointF(origin.x(), origin.y() - self._triangle_a * scale)
        c_pt = QPointF(origin.x() + self._triangle_b * scale, origin.y())
        return a_pt, b_pt, c_pt, scale

    def _draw_handle(self, painter: QPainter, point: QPointF, label: str) -> None:
        painter.save()
        painter.setPen(QPen(QColor(4, 12, 22, 230), 4))
        painter.setBrush(QColor(89, 222, 255))
        painter.drawEllipse(point, 10, 10)
        painter.setPen(QPen(QColor(235, 251, 255), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point, 10, 10)
        painter.setPen(QColor(218, 243, 255))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(point.x() - 20, point.y() - 31, 40, 17),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _draw_interactive_right_triangle(self, painter: QPainter, canvas: QRectF) -> None:
        a_pt, b_pt, c_pt, scale = self._triangle_geometry(canvas)
        a, b = self._triangle_a, self._triangle_b
        c = math.hypot(a, b)
        painter.save()

        # Main right triangle.
        polygon = QPolygonF([a_pt, b_pt, c_pt])
        painter.setPen(self._pen(QColor(87, 224, 255), 3))
        painter.setBrush(QColor(35, 145, 190, 35))
        painter.drawPolygon(polygon)

        # Right-angle marker at the fixed corner.
        marker = 21
        right_square = QRectF(a_pt.x(), a_pt.y() - marker, marker, marker)
        painter.setPen(self._pen(QColor(255, 194, 104), 2))
        painter.setBrush(QColor(255, 194, 104, 25))
        painter.drawRect(right_square)
        painter.setPen(QColor(255, 207, 131))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(a_pt.x() + 23, a_pt.y() - 27, 48, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "90°")

        # Side labels follow the actual geometry.
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.setPen(_COLORS["green"])
        painter.drawText(QRectF(a_pt.x() - 60, (a_pt.y() + b_pt.y()) / 2 - 12, 115, 24),
                         Qt.AlignmentFlag.AlignCenter, f"Cateto a = {self._fmt(a)}")
        painter.drawText(QRectF((a_pt.x() + c_pt.x()) / 2 - 55, a_pt.y() + 10, 130, 24),
                         Qt.AlignmentFlag.AlignCenter, f"Cateto b = {self._fmt(b)}")
        mid_h = QPointF((b_pt.x() + c_pt.x()) / 2, (b_pt.y() + c_pt.y()) / 2)
        painter.setPen(_COLORS["pink"])
        painter.drawText(QRectF(mid_h.x() - 24, mid_h.y() - 35, 150, 24),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"Hipotenusa c = {self._fmt(c)}")

        self._draw_handle(painter, b_pt, "ARRASTE A")
        self._draw_handle(painter, c_pt, "ARRASTE B")

        # Right-side live values.
        panel_x = canvas.left() + canvas.width() * 0.63
        panel_w = canvas.right() - panel_x - 16
        painter.setPen(QColor(102, 224, 255))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(QRectF(panel_x, canvas.top() + 22, panel_w, 22),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "MEDIDAS EM TEMPO REAL")
        rows = [
            ("CATETO A", a, _COLORS["green"]),
            ("CATETO B", b, _COLORS["green"]),
            ("HIPOTENUSA C", c, _COLORS["pink"]),
        ]
        y = canvas.top() + 57
        for label, value, color in rows:
            card = QRectF(panel_x, y, panel_w, 58)
            painter.setPen(QPen(QColor(93, 157, 184, 70), 1))
            painter.setBrush(QColor(19, 42, 59, 175))
            painter.drawRoundedRect(card, 10, 10)
            painter.setPen(QColor(157, 187, 205))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(card.adjusted(12, 6, -10, -28),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(color)
            painter.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
            painter.drawText(card.adjusted(12, 26, -10, -4),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             self._fmt(value))
            y += 68

        painter.setPen(QColor(162, 195, 213))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(QRectF(panel_x, y + 2, panel_w, 22),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "TEOREMA DE PITÁGORAS")
        formula = f"{a:.1f}² + {b:.1f}² = {c:.1f}²".replace(".", ",")
        formula_card = QRectF(panel_x, y + 29, panel_w, 54)
        painter.setPen(QPen(QColor(87, 224, 255, 150), 1.2))
        painter.setBrush(QColor(37, 117, 153, 35))
        painter.drawRoundedRect(formula_card, 10, 10)
        painter.setPen(QColor(226, 249, 255))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        painter.drawText(formula_card.adjusted(7, 3, -7, -3),
                         Qt.AlignmentFlag.AlignCenter, formula)

        # The area bars animate in sequence when the user presses Play.
        y += 101
        painter.setPen(QColor(162, 195, 213))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(panel_x, y, panel_w, 18),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "ÁREAS DOS QUADRADOS")
        areas = [("a²", a * a, _COLORS["green"]),
                 ("b²", b * b, _COLORS["blue"]),
                 ("c²", c * c, _COLORS["pink"])]
        max_area = max(c * c, 1e-6)
        bar_y = y + 27
        for index, (label, area, color) in enumerate(areas):
            if self._animating:
                phase = self._animation_phase
                if phase < 0.32:
                    fill = min(1.0, phase / 0.32) if index == 0 else 0.0
                elif phase < 0.64:
                    fill = 1.0 if index == 0 else (
                        min(1.0, (phase - 0.32) / 0.32) if index == 1 else 0.0
                    )
                else:
                    fill = 1.0 if index < 2 else min(1.0, (phase - 0.64) / 0.36)
            else:
                fill = 1.0
            painter.setPen(QColor(141, 170, 189, 75))
            painter.setBrush(QColor(37, 59, 75, 180))
            track = QRectF(panel_x, bar_y, panel_w, 25)
            painter.drawRoundedRect(track, 7, 7)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 175))
            active = QRectF(panel_x, bar_y, panel_w * (area / max_area) * fill, 25)
            painter.drawRoundedRect(active, 7, 7)
            painter.setPen(QColor(241, 248, 255))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(track.adjusted(8, 1, -8, -1),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{label}  =  {self._fmt(area)}")
            bar_y += 33

        if self._animating:
            stage = ("Preenchendo o quadrado de a²" if self._animation_phase < 0.32
                     else "Somando a área de b²" if self._animation_phase < 0.64
                     else "Resultado: área de c²")
        else:
            stage = "Arraste os pontos A e B para mudar o triângulo"
        painter.setPen(QColor(139, 180, 199))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(panel_x, min(bar_y + 2, canvas.bottom() - 22),
                                panel_w, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         stage[:80])
        painter.restore()

    def _draw_interaction_controls(self, painter: QPainter, rect: QRectF) -> None:
        # Keep the controls on their own row, above the lesson footer.
        y = rect.height() - 82
        self._play_rect = QRectF(24, y, 210, 27)
        self._reset_rect = QRectF(244, y, 142, 27)
        painter.save()
        painter.setPen(QColor(227, 249, 255))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        label = "Ⅱ  PAUSAR DEMONSTRAÇÃO" if self._animating else "▶  ANIMAR ÁREAS"
        painter.drawText(self._play_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QColor(206, 222, 235))
        painter.drawText(self._reset_rect, Qt.AlignmentFlag.AlignCenter, "↺  REINICIAR")
        painter.restore()

    def _collect_generic_handles(self, index: int, item: dict, canvas: QRectF) -> None:
        kind = item.get("type")
        if kind in {"polygon", "polyline", "curve"}:
            for point_index, point in enumerate(item.get("points", [])):
                self._generic_handles.append((
                    "polygon", index, point_index,
                    self._point(canvas, point.get("x", 50), point.get("y", 50)),
                ))
        elif kind in {"line", "arrow", "dimension"}:
            self._generic_handles.extend([
                ("line", index, 0, self._point(canvas, item.get("x", 50), item.get("y", 50))),
                ("line", index, 1, self._point(canvas, item.get("x2", 75), item.get("y2", 50))),
            ])
        elif kind == "circle":
            self._generic_handles.append((
                "circle", index, 0, self._point(canvas, item.get("x", 50), item.get("y", 50))
            ))
        elif kind in {"text", "formula", "card", "list", "table", "timeline",
                      "graph", "mindmap", "model3d", "quiz", "photo", "map", "molecule"}:
            origin = self._point(canvas, item.get("x", 50), item.get("y", 50))
            corner = QPointF(
                origin.x() + canvas.width() * float(item.get("width", 20)) / 100,
                origin.y() + canvas.height() * float(item.get("height", 12)) / 100,
            )
            self._generic_handles.append(("resize", index, 0, corner))

    def _draw_generic_handles(self, painter: QPainter) -> None:
        for _, _, _, point in self._generic_handles:
            if self._lesson_timeline and (self._hover_position is None or
                    math.hypot(point.x() - self._hover_position.x(),
                               point.y() - self._hover_position.y()) > 28):
                continue
            painter.setPen(QPen(QColor(4, 12, 22, 210), 3))
            painter.setBrush(QColor(87, 224, 255, 210))
            painter.drawEllipse(point, 6, 6)
            painter.setPen(QPen(QColor(220, 248, 255), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(point, 6, 6)

    def _tick_models(self) -> None:
        self._model_phase += 0.016
        self.update()

    def _tick_animation(self) -> None:
        self._animation_phase = (self._animation_phase + 0.006) % 1.0
        self.update()

    def _element_hit(self, item: dict, pos: QPointF, canvas: QRectF) -> bool:
        kind = item.get("type")
        if kind == "curve":
            path = self._curve_path(canvas, item)
            stroke = QPainterPathStroker()
            stroke.setWidth(max(16, float(item.get("stroke_width", 2)) + 10))
            return (bool(item.get("closed") and item.get("fill")) and path.contains(pos)
                    or stroke.createStroke(path).contains(pos))
        if kind in {"text", "formula", "card", "list", "table", "timeline", "graph", "mindmap", "model3d", "quiz", "photo", "map", "molecule"}:
            anchor = self._point(canvas, item.get("x", 50), item.get("y", 50))
            rect = QRectF(anchor.x(), anchor.y(), canvas.width() * float(item.get("width", 20)) / 100,
                          max(30, canvas.height() * float(item.get("height", 12)) / 100))
            return rect.adjusted(-8, -8, 8, 8).contains(pos)
        if kind in {"rect", "bar"}:
            a = self._point(canvas, item.get("x", 50), item.get("y", 50))
            rect = QRectF(a.x(), a.y(), canvas.width()*float(item.get("width",20))/100,
                          canvas.height()*float(item.get("height",12))/100)
            return rect.adjusted(-8,-8,8,8).contains(pos)
        if kind == "circle":
            c = self._point(canvas, item.get("x",50), item.get("y",50))
            radius = min(canvas.width(),canvas.height())*float(item.get("radius",8))/100
            return math.hypot(pos.x()-c.x(),pos.y()-c.y()) <= radius+10
        if kind in {"line","arrow","dimension"}:
            a=self._point(canvas,item.get("x",50),item.get("y",50)); b=self._point(canvas,item.get("x2",75),item.get("y2",50))
            vx,vy=b.x()-a.x(),b.y()-a.y(); denom=vx*vx+vy*vy or 1
            t=max(0,min(1,((pos.x()-a.x())*vx+(pos.y()-a.y())*vy)/denom))
            return math.hypot(pos.x()-(a.x()+t*vx),pos.y()-(a.y()+t*vy)) <= 14
        return False

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if self._close_rect.contains(pos):
            self.hide()
            event.accept()
            return
        for element_id, option_index, option_rect in self._quiz_rects:
            if option_rect.contains(pos):
                groups = (self._payload.get("elements", []),
                          self._payload.get("_annotation_elements", []))
                for group in groups:
                    for item in group:
                        if item.get("id") == element_id:
                            previous = item.get("selected")
                            if previous == option_index:
                                event.accept()
                                return
                            item["selected"] = option_index
                            options = list(item.get("options") or [])
                            choice = str(options[option_index]) if 0 <= option_index < len(options) else ""
                            answer = str(item.get("answer") or "").strip()
                            if answer:
                                letter = answer.upper().strip(" .)")
                                if len(letter) == 1 and letter in "ABCD":
                                    correct = (ord(letter) - ord("A")) == option_index
                                else:
                                    correct = choice.strip().casefold() == answer.casefold()
                            else:
                                correct = None
                            attempts = int(item.get("_answer_attempts", 0)) + 1
                            item["_answer_attempts"] = attempts
                            question = str(
                                item.get("title") or item.get("heading")
                                or item.get("text") or "Questão visual"
                            )[:180]
                            self.quiz_answered.emit({
                                "element_id": str(element_id),
                                "attempt": attempts,
                                "question": question,
                                "choice": choice[:120],
                                "answer": answer[:120],
                                "correct": correct,
                                "explanation": str(item.get("explanation") or "")[:240],
                            })
                            self.update()
                            event.accept()
                            return
        if self._interactive_kind == "right_triangle":
            if getattr(self, "_play_rect", QRectF()).contains(pos):
                self._animating = not self._animating
                if self._animating:
                    self._anim_timer.start()
                else:
                    self._anim_timer.stop()
                self.update()
                event.accept()
                return
            if getattr(self, "_reset_rect", QRectF()).contains(pos):
                self._triangle_a = self._initial_a
                self._triangle_b = self._initial_b
                self._animation_phase = 0.0
                self._animating = False
                self._anim_timer.stop()
                self.update()
                event.accept()
                return
            a_pt, b_pt, c_pt, _ = self._triangle_geometry(self._canvas_rect)
            if math.hypot(pos.x() - b_pt.x(), pos.y() - b_pt.y()) <= 24:
                self._drag_target = "triangle_a"
                self.grabMouse()
                event.accept()
                return
            if math.hypot(pos.x() - c_pt.x(), pos.y() - c_pt.y()) <= 24:
                self._drag_target = "triangle_b"
                self.grabMouse()
                event.accept()
                return
        else:
            nearest = None
            distance = 22.0
            for handle in self._generic_handles:
                d = math.hypot(pos.x() - handle[3].x(), pos.y() - handle[3].y())
                if d < distance:
                    nearest, distance = handle, d
            if nearest is not None:
                self._drag_target = nearest[:3]
                self.grabMouse()
                event.accept()
                return
            # 3D models orbit in place when dragged; their resize handle remains above this hit region.
            elements = self._payload.get("elements", [])
            if self._lesson_timeline:
                visible_count = max(0, self._reveal_index + (self._reveal_progress >= 1.0))
                elements = elements[:visible_count]
            for index in range(len(elements) - 1, -1, -1):
                item = elements[index]
                if item.get("type") == "model3d" and self._element_hit(item, pos, self._canvas_rect):
                    element_id = str(item.get("id") or f"element_{index+1}")
                    self._drag_target = ("model_rotate", index, 0)
                    self._model_drag_origin = (pos.x(), pos.y())
                    self._model_drag_initial = self._model_view_rotation.get(element_id, (0.0, 0.0))
                    self.grabMouse()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
            # Whole-object drag: resolve the topmost element whose visible
            # geometry contains the pointer. Point handles remain higher priority.
            for index in range(len(elements) - 1, -1, -1):
                if self._element_hit(elements[index], pos, self._canvas_rect):
                    self._drag_target = ("whole", index, 0)
                    self._drag_origin = (pos.x(), pos.y())
                    self._drag_original = copy.deepcopy(elements[index])
                    self.grabMouse()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        self._hover_position = pos
        if self._lesson_timeline:
            self.update()
        if self._drag_target == "triangle_a":
            a_pt, _, _, scale = self._triangle_geometry(self._canvas_rect)
            self._triangle_a = max(0.5, min(10.0, (a_pt.y() - pos.y()) / scale))
            self.update()
            event.accept()
            return
        if self._drag_target == "triangle_b":
            a_pt, _, _, scale = self._triangle_geometry(self._canvas_rect)
            self._triangle_b = max(0.5, min(10.0, (pos.x() - a_pt.x()) / scale))
            self.update()
            event.accept()
            return
        if self._drag_target and self._drag_target[0] == "model_rotate":
            _, index, _ = self._drag_target
            elements = self._payload.get("elements", [])
            if 0 <= index < len(elements):
                item = elements[index]
                element_id = str(item.get("id") or f"element_{index+1}")
                origin = self._model_drag_origin or (pos.x(), pos.y())
                dx, dy = pos.x() - origin[0], pos.y() - origin[1]
                yaw0, pitch0 = self._model_drag_initial
                self._model_view_rotation[element_id] = (
                    yaw0 + dx * 0.012,
                    max(-1.35, min(1.35, pitch0 + dy * 0.010)),
                )
                self.update()
            event.accept()
            return
        if self._drag_target:
            kind, index, point_index = self._drag_target
            canvas = self._canvas_rect
            x = max(0.0, min(100.0, (pos.x() - canvas.left()) / max(1.0, canvas.width()) * 100.0))
            y = max(0.0, min(100.0, (pos.y() - canvas.top()) / max(1.0, canvas.height()) * 100.0))
            item = self._payload.get("elements", [])[index]
            if kind == "whole":
                original = self._drag_original
                dxp = (pos.x() - self._drag_origin[0]) / max(1.0, canvas.width()) * 100.0
                dyp = (pos.y() - self._drag_origin[1]) / max(1.0, canvas.height()) * 100.0
                item.clear()
                item.update(copy.deepcopy(original))
                for key in ("x", "x2", "x3"):
                    if key in item: item[key] = max(0.0, min(100.0, float(item[key]) + dxp))
                for key in ("y", "y2", "y3"):
                    if key in item: item[key] = max(0.0, min(100.0, float(item[key]) + dyp))
                for point in item.get("points", []):
                    point["x"] = max(0.0, min(100.0, float(point.get("x",50)) + dxp))
                    point["y"] = max(0.0, min(100.0, float(point.get("y",50)) + dyp))
            elif kind == "polygon":
                item["points"][point_index]["x"] = x
                item["points"][point_index]["y"] = y
            elif kind == "line":
                key_x, key_y = (("x", "y") if point_index == 0 else ("x2", "y2"))
                item[key_x], item[key_y] = x, y
            elif kind == "circle":
                item["x"], item["y"] = x, y
            elif kind == "resize":
                origin = self._point(canvas, item.get("x", 50), item.get("y", 50))
                item["width"] = max(8.0, min(100.0,
                    (pos.x() - origin.x()) / max(1.0, canvas.width()) * 100.0))
                item["height"] = max(8.0, min(100.0,
                    (pos.y() - origin.y()) / max(1.0, canvas.height()) * 100.0))
                self._generic_handles = []
                self._collect_generic_handles(index, item, canvas)
            self.update()
            event.accept()
            return
        if self._interactive_kind == "right_triangle":
            a_pt, b_pt, c_pt, _ = self._triangle_geometry(self._canvas_rect)
            on_handle = (
                math.hypot(pos.x() - b_pt.x(), pos.y() - b_pt.y()) <= 24
                or math.hypot(pos.x() - c_pt.x(), pos.y() - c_pt.y()) <= 24
            )
            self.setCursor(Qt.CursorShape.SizeAllCursor if on_handle else Qt.CursorShape.ArrowCursor)
        else:
            on_handle = any(
                math.hypot(pos.x() - h[3].x(), pos.y() - h[3].y()) <= 16
                for h in self._generic_handles
            )
            on_model = any(
                item.get("type") == "model3d" and self._element_hit(item, pos, self._canvas_rect)
                for item in self._payload.get("elements", [])
            )
            self.setCursor(
                Qt.CursorShape.SizeAllCursor if on_handle else
                Qt.CursorShape.OpenHandCursor if on_model else Qt.CursorShape.ArrowCursor
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_position = None
        if self._lesson_timeline:
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_target:
            self._drag_target = None
            self.releaseMouse()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)
