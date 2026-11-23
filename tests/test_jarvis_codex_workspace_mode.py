import sys
import threading
import unittest
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "_jarvis_agent_ui"))

import codex_agent

DANGER_TEST = re.compile(chr(92) + "b(rm|del|Remove-Item)" + chr(92) + "b|-Recurse", re.I)


def approval_context(root, emitted):
    root = Path(root).resolve()
    return {
        "DANGER": DANGER_TEST,
        "ws": lambda: root,
        "inside": lambda path, base: path == base or base in path.parents,
        "emit": lambda task, event: emitted.append(event),
    }


class CodexWorkspaceModeTests(unittest.TestCase):
    def test_workspace_mode_keeps_sandbox_writes_without_user_prompts(self):
        self.assertEqual(
            codex_agent._codex_execution_settings(codex_agent.WORKSPACE_MODE),
            ("on-request", "workspace-write"),
        )

    def test_workspace_mode_has_explicit_single_root_and_no_network(self):
        root = PROJECT_ROOT / "codex_workspace_mode_smoke_20261121"
        policy = codex_agent._codex_sandbox_policy(codex_agent.WORKSPACE_MODE, root)
        self.assertEqual(policy["type"], "workspaceWrite")
        self.assertEqual(policy["writableRoots"], [str(root.resolve())])
        self.assertFalse(policy["networkAccess"])

    def test_workspace_mode_never_uses_full_access(self):
        policy = codex_agent._codex_sandbox_policy(codex_agent.WORKSPACE_MODE, PROJECT_ROOT)
        self.assertNotEqual(policy["type"], "dangerFullAccess")
        self.assertEqual(policy["writableRoots"], [str(PROJECT_ROOT.resolve())])
        self.assertFalse(policy["networkAccess"])

    def test_approval_mode_keeps_interactive_workspace_approvals(self):
        self.assertEqual(
            codex_agent._codex_execution_settings("Pedir aprovação"),
            ("on-request", "workspace-write"),
        )

    def test_plan_mode_is_read_only_and_non_interactive(self):
        self.assertEqual(
            codex_agent._codex_execution_settings(codex_agent.READ_ONLY_MODE),
            ("never", "read-only"),
        )
        self.assertEqual(
            codex_agent._codex_sandbox_policy(codex_agent.READ_ONLY_MODE, PROJECT_ROOT),
            {"type": "readOnly", "networkAccess": False},
        )

    def test_workspace_guard_auto_accepts_safe_command_in_active_root(self):
        root = PROJECT_ROOT.resolve()
        emitted = []
        request = {
            "method": "item/commandExecution/requestApproval",
            "params": {
                "cwd": str(root),
                "command": "powershell.exe -Command Set-Content -LiteralPath smoke.txt -Value OK",
            },
        }
        result = codex_agent._approval_result(
            {}, request, threading.Event(), approval_context(root, emitted), workspace_auto=True
        )
        self.assertEqual(result, {"decision": "accept"})
        self.assertEqual(len(emitted), 1)
        self.assertTrue(emitted[0]["ok"])

    def test_workspace_guard_rejects_external_path_without_prompt(self):
        root = PROJECT_ROOT.resolve()
        outside = Path.home() / "Documents" / "outside-workspace"
        emitted = []
        request = {
            "method": "item/commandExecution/requestApproval",
            "params": {"cwd": str(outside), "command": "type secret.txt"},
        }
        result = codex_agent._approval_result(
            {}, request, threading.Event(), approval_context(root, emitted), workspace_auto=True
        )
        self.assertEqual(result, {"decision": "decline"})
        self.assertFalse(emitted[0]["ok"])

    def test_workspace_guard_rejects_network_and_dangerous_commands(self):
        root = PROJECT_ROOT.resolve()
        emitted = []
        ctx = approval_context(root, emitted)
        network = {
            "method": "item/commandExecution/requestApproval",
            "params": {
                "cwd": str(root), "command": "python -m http.server",
                "networkApprovalContext": {"host": "example.com"},
            },
        }
        dangerous = {
            "method": "item/commandExecution/requestApproval",
            "params": {"cwd": str(root), "command": "Remove-Item -Recurse smoke.txt"},
        }
        stop = threading.Event()
        self.assertEqual(
            codex_agent._approval_result({}, network, stop, ctx, workspace_auto=True),
            {"decision": "decline"},
        )
        self.assertEqual(
            codex_agent._approval_result({}, dangerous, stop, ctx, workspace_auto=True),
            {"decision": "decline"},
        )
        self.assertTrue(all(not item["ok"] for item in emitted))

    def test_local_visual_qa_runner_exists(self):
        runner = PROJECT_ROOT / ".agents" / "skills" / "jarvis-web-workflow" / "scripts" / "jarvis_web_qa.py"
        self.assertTrue(runner.is_file(), str(runner))

    def test_web_directive_uses_verified_local_playwright_helper(self):
        directive = codex_agent._web_workflow_directive()
        self.assertIn("jarvis_web_qa.py", directive)
        self.assertIn("--check", directive)
        self.assertIn("Não presuma que Puppeteer está instalado", directive)
        self.assertIn("helper Playwright", directive)

    def test_web_visual_review_does_not_stop_after_static_lint_findings(self):
        directive = codex_agent._web_workflow_directive()
        self.assertIn("não motivo para encerrar a tarefa", directive)
        self.assertIn("corrija o comando", directive)


if __name__ == "__main__":
    unittest.main()
