"""ui.py — the entry point to the HUD.

The desktop interface is the single frontend in visual_novo/. This file keeps
JarvisUI — the object main.py builds and every plugin receives as `player` —
and re-exports the historical names expected by the app runtime.
"""
from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

# Before any Qt import: Qt's video backend prints signed stream URLs otherwise.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")

from PyQt6.QtWidgets import QApplication

from gui import hud as _gui_hud
from gui import metrics as _gui_metrics
from gui import overlays as _gui_overlays
from gui import providers_panel as _gui_providers_panel
from gui import theme as _gui_theme
from gui import widgets as _gui_widgets
from gui import window as _gui_window
from gui.window import MainWindow

# Compatibility: every top-level name the old single-file ui.py had.
for _mod in (_gui_theme, _gui_metrics, _gui_hud, _gui_widgets, _gui_overlays,
             _gui_providers_panel, _gui_window):
    for _name, _value in vars(_mod).items():
        if not _name.startswith("__") and _name not in globals():
            globals()[_name] = _value
del _mod, _name, _value


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


def _auto_ui_scale() -> float:
    """A scale for the interface from the primary screen's usable height.

    The HUD's sizes were laid out on a 1080-pixel-tall screen. Windows only
    enlarges them when the user has raised display scaling, so on a 1440p
    monitor at 100% — and even at 125% — the panels came out small enough to be
    hard to read. Measured against 900 logical pixels rather than 1080 because
    the designed sizes were on the small side even there.

    Windows only, through calls that are not DPI-virtualised — so nothing about
    the process's DPI awareness is touched before Qt sets it. Elsewhere the
    system's own scaling is trusted and this returns 1."""
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        try:
            physical_h = gdi32.GetDeviceCaps(hdc, 117)      # DESKTOPVERTRES
        finally:
            user32.ReleaseDC(0, hdc)
        percent = ctypes.windll.shcore.GetScaleFactorForDevice(0) or 100
        logical_h = physical_h * 100.0 / percent
    except Exception:
        return 1.0
    return max(1.0, min(2.0, round(logical_h / 900.0 * 20) / 20))


