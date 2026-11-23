import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QMenu
from gui.widgets import FileDropZone


class FileDropZoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / "sample.png"
        self.file.write_bytes(b"synthetic image selection")
        self.zone = FileDropZone()
        self.selected = []
        self.zone.file_selected.connect(self.selected.append)

    def tearDown(self):
        self.zone.close()
        self.zone.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def _drop(self, path):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(
            QPointF(8, 8), Qt.DropAction.CopyAction, mime,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.zone.dropEvent(event)
        return event

    def test_file_picker_sets_current_file_and_emits_signal(self):
        def choose_first_action(menu, *args, **kwargs):
            return menu.actions()[0]

        with patch.object(QMenu, "exec", new=choose_first_action), \
             patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.file), "All Files")):
            self.zone._browse()
        self.assertEqual(Path(self.zone.current_file()).resolve(), self.file.resolve())
        self.assertEqual(len(self.selected), 1)
        self.assertEqual(Path(self.selected[0]).resolve(), self.file.resolve())

    def test_drop_sets_file_emits_signal_and_accepts_event(self):
        event = self._drop(self.file)
        self.assertEqual(Path(self.zone.current_file()).resolve(), self.file.resolve())
        self.assertEqual(len(self.selected), 1)
        self.assertEqual(Path(self.selected[0]).resolve(), self.file.resolve())
        self.assertTrue(event.isAccepted())

    def test_drop_rejects_missing_path_without_changing_selection(self):
        event = self._drop(self.root / "missing.pdf")
        self.assertIsNone(self.zone.current_file())
        self.assertEqual(self.selected, [])
        self.assertFalse(event.isAccepted())

    def test_clear_removes_selected_file(self):
        self._drop(self.file)
        self.zone.clear_file()
        self.assertIsNone(self.zone.current_file())


if __name__ == "__main__":
    unittest.main()
