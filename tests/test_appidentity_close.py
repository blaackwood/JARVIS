import os
import sys
import unittest
from unittest.mock import patch

from core import appidentity


class RequestCloseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.match = appidentity.Match(
            pid=43210, name="notepad.exe", score=105,
            is_self=False, titles=["Untitled - Notepad"],
        )

    @patch("core.appidentity.is_running", return_value=False)
    @patch("core.appidentity._post_close_windows", return_value=1)
    @patch("core.appidentity.self_exes", return_value={r"C:\\Python\\python.exe"})
    @patch("core.appidentity._ancestor_pids", return_value={100, 200})
    @patch("core.appidentity.psutil.Process")
    def test_assistant_can_close_application_it_launched(
        self, process, ancestors, self_exes, post_close, is_running
    ):
        process.return_value.exe.return_value = r"C:\\Windows\\System32\\notepad.exe"
        gone, detail = appidentity.request_close(self.match, timeout=0.1)
        self.assertTrue(gone, detail)
        self.assertEqual(detail, "")
        post_close.assert_called_once_with(self.match.pid)

    @patch("core.appidentity._ancestor_pids", return_value={100, 200, 43210})
    def test_assistant_ancestor_is_never_closed(self, ancestors):
        gone, detail = appidentity.request_close(self.match)
        self.assertFalse(gone)
        self.assertIn("ancestors", detail)

    @patch("core.appidentity.self_exes", return_value={os.path.normcase(sys.executable)})
    @patch("core.appidentity._ancestor_pids", return_value={100, 200})
    @patch("core.appidentity.psutil.Process")
    def test_same_interpreter_is_never_closed(self, process, ancestors, self_exes):
        process.return_value.exe.return_value = sys.executable
        gone, detail = appidentity.request_close(self.match)
        self.assertFalse(gone)
        self.assertIn("same program", detail)


if __name__ == "__main__":
    unittest.main()
