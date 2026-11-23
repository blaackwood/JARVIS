from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SingleVisualSkinTests(unittest.TestCase):
    def test_startup_requires_the_new_visual_and_never_selects_an_old_skin(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn("live_skin.attach(self._win)", source)
        self.assertIn("raise RuntimeError", source)
        self.assertNotIn("JARVIS_SKIN", source)
        self.assertNotIn("ui_skin", source)

    def test_live_skin_has_no_return_switch_or_classic_fallback(self):
        source = (ROOT / "visual_novo" / "live_skin.py").read_text(encoding="utf-8-sig")
        for token in ("_manual_classic", "_classic_needed", "_go_classic",
                      "_come_back", "start_classic", "_save_skin", "ui_skin"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        tree = ast.parse(source)
        attach = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "attach")
        self.assertEqual([arg.arg for arg in attach.args.args], ["win"])

    def test_gui_is_a_real_runtime_package_not_a_path_to_an_old_visual_folder(self):
        init = (ROOT / "gui" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("__path__", init)
        self.assertTrue((ROOT / "gui" / "window.py").is_file())
        self.assertFalse((ROOT / "visual_classico").exists())
        self.assertFalse((ROOT / "gui_runtime").exists())

    def test_settings_route_does_not_fall_through_to_an_alternate_interface(self):
        source = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        start = source.index("    def _route_holo_workspace")
        end = source.index("    def _open_customize", start)
        route = source[start:end]
        self.assertIn("return True", route)
        self.assertIn("skin.open_workspace(page)", route)
        self.assertNotIn("_manual_classic", route)

    def test_quiz_is_presented_by_the_new_skin(self):
        source = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        self.assertIn("skin.show_quiz(topic, questions, grader)", source)
        skin = (ROOT / "visual_novo" / "live_skin.py").read_text(encoding="utf-8-sig")
        self.assertIn("def show_quiz(", skin)
        self.assertIn("def _sync_media_surface(", skin)

    def test_review_and_code_progress_route_to_new_selectable_content_surface(self):
        source = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        skin = (ROOT / "visual_novo" / "live_skin.py").read_text(encoding="utf-8-sig")
        self.assertGreaterEqual(source.count("skin.show_rich_panel(title, \"\".join(parts))"), 2)
        self.assertIn("def show_rich_panel(self, title, html):", skin)
        self.assertIn('self.news_select.setHtml(rich_html)', skin)
        self.assertIn('self._panel_copy_text = self.news_select.toPlainText()', skin)

    def test_live_news_and_search_shortcuts_do_not_use_static_demo_content(self):
        skin = (ROOT / "visual_novo" / "live_skin.py").read_text(encoding="utf-8-sig")
        preview = (ROOT / "visual_novo" / "preview.py").read_text(encoding="utf-8-sig")
        self.assertIn("def open_news(self):", skin)
        self.assertIn("Busque e apresente as principais notícias atuais", skin)
        self.assertIn("def open_search(self):", skin)
        self.assertIn("Pesquise na web:", skin)
        self.assertIn("def open_news(self):", preview)  # prototype remains isolated in preview

    def test_active_visual_has_clean_portuguese_accents_and_labels(self):
        skin = (ROOT / "visual_novo" / "live_skin.py").read_text(encoding="utf-8-sig")
        preview = (ROOT / "visual_novo" / "preview.py").read_text(encoding="utf-8-sig")
        fragments = (
            "Voc" + chr(0x00ea) + ":",
            "Mem" + chr(0xf3) + "ria",
            "ativa" + chr(0xe7) + chr(0xe3) + "o",
            "not" + chr(0xed) + "cias",
            "PR" + chr(0xd3) + "XIMA",
        )
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, skin)
        # Do not reject valid Portuguese uppercase accents such as Ã in
        # PERSONALIZAÇÃO. Reject common UTF-8/Windows-codepage mojibake sequences.
        for bad in ("Ãƒ", "Ã‚", "â€", chr(0xfffd)):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, skin)
                self.assertNotIn(bad, preview)


if __name__ == "__main__":
    unittest.main()

