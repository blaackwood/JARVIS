"""Opt-in focus sessions with lightweight foreground-window checks.

No screenshots, keystrokes, page contents, or network calls are collected.
Only the foreground app name and window title are inspected locally.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

CHECK_SECONDS = 20.0
DRIFT_CHECKS = 2
NUDGE_GAP_SECONDS = 180.0
MIN_MINUTES = 5
MAX_MINUTES = 240

DEFAULT_DISTRACTIONS = (
    "youtube.com", "YouTube", "reddit.com", "x.com", "twitter.com",
    "tiktok.com", "instagram.com", "facebook.com", "netflix.com", "Netflix",
    "twitch.tv", "Twitch", "Reddit", "Steam", "Epic Games", "Roblox", "Minecraft",
    "League of Legends", "Fortnite", "Valorant", "Counter-Strike",
    "Battle.net", "disneyplus.com", "primevideo.com", "9gag.com",
)


def parse_distractions(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_DISTRACTIONS
    raw = value if isinstance(value, (list, tuple)) else re.split(r"[,;\n]", str(value))
    cleaned = []
    seen = set()
    for item in raw:
        entry = re.sub(r"^www\.", "", re.sub(r"^https?://", "", str(item).strip(), flags=re.I), flags=re.I)
        entry = entry.split("/", 1)[0].strip()
        key = entry.casefold()
        if 2 <= len(entry) <= 60 and key not in seen:
            seen.add(key)
            cleaned.append(entry)
    return tuple(cleaned[:60])


def distraction(front: dict | None, entries=DEFAULT_DISTRACTIONS) -> str | None:
    if not isinstance(front, dict):
        return None
    app = str(front.get("app") or "").strip()
    title = str(front.get("title") or "")
    url = str(front.get("url") or "")
    if not app or app.casefold() in {"jarvis", "j.a.r.v.i.s"}:
        return None
    host = ""
    if url:
        match = re.search(r"^(?:https?://)?([^/:?#]+)", url, flags=re.I)
        host = (match.group(1).lower().removeprefix("www.") if match else "")
    for entry in entries:
        e = str(entry).strip()
        low = e.casefold()
        if re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", low):
            if host and (host == low or host.endswith("." + low)):
                return e
            if not host and re.search(r"(?<![a-z0-9])" + re.escape(e) + r"(?![a-z0-9])", title, re.I):
                return e
        elif low in app.casefold():
            return e
        elif not host and re.search(r"(?<!\w)" + re.escape(e) + r"(?!\w)", title, re.I):
            return e
    return None


@dataclass
class FocusBlock:
    started_at: float
    until: float
    minutes: int
    task: str = ""
    streak: int = 0
    drifts: int = 0
    nudged_at: float = 0.0
    current_distraction: str | None = None


def start_block(minutes: int | float | None, task: str = "", now: float | None = None) -> FocusBlock:
    now = time.time() if now is None else float(now)
    try:
        requested = float(minutes or 25)
    except (TypeError, ValueError):
        requested = 25
    length = max(MIN_MINUTES, min(MAX_MINUTES, round(requested)))
    return FocusBlock(now, now + length * 60, length, str(task or "").strip()[:120])


def check_block(block: FocusBlock, front: dict | None, entries=DEFAULT_DISTRACTIONS,
                now: float | None = None) -> dict:
    now = time.time() if now is None else float(now)
    if now >= block.until:
        return {"end": True}
    hit = distraction(front, entries)
    if not hit:
        block.streak = 0
        block.current_distraction = None
        return {}
    if block.current_distraction != hit:
        block.drifts += 1
    block.current_distraction = hit
    block.streak += 1
    if block.streak >= DRIFT_CHECKS and now - block.nudged_at >= NUDGE_GAP_SECONDS:
        block.nudged_at = now
        return {"nudge": hit}
    return {}


class FocusManager:
    """One in-memory focus block. Observer/notify are injected for safe testing."""

    def __init__(self, observe: Callable[[], dict | None], notify: Callable[[str], None],
                 log: Callable[[str], None] = lambda _message: None,
                 clock: Callable[[], float] = time.time,
                 interval: float = CHECK_SECONDS):
        self._observe = observe
        self._notify = notify
        self._log = log
        self._clock = clock
        self._interval = max(1.0, float(interval))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._block: FocusBlock | None = None

    def status(self) -> dict | None:
        with self._lock:
            b = self._block
            if b is None:
                return None
            return {"minutes": b.minutes, "task": b.task, "until": b.until,
                    "remaining_seconds": max(0, round(b.until - self._clock())),
                    "drifts": b.drifts}

    def start(self, minutes: int | float | None = 25, task: str = "") -> str:
        block = start_block(minutes, task, self._clock())
        with self._lock:
            self._stop.set()
            old = self._thread
            self._block = block
            self._stop = threading.Event()
            stop_event = self._stop
            self._thread = threading.Thread(
                target=self._run, args=(block, stop_event),
                name="jarvis-focus", daemon=True)
            self._thread.start()
        if old and old.is_alive():
            old.join(timeout=0.2)
        self._log(f"Focus started: {block.minutes} min" + (f" — {block.task}" if block.task else ""))
        return f"Focus session started for {block.minutes} minutes" + (f" on {block.task}" if block.task else "") + "."

    def stop(self) -> str:
        with self._lock:
            block = self._block
            self._block = None
            self._stop.set()
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        if block is None:
            return "No focus session is active."
        elapsed = max(0, round((self._clock() - block.started_at) / 60))
        self._log(f"Focus ended after {elapsed} min; distractions detected: {block.drifts}")
        return f"Focus session ended after {elapsed} minutes. Distractions detected: {block.drifts}."

    def _run(self, block: FocusBlock, stop_event: threading.Event) -> None:
        while not stop_event.wait(self._interval):
            with self._lock:
                if self._block is not block:
                    return
            try:
                front = self._observe()
                result = check_block(block, front, now=self._clock())
            except Exception as exc:
                self._log(f"Focus check unavailable: {exc}")
                continue
            if result.get("end"):
                with self._lock:
                    if self._block is block:
                        self._block = None
                        self._thread = None
                self._notify("Your focus session has finished.")
                self._log("Focus session completed.")
                return
            if result.get("nudge"):
                self._notify(f"You're still on {result['nudge']}. Gently return to your focus task.")
                self._log(f"Focus nudge: {result['nudge']}")