def _apply_ui_scale() -> None:
    """Set Qt's global scale factor. Must run before QApplication exists.

    `ui_scale` in config/api_keys.json overrides the automatic choice (0.5 to
    3); QT_SCALE_FACTOR set by the user is never overridden."""
    if QApplication.instance() is not None or os.environ.get("QT_SCALE_FACTOR"):
        return              # too late, or the user set it themselves
    try:
        from memory.config_manager import get_ui_scale
        scale = get_ui_scale() or _auto_ui_scale()
    except Exception:
        scale = _auto_ui_scale()
    if abs(scale - 1.0) > 0.01:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        _apply_ui_scale()
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._attach_holo_skin()
        self._visual_voice_cps = 13.0  # conservative until measured from Gemini PCM
        self.root = _RootShim(self._app)
        self._win.show()

    def _attach_holo_skin(self) -> None:
        """Load the only supported JARVIS desktop visual."""
        visual_dir = str(Path(__file__).resolve().parent / "visual_novo")
        if not os.path.isdir(visual_dir):
            raise RuntimeError("O visual principal do JARVIS não foi encontrado.")
        if visual_dir not in sys.path:
            sys.path.insert(0, visual_dir)
        try:
            import live_skin
            skin = live_skin.attach(self._win)
        except Exception as exc:
            raise RuntimeError("Não foi possível iniciar o visual principal do JARVIS.") from exc
        if skin is None:
            raise RuntimeError("O visual principal do JARVIS não pôde ser carregado.")
        self._win._holo_skin = skin

    @property
    def on_close(self):
        return getattr(self._win, "on_close", None)

    @on_close.setter
    def on_close(self, callback):
        self._win.on_close = callback

    @property
    def on_hibernate(self):
        return getattr(self._win, "on_hibernate", None)

    @on_hibernate.setter
    def on_hibernate(self, callback):
        self._win.on_hibernate = callback

    @property
    def get_active_tasks(self):
        return getattr(self._win, "get_active_tasks", None)

    @get_active_tasks.setter
    def get_active_tasks(self, callback):
        self._win.get_active_tasks = callback

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if bool(v) != self._win._muted:
            # The wake-word callback runs on its own inference thread. Route
            # mute changes through Qt rather than touching widgets off-thread.
            self._win._mute_sig.emit(bool(v))

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    def show_confirm(self, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(str(title)[:120], str(detail)[:300])

    def hide_confirm(self) -> None:
        """Thread-safe: take the gate down."""
        self._win._confirm_hide_sig.emit()

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)."""
        try:
            self._win.hud.glance(dx, dy, hold)
        except Exception:
            pass

    @property
    def ptt_hold(self):
        return self._win.ptt_hold

    @ptt_hold.setter
    def ptt_hold(self, cb):
        self._win.ptt_hold = cb

    @property
    def on_push_to_talk(self):
        return self._win.on_push_to_talk

    @on_push_to_talk.setter
    def on_push_to_talk(self, cb):
        self._win.on_push_to_talk = cb

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe: post a schedule of (level, openness, width) mouth frames
        for JARVIS's own speech. `at` is the wall-clock time the batch begins to
        sound, not the time of the call. See HudCanvas.push_visemes()."""
        try:
            self._win.hud.push_visemes(frames, hop, at)
        except Exception:
            pass

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def hide_window(self) -> None:
        """Thread-safe: hide the HUD but keep JARVIS and its tray icon alive."""
        self._win._hide_sig.emit()

    def hibernate_for_voice(self) -> None:
        """Thread-safe request for full low-footprint wake-word hibernation."""
        self._win._hibernate_sig.emit()

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display complete search/news/briefing text below the HUD."""
        self._win._content_sig.emit(str(title or "")[:48], str(text or ""))

    def show_visual_board(self, payload: dict, timeout: float = 4.0, operation: str = "append") -> bool:
        """Thread-safe: wait for Qt to confirm that the visual board is really visible."""
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        data = dict(payload or {})
        data["_board_operation"] = operation
        self._win._visual_show_sig.emit(data, ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The desktop UI did not confirm the visual board within the timeout.")
        if not ack["ok"]:
            raise RuntimeError(ack.get("error") or "The visual board could not be displayed.")
        return True

    def set_visual_lesson_status(self, caption: str, index: int,
                                 total: int, waiting: bool = False,
                                 draw_duration: float | None = None,
                                 timeout: float = 4.0) -> None:
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        payload = {
            "caption": str(caption or ""),
            "index": int(index or 0),
            "total": int(total or 0),
            "waiting": bool(waiting),
            "draw_duration": (
                max(0.25, min(45.0, float(draw_duration)))
                if draw_duration is not None else None
            ),
        }
        self._win._visual_lesson_sig.emit(payload, ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The visual lesson caption did not update in time.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        if not ack.get("ok"):
            raise RuntimeError("The visual lesson caption was not acknowledged.")

    def get_visual_voice_cps(self) -> float:
        """Measured speaking pace in characters/second, smoothed like JARVIS."""
        try:
            return max(8.0, min(30.0, float(self._visual_voice_cps)))
        except (TypeError, ValueError):
            return 13.0

    def update_visual_voice_cps(self, measured_cps: float) -> float:
        """Learn Gemini's speaking rate with the same 60/40 smoothing as JARVIS."""
        try:
            measured = max(8.0, min(30.0, float(measured_cps)))
        except (TypeError, ValueError):
            return self.get_visual_voice_cps()
        previous = self.get_visual_voice_cps()
        self._visual_voice_cps = max(8.0, min(30.0, previous * 0.6 + measured * 0.4))
        return self._visual_voice_cps

    def set_visual_live_caption(self, caption: str) -> None:
        """Thread-safe update from Gemini Live's actual output transcription."""
        try:
            self._win._visual_caption_sig.emit(str(caption or ""))
        except Exception:
            pass

    def set_visual_timed_caption(self, caption: str, audible_at: float) -> None:
        """Tie a Live transcript snapshot to when its queued PCM reaches the speaker."""
        try:
            self._win._visual_timed_caption_sig.emit(
                str(caption or ""), float(audible_at)
            )
        except Exception:
            pass

    def push_visual_audio_window(self, at: float, duration: float) -> None:
        """Schedule the visual lesson clock against a real speaker PCM batch."""
        try:
            self._win._visual_audio_sig.emit({
                "start": float(at),
                "duration": float(duration),
            })
        except Exception:
            pass

    def push_visual_stream_caption(self, caption: str, at: float, clock) -> None:
        self._win._visual_audio_sig.emit({
            "caption": str(caption or ""), "at": float(at), "clock": clock,
        })

    def push_visual_stream_audio(self, start: float, duration: float, clock) -> None:
        self._win._visual_audio_sig.emit({
            "sample_start": float(start), "duration": float(duration), "clock": clock,
        })

    def clear_visual_audio_clock(self) -> None:
        try:
            self._win._visual_audio_sig.emit({"clear": True})
        except Exception:
            pass

    # ── marker-synchronised narration (core/pcm_clock.py) ───────────────────
    def push_lesson_mark(self, kind: str, index: int, at: float, clock=None) -> None:
        """A beat boundary measured in the speech stream's own timeline."""
        try:
            self._win._visual_audio_sig.emit({
                "mark": {"kind": str(kind), "index": int(index), "at": float(at)},
                "clock": clock,
            })
        except Exception:
            pass

    def cancel_marker_lesson(self) -> None:
        try:
            self._win._visual_audio_sig.emit({"cancel": True})
        except Exception:
            pass

    def start_marker_lesson(self, captions: list, title: str = "") -> bool:
        """Hand a lesson script to the Live session, which will speak it beat by
        beat and mark each beat's exact place in the PCM stream. Returns False
        when the narration engine cannot do that (the caller then falls back)."""
        handler = getattr(self, "lesson_script_handler", None)
        if not callable(handler):
            return False
        try:
            return bool(handler([str(c) for c in captions], str(title or "")))
        except Exception:
            return False

    def set_visual_input_passthrough(self, enabled: bool,
                                     timeout: float = 4.0) -> None:
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        self._win._visual_passthrough_sig.emit(bool(enabled), ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The visual board input mode did not change in time.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        if not ack.get("ok"):
            raise RuntimeError("The visual board input mode was not acknowledged.")

    def visual_animation_done(self, timeout: float = 1.0) -> bool:
        ack = {"event": threading.Event(), "done": False}
        self._win._visual_state_sig.emit(ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 3.0))):
            raise TimeoutError("The visual animation state was not returned.")
        return bool(ack.get("done", False))

    def show_guidance_target(self, rect, label: str, step: int = 1,
                             timeout: float = 4.0) -> None:
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        self._win._guidance_show_sig.emit(tuple(rect), str(label), int(step), ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The guided screen target did not render in time.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        if not ack.get("ok"):
            raise RuntimeError("The guided screen target was not acknowledged.")

    def clear_guidance_target(self, timeout: float = 4.0) -> None:
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        self._win._guidance_clear_sig.emit(ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The guided screen target did not clear in time.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])

    def show_desktop_ink(self, points, snapped: bool = False) -> None:
        try:
            self._win._desktop_ink_sig.emit(list(points or []), bool(snapped))
        except Exception:
            pass

    def clear_desktop_ink(self, delay_ms: int = 0) -> None:
        try:
            self._win._desktop_ink_clear_sig.emit(int(delay_ms))
        except Exception:
            pass

    def show_screen_marks(self, payload: dict, timeout: float = 4.0,
                          operation: str = "append") -> None:
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        data = dict(payload or {})
        data["_operation"] = operation
        self._win._screen_marks_sig.emit(data, ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("Screen marks did not render in time.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        if not ack.get("ok"):
            raise RuntimeError("Screen marks were not acknowledged.")

    def inspect_screen_marks(self, timeout: float = 4.0) -> dict:
        ack = {"event": threading.Event(), "result": {}, "error": ""}
        self._win._screen_marks_inspect_sig.emit(ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("Screen marks inspection timed out.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        return dict(ack.get("result") or {})

    def edit_screen_marks(self, operation: str, element_id: str = "",
                          patch: dict | None = None, dx: float = 0.0,
                          dy: float = 0.0, timeout: float = 4.0) -> str:
        ack = {"event": threading.Event(), "result": "", "error": ""}
        self._win._screen_marks_edit_sig.emit(
            str(operation), str(element_id), dict(patch or {}),
            float(dx), float(dy), ack
        )
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("Screen-mark edit timed out.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        return str(ack.get("result") or "edited")

    def clear_screen_marks(self, timeout: float = 4.0) -> None:
        ack = {"event": threading.Event(), "ok": False, "error": ""}
        self._win._screen_marks_clear_sig.emit(ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("Screen marks did not clear in time.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])

    def select_screen_area(self, timeout: float = 90.0) -> dict:
        """Thread-safe frozen-screen region picker; returns PNG and its screen viewport."""
        ack = {"event": threading.Event(), "selection": None, "error": ""}
        self._win._screen_area_sig.emit(ack)
        if not ack["event"].wait(max(1.0, min(float(timeout), 120.0))):
            raise TimeoutError("The screen-area selection did not finish.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        selection = ack.get("selection")
        if not isinstance(selection, dict) or not selection.get("image") or not selection.get("viewport"):
            raise RuntimeError("No screen area was selected.")
        selection = dict(selection)
        selection["image"] = bytes(selection["image"])
        return selection

    def inspect_visual_board(self, timeout: float = 4.0) -> dict:
        ack = {"event": threading.Event(), "result": {}, "error": ""}
        self._win._visual_inspect_sig.emit(ack)
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The visual board did not answer inspection.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        return dict(ack.get("result") or {})

    def edit_visual_board(self, operation: str, element_id: str = "", patch: dict | None = None,
                          dx: float = 0.0, dy: float = 0.0, timeout: float = 4.0) -> str:
        """Thread-safe, acknowledged in-place edit of one visual scene element."""
        ack = {"event": threading.Event(), "result": "", "error": ""}
        self._win._visual_edit_sig.emit(
            str(operation), str(element_id), dict(patch or {}), float(dx), float(dy), ack
        )
        if not ack["event"].wait(max(0.1, min(float(timeout), 8.0))):
            raise TimeoutError("The visual board did not acknowledge the edit.")
        if ack.get("error"):
            raise RuntimeError(ack["error"])
        return str(ack.get("result") or "edited")
    
    def clear_visual_board(self) -> None:
        """Thread-safe: remove the screen-side teaching overlay."""
        self._win._visual_clear_sig.emit()

    def show_code_job(self, job: dict) -> None:
        """Thread-safe: draw the coding agent's live progress in the panel."""
        self._win._codejob_sig.emit(dict(job))

    def show_quiz(self, topic: str, questions, grade=None) -> None:
        """Thread-safe: put an interactive quiz on the board.

        `grade(question, given)` decides each answer — the plugin supplies it so
        the marking rules live with the questions rather than being duplicated
        here. Returning None from it means "JARVIS should judge this one", which
        is how open answers and near-miss gap-fills are handled.

        Returns immediately: the user answers at their own pace and the finished
        result is delivered back through on_text_command.
        """
        self._win._quiz_sig.emit(str(topic or ""), list(questions or []), grade)

    def hide_quiz(self) -> None:
        """Thread-safe: clear any quiz currently on the board."""
        self._win._quiz_hide_sig.emit()

    def show_review(self, title: str, summary: str, findings, unclear=None) -> None:
        """Thread-safe: lay a document review into the panel below the HUD.

        `findings` is a list of {heading, detail, severity, quote, suggestion};
        severity is one of 'serious' / 'caution' / 'note' and decides colour and
        order here, so the caller supplies no styling of its own.
        """
        self._win._review_sig.emit(str(title or ""), str(summary or ""),
                                   list(findings or []), list(unclear or []))

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def show_video(self, source: str, title: str = "", muted: bool = True,
                   audio_source: str = "") -> None:
        """Thread-safe: play a video where the avatar normally is.

        `source` is a local path or a direct media URL. `audio_source` is for
        the case where the sound arrives as its own stream — YouTube serves no
        combined format any more — and when it is given the two are played
        together and kept in step.

        Muted by default, and that is a decision rather than a default: a
        soundtrack talking over JARVIS is the one way this could make the
        assistant worse. The user turns sound on from the header button or by
        asking, and closes it the same two ways.
        """
        self._win._video_open_sig.emit(str(source or ""), str(title or ""),
                                       bool(muted), str(audio_source or ""))

    def show_image(self, path: str, title: str = "") -> None:
        """Thread-safe: put a still picture where the avatar normally is.

        The same surface the video uses, so a picture, a video and the live
        camera can never be on screen at once — and `stop_video()` closes a
        picture too, which is why "close it" needed nothing new.

        `generate_image` has been calling this method by name since it was
        written, against the possibility that it would one day exist. It does
        now, so a picture JARVIS draws appears on the HUD instead of only in a
        folder.
        """
        self._win._image_open_sig.emit(str(path or ""), str(title or ""))

    def stop_video(self) -> None:
        """Thread-safe: close the video and give the HUD back to the avatar."""
        self._win._video_close_sig.emit()

    def set_video_muted(self, muted: bool) -> None:
        """Thread-safe: silence or unsilence whatever is playing."""
        self._win._video_mute_sig.emit(bool(muted))

    def video_is_playing(self) -> bool:
        return bool(self._win.video_is_playing())

    def seek_video(self, seconds: float, relative: bool = True) -> None:
        """Thread-safe: move the video on the display — by `seconds` (negative is
        back) when relative, or to `seconds` from the start."""
        self._win._video_seek_sig.emit(float(seconds), bool(relative))

    def pause_video(self, paused: bool = True) -> None:
        """Thread-safe: pause or resume the video on the display."""
        self._win._video_pause_sig.emit(bool(paused))

    def video_state(self) -> dict:
        """kind ('video' | 'image' | ''), position, duration (seconds), paused."""
        try:
            return dict(self._win.video_state())
        except Exception:
            return {}

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")