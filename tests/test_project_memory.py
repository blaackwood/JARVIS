import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import project_memory as pm


class ProjectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-test-project-memory-")
        self._projects_patch = patch.object(pm, "PROJECTS_DIR", Path(self.temp.name))
        self._projects_patch.start()
        self.name = "test-project-memory"
        self.path = pm.PROJECTS_DIR / "test-project-memory.json"

    def tearDown(self):
        self._projects_patch.stop()
        self.temp.cleanup()

    def test_create_and_retrieve_project(self):
        saved = pm.update_project(
            self.name, status="In progress",
            decisions=["Keep project memory separate"],
            next_steps=["Add automatic session handoff"],
        )
        loaded = pm.get_project(self.name)
        self.assertEqual(saved["status"], "In progress")
        self.assertEqual(loaded["next_steps"], ["Add automatic session handoff"])

    def test_updates_append_unique_items(self):
        pm.update_project(self.name, decisions=["Use JSON"])
        result = pm.update_project(self.name, decisions=["Use JSON", "Keep backups"])
        self.assertEqual(result["decisions"], ["Use JSON", "Keep backups"])

    def test_project_name_cannot_escape_memory_directory(self):
        path = pm._path("../../outside")
        self.assertEqual(path.parent, pm.PROJECTS_DIR)
        self.assertTrue(path.name.endswith(".json"))

    def test_search_finds_project_context(self):
        pm.update_project(self.name, blockers=["Audio device reconnect issue"])
        result = pm.search_projects("reconnect")
        self.assertIn("Audio device reconnect issue", result)

    def test_prompt_format_includes_next_steps(self):
        project = {"name": "Example", "status": "Active", "next_steps": ["Write tests"]}
        prompt = pm.format_project_for_prompt(project)
        self.assertIn("Write tests", prompt)

    def test_session_summary_is_attached_only_to_mentioned_projects(self):
        pm.update_project(self.name, status="Active")
        saved = pm.save_session_summary_for_projects(
            "We discussed test-project-memory and its next step.",
            "The next step is to add a regression test.",
        )
        self.assertEqual(saved, [self.name])
        project = pm.get_project(self.name)
        self.assertTrue(any("regression test" in note for note in project["notes"]))

    def test_session_summary_does_not_update_unmentioned_projects(self):
        pm.update_project(self.name, status="Active")
        saved = pm.save_session_summary_for_projects(
            "We discussed an unrelated topic.",
            "No project changes were made.",
        )
        self.assertEqual(saved, [])

    def test_exact_project_name_ranks_above_note_only_match(self):
        pm.update_project("jarvis-main", status="Active")
        pm.update_project("other-project", notes=["A note mentions jarvis-main"])
        result = pm.search_projects("jarvis-main", limit=2)
        self.assertTrue(result.startswith("Project: jarvis-main"))

    def test_project_search_prioritizes_status_and_next_steps(self):
        pm.update_project("audio-tools", status="Active", next_steps=["Tune microphone capture"])
        pm.update_project("archive", notes=["Old microphone experiment"])
        result = pm.search_projects("microphone", limit=2)
        self.assertLess(result.find("Project: audio-tools"), result.find("Project: archive"))


if __name__ == "__main__":
    unittest.main()
