import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import file_controller as fc
from core import authorization


class OpenFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / "Folder"
        self.folder.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_open_folder_launches_windows_explorer(self):
        with patch.object(fc, "_OS", "Windows"), patch.object(fc.os, "startfile", create=True) as startfile:
            result = fc.open_folder(str(self.folder))
        startfile.assert_called_once_with(str(self.folder.resolve()))
        self.assertIn("Opened folder", result)

    def test_open_folder_rejects_path_outside_safe_root(self):
        with patch.object(fc, "_resolve_path", return_value=Path("C:/Windows")):
            result = fc.open_folder("C:/Windows")
        self.assertIn("Access denied", result)

    def test_open_folder_rejects_missing_path(self):
        result = fc.open_folder(str(self.folder / "missing"))
        self.assertIn("Folder not found", result)

    def test_videos_shortcut_resolves_to_existing_user_folder(self):
        target = fc._resolve_path("videos")
        self.assertTrue(target.exists())
        self.assertTrue(target.is_dir())
        self.assertTrue(fc._is_safe_path(target))

    def test_open_recovers_model_mistake_c_videos_to_user_videos(self):
        with (
            patch.object(fc, "_OS", "Windows"),
            patch.object(fc, "_get_videos", return_value=self.folder),
            patch.object(fc.os, "startfile", create=True) as startfile,
        ):
            result = fc.open_folder("C:/Videos")
        startfile.assert_called_once_with(str(self.folder.resolve()))
        self.assertIn(str(self.folder.resolve()), result)

    def test_open_action_is_read_only(self):
        self.assertEqual(
            authorization.classify_action("file_controller", {"action": "open"}),
            "read_only",
        )


if __name__ == "__main__":
    unittest.main()
