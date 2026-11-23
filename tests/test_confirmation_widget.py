import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton
from gui.overlays import ConfirmBanner


class ConfirmationWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _click_button(self, banner, text_part):
        for button in banner.findChildren(QPushButton):
            if text_part in button.text():
                button.click()
                self.app.processEvents()
                return
        self.fail(f"button containing {text_part!r} not found")

    def test_confirm_button_emits_true(self):
        banner = ConfirmBanner("Delete file", "Review the target")
        answers = []
        banner.answered.connect(answers.append)
        self._click_button(banner, "CONFIRM")
        self.assertEqual(answers, [True])
        banner.deleteLater()
        self.app.processEvents()

    def test_cancel_button_emits_false(self):
        banner = ConfirmBanner("Delete file", "Review the target")
        answers = []
        banner.answered.connect(answers.append)
        self._click_button(banner, "CANCEL")
        self.assertEqual(answers, [False])
        banner.deleteLater()
        self.app.processEvents()

    def test_cancel_is_the_default_button(self):
        banner = ConfirmBanner("Delete file", "Review the target")
        defaults = [b for b in banner.findChildren(QPushButton) if b.isDefault()]
        self.assertEqual(len(defaults), 1)
        self.assertIn("CANCEL", defaults[0].text())
        banner.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
