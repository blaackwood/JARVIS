import unittest
from pathlib import Path

from actions import opencode_agent as agent


class SuperpowersIntegrationTests(unittest.TestCase):
    def test_improve_mode_loads_superpowers_plugin(self):
        config = agent._permissions(False)
        expected = str((Path.home() / ".config" / "opencode" / "superpowers").resolve())
        self.assertIn(expected, config["plugins"])

    def test_improve_mode_allows_skills_and_limited_subagents(self):
        rules = agent._permissions(False)["permissions"]
        self.assertIn(
            {"action": "skill", "resource": "*", "effect": "allow"}, rules
        )
        self.assertIn(
            {"action": "subagent", "resource": "*", "effect": "deny"}, rules
        )
        self.assertIn(
            {"action": "subagent", "resource": "general", "effect": "allow"}, rules
        )
        self.assertIn(
            {"action": "subagent", "resource": "explore", "effect": "allow"}, rules
        )

    def test_review_mode_keeps_skills_and_subagents_disabled(self):
        rules = agent._permissions(True)["permissions"]
        self.assertIn(
            {"action": "skill", "resource": "*", "effect": "deny"}, rules
        )
        self.assertIn(
            {"action": "subagent", "resource": "*", "effect": "deny"}, rules
        )
        self.assertFalse(
            any(
                rule["action"] == "subagent" and rule["effect"] == "allow"
                for rule in rules
            )
        )


if __name__ == "__main__":
    unittest.main()
