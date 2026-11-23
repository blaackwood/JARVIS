import unittest

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from gui.widgets import RoutineRow


_APP = QApplication.instance() or QApplication([])


class RoutineRowReminderUiTests(unittest.TestCase):
    def click(self, row, x):
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(float(x), 10.0),
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        row.mousePressEvent(event)

    def make_row(self, routine):
        row = RoutineRow()
        row.resize(300, 40)
        row.set_routine(routine)
        return row

    def test_open_reminder_check_emits_complete(self):
        row = self.make_row({"id": "r1", "name": "Pay bill", "source": "reminder",
                             "enabled": True, "options": {"jarvis_reminder": {"status": "open"}}})
        seen = []
        row.toggled.connect(lambda rid, enabled: seen.append((rid, enabled)))
        self.click(row, 290)
        self.assertEqual(seen, [("r1", False)])

    def test_done_or_cancelled_reminder_check_emits_reopen(self):
        for status in ("done", "cancelled"):
            with self.subTest(status=status):
                row = self.make_row({"id": "r2", "name": "Pay bill", "source": "reminder",
                                     "enabled": False, "options": {"jarvis_reminder": {"status": status}}})
                seen = []
                row.toggled.connect(lambda rid, enabled: seen.append((rid, enabled)))
                self.click(row, 290)
                self.assertEqual(seen, [("r2", True)])
                row.close()

    def test_missed_reminder_remains_an_open_commitment(self):
        row = self.make_row({"id": "r3", "name": "Pay bill", "source": "reminder",
                             "enabled": False, "options": {"jarvis_reminder": {"status": "missed"}}})
        seen = []
        row.toggled.connect(lambda rid, enabled: seen.append((rid, enabled)))
        self.click(row, 290)
        self.assertEqual(seen, [("r3", False)])

    def test_recurring_routine_keeps_original_on_off_switch(self):
        row = self.make_row({"id": "r4", "name": "Check-in", "source": "builtin", "enabled": True})
        seen = []
        row.toggled.connect(lambda rid, enabled: seen.append((rid, enabled)))
        self.click(row, 290)
        self.assertEqual(seen, [("r4", False)])

    def test_clicking_reminder_body_opens_details_not_completes(self):
        row = self.make_row({"id": "r5", "name": "Pay bill", "source": "reminder",
                             "enabled": True, "options": {"jarvis_reminder": {"status": "open"}}})
        seen = []
        row.clicked.connect(seen.append)
        self.click(row, 100)
        self.assertEqual(seen, ["r5"])


if __name__ == "__main__":
    unittest.main()
