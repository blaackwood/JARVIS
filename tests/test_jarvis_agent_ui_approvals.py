import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "_jarvis_agent_ui" / "server.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("jarvis_agent_ui_approvals_under_test", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class JarvisAgentApprovalScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.data = self.base / "data"
        self.data.mkdir()
        self.original = {
            "DATA": server.DATA,
            "ALWAYS_FILE": server._ALWAYS_FILE,
            "ACCESS_ROOTS": server.ACCESS_ROOTS,
            "ws": server.STATE["ws"],
            "term": server.STATE["term"],
            "always": set(server.ALWAYS),
        }
        server.DATA = self.data
        server._ALWAYS_FILE = self.data / "always_allow.json"
        server.ACCESS_ROOTS = [self.base]
        server.STATE["ws"] = self.workspace
        server.STATE["term"] = self.workspace
        server.ALWAYS.clear()
        self.task = {
            "id": "approval01", "title": "Approval scope test",
            "created": 1, "updated": 1, "messages": [], "events": [],
            "todos": [], "changes": {}, "procs": [], "allow": [],
            "running": False, "awaiting": False, "last": "",
        }

    def tearDown(self):
        server.DATA = self.original["DATA"]
        server._ALWAYS_FILE = self.original["ALWAYS_FILE"]
        server.ACCESS_ROOTS = self.original["ACCESS_ROOTS"]
        server.STATE["ws"] = self.original["ws"]
        server.STATE["term"] = self.original["term"]
        server.ALWAYS.clear()
        server.ALWAYS.update(self.original["always"])
        self.temp.cleanup()

    def test_workspace_file_permission_is_bound_to_exact_workspace(self):
        inside = self.workspace / "src" / "module.py"
        outside = self.base / "outside.py"
        self.assertEqual(server._workspace_file_allow(inside), server._workspace_allow("files"))
        self.assertIsNone(server._workspace_file_allow(outside))
        other_workspace = self.base / "other"
        other_workspace.mkdir()
        server.STATE["ws"] = other_workspace
        self.assertNotEqual(server._workspace_allow("files"), server._workspace_allow("commands"))
        self.assertNotEqual(server._workspace_file_allow(inside), server._workspace_allow("files"))

    def test_only_valid_workspace_scopes_can_be_persisted(self):
        files_token = server._workspace_allow("files")
        commands_token = server._workspace_allow("commands")
        self.assertTrue(server._valid_always_token(files_token))
        self.assertTrue(server._valid_always_token(commands_token))
        self.assertFalse(server._valid_always_token("workspace:everything:000000000000000000000000"))
        self.assertFalse(server._valid_always_token("run_command"))
        server._ALWAYS_FILE.write_text(
            __import__("json").dumps([files_token, commands_token, "run_command"]),
            encoding="utf-8",
        )
        loaded = server._load_always()
        self.assertEqual(loaded, {files_token, commands_token})

    def test_safe_command_allowlist_rejects_chaining_and_escape_paths(self):
        for command in (
            "python -m unittest -v",
            "python -m pytest -q",
            ".venv\\Scripts\\python.exe -m unittest -v",
            "node --check static\\app.js",
            "npm test",
            "npm run build",
            "git status --short",
            "git diff --check",
        ):
            with self.subTest(command=command):
                self.assertTrue(server._safe_workspace_command(command))
        for command in (
            "python -m unittest -v; Remove-Item important.txt",
            "python -m unittest ..\\outside",
            "python -m unittest C:\\Users\\bwd\\secret.py",
            "npm install",
            "Remove-Item src\\file.py",
            "python -c print(1)",
            "python -m unittest > result.txt",
        ):
            with self.subTest(command=command):
                self.assertFalse(server._safe_workspace_command(command))

    def test_user_can_trust_workspace_once_and_permission_is_persisted(self):
        import time

        token = server._workspace_allow("files")
        result = {}

        def request_approval():
            result["value"] = server.approve(
                self.task,
                "Pedir aprovação",
                "edit",
                "src/module.py",
                "Editar módulo?",
                diff=[],
                allow=token,
            )

        worker = threading.Thread(target=request_approval, daemon=True)
        with patch.object(server, "notify"):
            worker.start()
            deadline = time.time() + 3
            ask = None
            while time.time() < deadline:
                ask = next((event for event in self.task["events"] if event.get("t") == "ask"), None)
                if ask:
                    break
                time.sleep(0.01)

            self.assertIsNotNone(ask, "first workspace edit must request approval")
            self.assertEqual(ask["always"], "arquivos nesta pasta")
            status, response = server.api_approve({}, {"ask": ask["id"], "choice": 2, "note": ""})
            self.assertEqual(status, 200, response)
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(result["value"], (True, ""))
        self.assertIn(token, server.ALWAYS)
        self.assertIn(token, server._load_always())
        self.assertTrue(server._ALWAYS_FILE.is_file())

        event_count = len(self.task["events"])
        self.assertEqual(
            server.approve(self.task, "Pedir aprovação", "edit", "src/module.py",
                           "Editar módulo?", diff=[], allow=token),
            (True, ""),
        )
        self.assertEqual(len(self.task["events"]), event_count, "trusted edits should not ask again")

    def test_trusted_workspace_file_write_skips_repeated_prompt(self):
        token = server._workspace_allow("files")
        server.ALWAYS.add(token)
        stop = threading.Event()
        ok, message, detail = server.tool_write(
            self.task,
            {"path": "src\\new_module.py", "content": "VALUE = 42\n"},
            "Pedir aprovação",
            stop,
        )
        self.assertTrue(ok, message)
        self.assertEqual((self.workspace / "src" / "new_module.py").read_text("utf-8"), "VALUE = 42\n")
        self.assertFalse(self.task["awaiting"])
        self.assertFalse(any(event.get("t") == "ask" for event in self.task["events"]))
        self.assertEqual(detail["path"], "src/new_module.py")

    def test_trusted_workspace_test_command_skips_prompt_but_still_runs(self):
        token = server._workspace_allow("commands")
        server.ALWAYS.add(token)
        with patch.object(server, "sh", return_value=(0, "Ran 5 tests — OK")) as shell:
            ok, message, detail = server.tool_run(
                self.task,
                {"command": "python -m unittest -v"},
                "Pedir aprovação",
                threading.Event(),
            )
        self.assertTrue(ok, message)
        shell.assert_called_once()
        self.assertFalse(any(event.get("t") == "ask" for event in self.task["events"]))
        self.assertIn("Ran 5 tests", message)

    def test_untrusted_command_never_qualifies_for_persistent_permission(self):
        self.assertFalse(server._safe_workspace_command("python -m unittest -v; whoami"))
        self.assertFalse(server._safe_workspace_command("npm install"))
        self.assertFalse(server._safe_workspace_command("git reset --hard"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
