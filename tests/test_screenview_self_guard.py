import os
import unittest
from unittest.mock import patch

from core import screenview


class ScreenviewSelfGuardTests(unittest.TestCase):
    def test_current_process_is_protected(self):
        self.assertTrue(screenview._is_own_window(os.getpid()))

    def test_other_process_is_not_self_even_when_executable_is_shared(self):
        # Ancestor executables such as explorer.exe and PowerShell are not
        # the assistant's own window merely because they launched it.
        with patch("core.appidentity.self_exes", return_value={os.path.normcase(os.sys.executable)}):
            self.assertFalse(screenview._is_own_window(os.getpid() + 100000))

    def test_missing_pid_is_not_self(self):
        self.assertFalse(screenview._is_own_window(0))


if __name__ == "__main__":
    unittest.main()
