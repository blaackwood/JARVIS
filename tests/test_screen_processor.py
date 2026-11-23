import unittest
from unittest.mock import patch

from actions import screen_processor


class FakeShot:
    rgb = b"rgb"
    size = (2, 2)


class FakeMSS:
    def __init__(self):
        self.grabbed = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def grab(self, monitor):
        self.grabbed = monitor
        return FakeShot()


class ScreenProcessorTests(unittest.TestCase):
    def test_screen_capture_uses_monitor_for_foreground_window(self):
        monitor = {"left": 0, "top": 0, "width": 1440, "height": 900}
        fake = FakeMSS()
        with patch("core.screenview.look", return_value=object()), \
             patch("core.screenview.monitor_rect", return_value=monitor), \
             patch.object(screen_processor.mss, "mss", return_value=fake), \
             patch.object(screen_processor.mss.tools, "to_png", return_value=b"png"), \
             patch.object(screen_processor, "_compress", return_value=(b"jpeg", "image/jpeg")) as compress:
            result = screen_processor._capture_screen()
        self.assertEqual(fake.grabbed, monitor)
        compress.assert_called_once_with(b"png", "PNG")
        self.assertEqual(result, (b"jpeg", "image/jpeg"))


if __name__ == "__main__":
    unittest.main()
