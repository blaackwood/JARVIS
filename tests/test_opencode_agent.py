import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import opencode_agent as agent


class OpenCodeAgentTests(unittest.TestCase):
    def test_coding_agent_uses_free_only_priority_combo(self):
        self.assertEqual(
            agent._MODEL, "omniroute/jarvis-coding-free-v2"
        )

    def test_run_config_preserves_global_provider_and_overlays_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True)
            (config_dir / "opencode.json").write_text(
                '{"provider":{"omniroute":{"models":{"jarvis-coding-free":{}}}},'
                '"agents":{"coder":{"model":"omniroute/arsenal"},"tester":{"mode":"subagent","model":"omniroute/arsenal"}},'
                '"plugins":["existing-plugin"]}', encoding="utf-8"
            )
            with patch.object(agent.Path, "home", return_value=home):
                config = agent._merged_opencode_config(False, model="omniroute/nvidia/nvidia/nemotron-3.5-lightning-30b-a3b")
            self.assertIn("jarvis-coding-free", config["provider"]["omniroute"]["models"])
            self.assertIn("existing-plugin", config["plugins"])
            self.assertEqual(config["model"], "omniroute/nvidia/nvidia/nemotron-3.5-lightning-30b-a3b")
            self.assertTrue(all(
                value.get("model") == config["model"]
                for value in config["agents"].values()
                if isinstance(value, dict)
            ))
            self.assertIn(str(home / ".config" / "opencode" / "superpowers"), config["plugins"])
            self.assertIn(
                {"action": "edit", "resource": "*", "effect": "allow"},
                config["permissions"],
            )

    def test_nested_folder_inside_git_repo_is_rejected(self):
        if not shutil.which("git"):
            self.skipTest("git is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo = home / "Documents" / "repo"
            nested = repo / "subproject"
            nested.mkdir(parents=True)
            (nested / "README.md").write_text("test", encoding="utf-8")
            subprocess.run(
                ["git", "init", str(repo)], check=True, stdin=subprocess.DEVNULL,
                capture_output=True, text=True,
            )
            with patch.object(agent.Path, "home", return_value=home):
                folder, error = agent._project(str(nested))
            self.assertIsNone(folder)
            self.assertIn(str(repo.resolve()), error)
            self.assertIn("raiz do repositório", error)

    def test_syntax_reader_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bom.py"
            source.write_bytes(bytes.fromhex("efbbbf6465662068656c6c6f28293a0a202072657475726e20276f6b270a"))
            text = agent._read_syntax_text(source)
            self.assertTrue(text.startswith("def hello():"))
            compile(text, str(source), "exec")

    def test_review_mode_is_read_only(self):
        rules = agent._permissions(True)["permissions"]
        self.assertIn(
            {"action": "edit", "resource": "*", "effect": "deny"}, rules
        )
        self.assertIn(
            {"action": "shell", "resource": "*", "effect": "deny"}, rules
        )
        self.assertIn(
            {"action": "external_directory", "resource": "*", "effect": "deny"},
            rules,
        )

    def test_agent_browser_cli_is_allowed_only_in_improve_mode(self):
        improve = agent._permissions(False)["permissions"]
        review = agent._permissions(True)["permissions"]
        self.assertIn(
            {"action": "shell", "resource": "agent-browser *", "effect": "allow"},
            improve,
        )
        self.assertIn(
            {"action": "shell", "resource": "*", "effect": "deny"},
            review,
        )
        self.assertNotIn(
            {"action": "shell", "resource": "*", "effect": "allow"},
            improve,
        )

    def test_node_builtin_tests_are_allowed_in_improve_mode(self):
        improve = agent._permissions(False)["permissions"]
        self.assertIn(
            {"action": "shell", "resource": "node --test*", "effect": "allow"},
            improve,
        )

    def test_project_gitignore_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / ".gitignore").write_text(
                "private.txt\nbuild/\n", encoding="utf-8"
            )
            rules = agent._permissions(False, folder)["permissions"]
            denied = {
                (item["action"], item["resource"], item["effect"])
                for item in rules
            }
            self.assertIn(("edit", "**/private.txt", "deny"), denied)
            self.assertIn(("read", "**/private.txt", "deny"), denied)
            self.assertIn(("edit", "**/build/**", "deny"), denied)

    def test_backup_excludes_ignored_secret_and_restores_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "project"
            backup = root / "backup"
            folder.mkdir()
            (folder / ".gitignore").write_text(
                "secret.txt\nbuild/\n", encoding="utf-8"
            )
            (folder / "main.py").write_text(
                'print("original")\n', encoding="utf-8"
            )
            (folder / "secret.txt").write_text(
                "do not copy", encoding="utf-8"
            )

            before = agent._snapshot(folder, backup)
            self.assertIn("main.py", before)
            self.assertNotIn("secret.txt", before)
            self.assertFalse((backup / "secret.txt").exists())

            (folder / "main.py").write_text(
                'print("changed")\n', encoding="utf-8"
            )
            (folder / "new.py").write_text(
                'print("new")\n', encoding="utf-8"
            )
            delta = agent._delta(before, agent._snapshot(folder))
            errors = agent._restore(folder, backup, delta)

            self.assertEqual(errors, [])
            self.assertEqual(
                (folder / "main.py").read_text(encoding="utf-8"),
                'print("original")\n',
            )
            self.assertFalse((folder / "new.py").exists())
            self.assertEqual(
                (folder / "secret.txt").read_text(encoding="utf-8"),
                "do not copy",
            )

    def test_delta_reports_created_modified_and_deleted(self):
        before = {"same.py": "a", "changed.py": "b", "deleted.py": "c"}
        after = {"same.py": "a", "changed.py": "new", "created.py": "d"}
        delta = agent._delta(before, after)
        self.assertEqual(delta["created"], ["created.py"])
        self.assertEqual(delta["modified"], ["changed.py"])
        self.assertEqual(delta["deleted"], ["deleted.py"])

    def test_secret_redaction(self):
        redacted = agent._redact(
            "Bearer abcdef1234567890 api_key=sk-abcdefghijklmnop"
        )
        self.assertNotIn("abcdef1234567890", redacted)
        self.assertNotIn("sk-abcdefghijklmnop", redacted)
        self.assertIn("[redacted]", redacted)


    def test_timeout_details_redact_credentials(self):
        details = agent._timeout_details(
            b"Bearer abcdef1234567890\\n",
            "api_key=sk-abcdefghijklmnop",
            ["server password supersecret"],
        )
        self.assertNotIn("abcdef1234567890", details)
        self.assertNotIn("sk-abcdefghijklmnop", details)
        self.assertNotIn("supersecret", details)
        self.assertIn("server password [redacted]", details)

    def test_large_files_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "large.bin").write_bytes(b"x" * (13 * 1024 * 1024))
            rules = agent._permissions(False, folder)["permissions"]
            denied = {
                (item["action"], item["resource"], item["effect"])
                for item in rules
            }
            self.assertIn(("read", "large.bin", "deny"), denied)
            self.assertIn(("edit", "large.bin", "deny"), denied)

if __name__ == "__main__":
    unittest.main()



