import tempfile
import unittest
from pathlib import Path

from core.tasks.agents import load
from core.tasks.tools import KNOWN, TaskTools


class SpecialistAgentTests(unittest.TestCase):
    def test_specialist_profiles_load_with_expected_roles(self):
        root = Path(__file__).resolve().parents[1] / "agents"
        profiles = load([root], log=lambda *_: None)

        self.assertIn("document_analyst", profiles)
        self.assertIn("study_coach", profiles)
        self.assertIn("quality_reviewer", profiles)
        self.assertIn("researcher", profiles)
        self.assertIn("general", profiles)

    def test_background_task_tool_advertises_the_specialist_profiles(self):
        from actions.background_tasks import TOOL

        description = TOOL["description"]
        agent_schema = TOOL["parameters"]["properties"]["agent"]["description"]
        for name in ("document_analyst", "study_coach", "quality_reviewer"):
            self.assertIn(name, description)
            self.assertIn(name, agent_schema)

    def test_study_coach_can_recall_private_memory_but_has_no_web(self):
        root = Path(__file__).resolve().parents[1] / "agents"
        profile = load([root], log=lambda *_: None)["study_coach"]
        with tempfile.TemporaryDirectory() as folder:
            tools = TaskTools(Path(folder), profile.tools, log=lambda *_: None)

        self.assertIn("recall_memory", tools.names)
        self.assertFalse(tools.has_web)

    def test_document_and_quality_agents_are_limited_to_task_files(self):
        root = Path(__file__).resolve().parents[1] / "agents"
        profiles = load([root], log=lambda *_: None)
        for name in ("document_analyst", "quality_reviewer"):
            with self.subTest(agent=name), tempfile.TemporaryDirectory() as folder:
                tools = TaskTools(Path(folder), profiles[name].tools, log=lambda *_: None)
                self.assertIn("file_processor", tools.names)
                self.assertIn("write_file", tools.names)
                self.assertFalse(tools.has_web)
                self.assertNotIn("recall_memory", tools.names)

    def test_background_agents_never_receive_desktop_control_tools(self):
        self.assertNotIn("computer_control", KNOWN)
        self.assertNotIn("send_message", KNOWN)
        self.assertNotIn("open_app", KNOWN)


if __name__ == "__main__":
    unittest.main()
