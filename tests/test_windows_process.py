import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.windows_process import hidden_creationflags


CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


class HiddenProcessPolicyTests(unittest.TestCase):
    def test_default_child_process_gets_no_window_flag(self):
        flags = hidden_creationflags(0)
        self.assertTrue(flags & CREATE_NO_WINDOW)
        self.assertFalse(flags & CREATE_NEW_CONSOLE)

    def test_existing_detached_flags_are_preserved(self):
        flags = hidden_creationflags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(flags & DETACHED_PROCESS)
        self.assertTrue(flags & CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(flags & CREATE_NO_WINDOW)

    def test_explicit_new_console_is_overridden(self):
        flags = hidden_creationflags(CREATE_NEW_CONSOLE)
        self.assertFalse(flags & CREATE_NEW_CONSOLE)
        self.assertTrue(flags & CREATE_NO_WINDOW)


if __name__ == "__main__":
    unittest.main()
