import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.skills import discover_skills, format_skill_index, read_skill


class SkillDiscoveryTests(unittest.TestCase):
    def test_discovers_skill_metadata_and_formats_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents" / "skills" / "sample-skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Use this for sample tasks.\n---\n\n# Guide",
                encoding="utf-8",
            )
            skills = discover_skills(Path(tmp))
            self.assertEqual([item["slug"] for item in skills], ["sample-skill"])
            index = format_skill_index(Path(tmp))
            self.assertIn("sample-skill", index)
            self.assertIn("use_skill", index)

    def test_reads_only_installed_skill_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents" / "skills" / "sample-skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Sample.\n---\n\nDo the task.",
                encoding="utf-8",
            )
            loaded = read_skill("sample-skill", Path(tmp))
            self.assertIn("Do the task.", loaded)
            self.assertIn("Supporting resources directory:", loaded)
            with self.assertRaises(ValueError):
                read_skill("../outside", Path(tmp))
            with self.assertRaises(FileNotFoundError):
                read_skill("missing", Path(tmp))

    def test_redistributed_anthropic_skills_keep_their_license_and_reference_gaps(self):
        root = Path(__file__).resolve().parents[1]
        lock = json.loads((root / "skills-lock.json").read_text(encoding="utf-8"))
        anthropic_slugs = {
            slug for slug, meta in lock.get("skills", {}).items()
            if meta.get("source") == "anthropics/skills"
        }
        installed_slugs = {item["slug"] for item in discover_skills()}
        licensed_slugs = {
            slug for slug in anthropic_slugs
            if (root / ".agents" / "skills" / slug / "LICENSE.txt").is_file()
        }
        reference_slugs = {"doc-coauthoring", "template-skill"}

        self.assertTrue(licensed_slugs)
        self.assertTrue(licensed_slugs.issubset(installed_slugs))
        self.assertIn("pdf", installed_slugs)
        self.assertIn("frontend-design", installed_slugs)
        self.assertTrue(reference_slugs.isdisjoint(installed_slugs))
        for slug in reference_slugs:
            self.assertTrue(
                (root / ".agents" / "skills" / slug / "UPSTREAM_REFERENCE.md").is_file()
            )

    def test_use_skill_action_is_discovered_and_read_only(self):
        from core.action_loader import discover_actions
        from core import authorization

        with tempfile.TemporaryDirectory(prefix="jarvis-test-skills-auth-") as tmp:
            root = Path(tmp)
            with patch.object(authorization, "_POLICY_PATH", root / "policy.json"), \
                    patch.object(authorization, "_AUDIT_PATH", root / "decisions.jsonl"):
                registry = discover_actions(Path(__file__).resolve().parents[1] / "actions",
                                            logger=lambda _message: None)
                self.assertTrue(registry.has("use_skill"))
                action_class, decision = authorization.authorize(
                    "use_skill", {"skill_name": "pdf"}
                )
                self.assertEqual((action_class, decision), ("read_only", "allow"))
                result = registry.run("use_skill", {"skill_name": "pdf"})
                self.assertIn("[SKILL: pdf]", result)
                self.assertIn("PDF Processing Guide", result)


if __name__ == "__main__":
    unittest.main()
