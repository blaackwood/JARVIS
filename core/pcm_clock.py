"""Sample-accurate speaker clock and in-band lesson markers for JARVIS speech.

Why this exists
---------------
Gemini Live gives us two unrelated streams: PCM audio and a text transcript.
Nothing ties a transcript word to a PCM sample, so any scheme that tries to
infer "when was this word audible" from queue sizes, wall-clock cursors or
characters-per-second is an estimate, and its error is unbounded.

This module removes the estimate:

* ``PcmPlayer`` owns the output stream. Its callback counts the frames that the
  device really consumed, and it records when each block will sound
  (``outputBufferDacTime``). ``audible_seconds()`` is therefore the position,
  in the speech stream, that is coming out of the speakers right now.
* ``LessonMark`` objects travel through the same FIFO as the PCM. When the
  playback loop reaches one it reads ``PcmPlayer.written_seconds()``: the exact
  stream position where that beat's audio begins or ends.

The visual board compares ``audible_seconds()`` with those positions; it never
needs to know what words were spoken.
"""
from __future__ import annotations

import collections
import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LessonMark:
    """A lesson boundary placed in the audio queue between PCM chunks."""
    kind: str          # start/end for beats; narration_start/narration_end for the script
    index: int         # 1-based beat number, or zero for the continuous script
    frames: int | None = None


@dataclass(frozen=True)
class CaptionMark:
    caption: str


class PcmPlayer:
    """Callback-driven int16 output with a real playback position.

    ``write()`` blocks while more than ``max_ahead`` seconds are buffered, which
    keeps the same back-pressure the old blocking ``RawOutputStream.write`` had
    (the avatar's mouth schedule depends on it).
    """

    def __init__(self, sd, samplerate: int, channels: int = 1, device=None,
                 blocksize: int = 1024, max_ahead: float = 0.30) -> None:
        self._sr = int(samplerate)
        self._channels = int(channels)
        self._bpf = 2 * self._channels                 # bytes per frame (int16)
        self._max_ahead_bytes = int(max_ahead * self._sr) * self._bpf
        self._cond = threading.Condition()
        self._buf = bytearray()
        self._carry = b""
        self._written = 0                              # frames accepted
        self._consumed = 0                             # real frames handed to the device
        self._generation = 0
        self._closed = False
        self._anchors: collections.deque = collections.deque(maxlen=64)
        self._latency = 0.10
        try:
            self._offset = float(os.environ.get("JARVIS_SYNC_OFFSET_MS", "0")) / 1000.0
        except ValueError:
            self._offset = 0.0
        self._stream = sd.RawOutputStream(
            samplerate=self._sr,
            channels=self._channels,
            dtype="int16",
            blocksize=int(blocksize),
            device=device,
            callback=self._callback,
        )

    # ── stream-like surface (so the playback loop barely changes) ────────────
    def start(self) -> None:
        self._stream.start()
        try:
            latency = float(getattr(self._stream, "latency", 0.0) or 0.0)
            if 0.0 < latency < 1.0:
                self._latency = latency
        except Exception:
            pass

    @property
    def latency(self) -> float:
        return float(self._latency)

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        self._stream.close()

    # ── producer side ────────────────────────────────────────────────────────
    def write(self, data: bytes) -> None:
        """Queue PCM; block while the device already has enough ahead."""
        if not data:
            return
        with self._cond:
            generation = self._generation
            data = self._carry + bytes(data)
            usable = len(data) - (len(data) % self._bpf)
            self._carry = data[usable:]
            data = data[:usable]
            while (
                self._buf
                and len(self._buf) + len(data) > self._max_ahead_bytes
                and not self._closed
                and generation == self._generation
            ):
                self._cond.wait(0.05)
            if self._closed or generation != self._generation:
                return                                  # flushed while waiting
            self._buf += data
            self._written += len(data) // self._bpf

    def flush(self) -> None:
        """Drop queued audio and device-buffered samples (barge-in)."""
        with self._cond:
            self._generation += 1
            self._buf.clear()
            self._carry = b""
            self._written = self._consumed
            self._anchors.clear()
            self._cond.notify_all()
        # PortAudio may already hold samples beyond the Python callback buffer.
        # Abort/restart clears that device-side tail as well; never call this from
        # the audio callback itself.
        try:
            self._stream.abort()
            self._stream.start()
        except Exception:
            # The next write still uses the generation guard. If the host API
            # cannot restart this stream, the session will reconnect on error.
            pass

    def pending_seconds(self) -> float:
        """PCM accepted by the Python player but not yet handed to the device."""
        with self._cond:
            return len(self._buf) / max(1, self._bpf * self._sr)

    def is_drained(self, tolerance: float = 0.025) -> bool:
        """True after queued samples have actually passed their DAC time."""
        with self._cond:
            if self._buf:
                return False
            written = self._written / self._sr
        try:
            return self.audible_seconds() + max(0.0, float(tolerance)) >= written
        except Exception:
            return False

    def written_seconds(self) -> float:
        """Stream position just after the last frame accepted so far."""
        with self._cond:
            return self._written / self._sr

    # ── clock ────────────────────────────────────────────────────────────────
    def audible_seconds(self) -> float:
        """Stream position that is leaving the speakers at this instant."""
        now = time.perf_counter()
        with self._cond:
            anchors = tuple(self._anchors)
            consumed = self._consumed
        position = None
        for start_at, start_frames, real_frames in reversed(anchors):
            if start_at <= now:
                position = start_frames + min(real_frames, (now - start_at) * self._sr)
                break
        if position is None:
            position = anchors[0][1] if anchors else float(consumed)
        return max(0.0, position / self._sr + self._offset)

    # ── device callback ──────────────────────────────────────────────────────
    def _callback(self, outdata, frames, time_info, status) -> None:
        need = frames * self._bpf
        with self._cond:
            take = min(len(self._buf), need)
            chunk = bytes(self._buf[:take]) if take else b""
            if take:
                del self._buf[:take]
            real_frames = take // self._bpf
            start_frames = self._consumed
            self._consumed += real_frames
            self._cond.notify_all()
        if take:
            outdata[:take] = chunk
        if take < need:
            outdata[take:need] = bytes(need - take)       # silence on underrun
        try:
            ahead = float(time_info.outputBufferDacTime) - float(time_info.currentTime)
        except Exception:
            ahead = -1.0
        if not (0.0 <= ahead < 2.0):
            ahead = self._latency
        with self._cond:
            self._anchors.append((time.perf_counter() + ahead, start_frames, real_frames))
