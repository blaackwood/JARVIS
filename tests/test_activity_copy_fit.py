import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit
from gui.widgets import LogWidget
from gui.visual_board import VisualBoardOverlay


_APP = QApplication.instance() or QApplication([])


class ActivityCopyAndCaptionTests(unittest.TestCase):
    def test_activity_log_wraps_long_lines_and_copies_all_text(self):
        widget = LogWidget()
        long_line = "JARVIS: " + ("This is a long activity sentence that must remain readable and copyable. " * 30)
        widget.setPlainText(long_line)
        self.assertEqual(widget.lineWrapMode(), QTextEdit.LineWrapMode.WidgetWidth)
        copied = widget.copy_all_text()
        self.assertEqual(copied, long_line)
        self.assertEqual(_APP.clipboard().text(), long_line)
        widget.deleteLater()
        _APP.processEvents()

    def test_content_panel_receives_full_news_and_briefing_text(self):
        from ui import JarvisUI

        class Signal:
            def __init__(self):
                self.args = None
            def emit(self, *args):
                self.args = args

        class FakeWindow:
            def __init__(self):
                self._content_sig = Signal()

        fake = type("FakeUI", (), {})()
        fake._win = FakeWindow()
        text = "Full news and briefing body. " * 400
        title = "NEWS — " + ("very long topic " * 10)
        JarvisUI.show_content(fake, title, text)
        self.assertEqual(fake._win._content_sig.args[0], title[:48])
        self.assertEqual(fake._win._content_sig.args[1], text)

    def test_activity_log_copy_selected_is_supported_by_text_edit(self):
        widget = LogWidget()
        widget.setPlainText("first line\nsecond line")
        cursor = widget.textCursor()
        cursor.select(cursor.SelectionType.Document)
        widget.setTextCursor(cursor)
        widget.copy()
        self.assertEqual(_APP.clipboard().text(), "first line\nsecond line")
        widget.deleteLater()
        _APP.processEvents()

    def test_live_caption_keeps_full_long_transcript(self):
        board = VisualBoardOverlay()
        transcript = "Long narrated activity. " * 60
        board.set_live_caption(transcript)
        self.assertEqual(board._live_caption, transcript.strip())
        board.deleteLater()
        _APP.processEvents()

    def test_board_copy_menu_helper_copies_full_narration_and_step(self):
        board = VisualBoardOverlay()
        narration = "Full narration text. " * 40
        step = "Full activity instruction. " * 20
        board.set_live_caption(narration)
        board.set_lesson_status(step, 1, 3)
        combined = board.copy_caption_text("both")
        self.assertEqual(combined, narration.strip() + "\n\n" + step)
        self.assertEqual(_APP.clipboard().text(), combined)
        board.copy_caption_text("live")
        self.assertEqual(_APP.clipboard().text(), narration.strip())
        board.deleteLater()
        _APP.processEvents()

    def test_live_skin_activity_copy_preserves_full_long_entries(self):
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        skin_dir = str(root / "visual_novo")
        if skin_dir not in sys.path:
            sys.path.insert(0, skin_dir)
        from live_skin import LiveSkin

        fake = type("FakeLiveSkin", (), {})()
        fake.log = []
        long_entry = "Full assistant activity entry. " * 80
        LiveSkin._note(fake, long_entry)
        copied = LiveSkin.copy_activity_log(fake)
        self.assertIn(long_entry, copied)
        self.assertEqual(_APP.clipboard().text(), copied)

        captured = {}
        fake.open_panel = lambda panel: captured.update(panel)
        LiveSkin._show_activity_detail(fake, 0)
        self.assertEqual(captured["paras"][1], long_entry)
        self.assertEqual(captured["_copy_text"], captured["paras"][0] + "\n\n" + long_entry)

    def test_live_skin_news_panel_keeps_full_content_and_copy_text(self):
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        skin_dir = str(root / "visual_novo")
        if skin_dir not in sys.path:
            sys.path.insert(0, skin_dir)
        from live_skin import LiveSkin

        fake = type("FakeLiveSkin", (), {})()
        captured = {}
        fake.open_panel = lambda panel: captured.update(panel)
        text = ("Full news article list and briefing text. " * 250).rstrip()
        LiveSkin._text_panel(fake, "NEWS — hoje", text)
        self.assertEqual(captured["_copy_text"], text)
        self.assertEqual("\n".join(captured["paras"]), text)

    def test_preview_opening_activity_detail_does_not_add_a_new_activity(self):
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        skin_dir = str(root / "visual_novo")
        if skin_dir not in sys.path:
            sys.path.insert(0, skin_dir)
        from preview import NovoVisual

        visual = NovoVisual()
        before = list(visual.log)
        visual.open_panel({"kind": "ATIVIDADE", "title": "Viewing detail", "paras": ["full"]})
        self.assertEqual(visual.log, before)
        visual.close_panel()
        visual.deleteLater()
        _APP.processEvents()

    def test_preview_activity_wraps_complete_message_without_eliding(self):
        import sys
        from pathlib import Path
        from PyQt6.QtGui import QFontMetrics
        root = Path(__file__).resolve().parents[1]
        skin_dir = str(root / "visual_novo")
        if skin_dir not in sys.path:
            sys.path.insert(0, skin_dir)
        from preview import NovoVisual, wrap_lines

        visual = NovoVisual()
        message = ("Jarvis online -- sleeping... Jarvis online-- sleeping. Say " + ("the wake word to activate. " * 35)).strip()
        metrics = QFontMetrics(visual.f_body)
        wrapped = wrap_lines(metrics, message, 180)
        self.assertEqual(" ".join(wrapped), message)
        self.assertGreater(len(wrapped), 3)
        visual.deleteLater()
        _APP.processEvents()

    def test_preview_copy_fallback_copies_all_paragraphs(self):
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        skin_dir = str(root / "visual_novo")
        if skin_dir not in sys.path:
            sys.path.insert(0, skin_dir)
        from preview import NovoVisual

        fake = type("FakePreview", (), {})()
        paras = ["first paragraph " * 30, "second paragraph " * 30]
        fake.panel = {"paras": paras}
        fake._panel_copy_text = None
        copied = NovoVisual.copy_panel_content(fake)
        self.assertEqual(copied, "\n\n".join(paras))
        self.assertEqual(_APP.clipboard().text(), copied)

    def test_long_live_and_step_captions_render_with_adaptive_wrapping(self):
        from PyQt6.QtGui import QImage
        from PyQt6.QtCore import Qt

        board = VisualBoardOverlay()
        narration = ("A explicação completa precisa continuar visível e legível. " * 18).strip()
        step = ("Instrução da atividade com várias palavras para quebrar em linhas. " * 4).strip()
        board.resize(1280, 720)
        board.set_live_caption(narration)
        board.set_lesson_status(step, 2, 5)
        board.show()
        _APP.processEvents()
        image = QImage(board.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        board.render(image)
        self.assertFalse(image.isNull())
        self.assertEqual(board._live_caption, narration)
        self.assertEqual(board._lesson_caption, step)
        board.close()
        board.deleteLater()
        _APP.processEvents()

    def test_lesson_footer_caption_is_not_truncated(self):
        board = VisualBoardOverlay()
        caption = "Long lesson instruction. " * 25
        board.set_lesson_status(caption, 1, 4)
        self.assertEqual(board._lesson_caption, caption)
        board.deleteLater()
        _APP.processEvents()


if __name__ == "__main__":
    unittest.main()
