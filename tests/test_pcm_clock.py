"""Deterministic tests for the callback-driven PCM playback clock."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.pcm_clock import LessonMark, PcmPlayer


class _FakeOutputStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.latency = 0.012
        self.started = False
        self.aborted = 0
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def abort(self):
        self.aborted += 1
        self.started = False

    def close(self):
        self.closed = True

    def pump(self, frames, current=10.0, dac=10.010):
        output = bytearray(frames * 2)
        time_info = SimpleNamespace(
            currentTime=current,
            outputBufferDacTime=dac,
        )
        self.callback(output, frames, time_info, None)
        return bytes(output)


class _FakeSoundDevice:
    def __init__(self):
        self.stream = None

    def RawOutputStream(self, **kwargs):
        self.stream = _FakeOutputStream(**kwargs)
        return self.stream


class PcmPlayerTests(unittest.TestCase):
    def test_audible_clock_uses_dac_time_and_counts_only_real_frames(self):
        sound = _FakeSoundDevice()
        player = PcmPlayer(sound, samplerate=24000, channels=1, blocksize=8)
        try:
            player.start()
            samples = bytes(range(8))  # four int16 frames
            player.write(samples)

            self.assertAlmostEqual(player.written_seconds(), 4 / 24000)
            self.assertAlmostEqual(player.pending_seconds(), 4 / 24000)

            with patch("core.pcm_clock.time.perf_counter", return_value=10.0):
                output = sound.stream.pump(8)

            self.assertEqual(output[:8], samples)
            self.assertEqual(output[8:], bytes(8))  # underrun silence
            self.assertEqual(player._consumed, 4)   # not the 8 requested frames

            with patch("core.pcm_clock.time.perf_counter", return_value=10.009):
                self.assertEqual(player.audible_seconds(), 0.0)
            with patch("core.pcm_clock.time.perf_counter", return_value=10.011):
                self.assertAlmostEqual(player.audible_seconds(), 4 / 24000)
                self.assertTrue(player.is_drained())
        finally:
            player.close()

    def test_flush_discards_python_and_device_buffered_audio(self):
        sound = _FakeSoundDevice()
        player = PcmPlayer(sound, samplerate=24000, channels=1, blocksize=4)
        try:
            player.start()
            player.write(bytes(16))  # eight frames
            with patch("core.pcm_clock.time.perf_counter", return_value=10.0):
                sound.stream.pump(4)
            self.assertGreater(player.pending_seconds(), 0.0)

            player.flush()

            self.assertEqual(player.pending_seconds(), 0.0)
            self.assertAlmostEqual(player.written_seconds(), 4 / 24000)
            self.assertEqual(sound.stream.aborted, 1)
            self.assertTrue(sound.stream.started)
        finally:
            player.close()

    def test_lesson_mark_is_an_ordered_fifo_control_item(self):
        start = LessonMark("start", 3)
        end = LessonMark("end", 3)
        self.assertEqual((start.kind, start.index), ("start", 3))
        self.assertEqual((end.kind, end.index), ("end", 3))


if __name__ == "__main__":
    unittest.main()
