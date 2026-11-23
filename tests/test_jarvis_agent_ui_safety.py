import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "_jarvis_agent_ui" / "server.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("jarvis_agent_ui_server_under_test", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class JarvisAgentUISafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.data = self.base / "data"
        self.data.mkdir()
        self.approvals = self.data / "approvals"
        self.approvals.mkdir()

        self.originals = {
            "DATA": server.DATA,
            "APPROVAL_DIR": server.APPROVAL_DIR,
            "_ALWAYS_FILE": server._ALWAYS_FILE,
            "ACCESS_ROOTS": server.ACCESS_ROOTS,
            "ws": server.STATE["ws"],
            "term": server.STATE["term"],
            "tasks": dict(server.TASKS),
            "runs": dict(server.RUNS),
            "asks": dict(server.ASKS),
        }
        server.DATA = self.data
        server.APPROVAL_DIR = self.approvals
        server._ALWAYS_FILE = self.data / "always_allow.json"
        server.ACCESS_ROOTS = [self.base.resolve()]
        server.STATE["ws"] = self.workspace
        server.STATE["term"] = self.workspace
        server.TASKS.clear()
        server.RUNS.clear()
        server.ASKS.clear()

        self.task = {
            "id": "safety001",
            "title": "Safety test",
            "created": 1,
            "updated": 1,
            "messages": [],
            "events": [],
            "todos": [],
            "changes": {},
            "procs": [],
            "allow": [],
            "running": False,
            "awaiting": False,
            "last": "",
        }
        server.TASKS[self.task["id"]] = self.task
        self.stop = __import__("threading").Event()

    def tearDown(self):
        server.DATA = self.originals["DATA"]
        server.APPROVAL_DIR = self.originals["APPROVAL_DIR"]
        server._ALWAYS_FILE = self.originals["_ALWAYS_FILE"]
        server.ACCESS_ROOTS = self.originals["ACCESS_ROOTS"]
        server.STATE["ws"] = self.originals["ws"]
        server.STATE["term"] = self.originals["term"]
        server.TASKS.clear()
        server.TASKS.update(self.originals["tasks"])
        server.RUNS.clear()
        server.RUNS.update(self.originals["runs"])
        server.ASKS.clear()
        server.ASKS.update(self.originals["asks"])
        self.temp.cleanup()

    def write_tool(self, name, content):
        return server.tool_write(
            self.task,
            {"path": name, "content": content},
            "Pedir aprovação",
            self.stop,
        )

    def test_restart_marks_interrupted_task_and_cancels_orphaned_approval(self):
        task_id = "cafe123456"
        approval_id = "deadbeef"
        interrupted = dict(self.task)
        interrupted.update({
            "id": task_id,
            "running": True,
            "awaiting": True,
            "messages": [
                {"role": "user", "content": "edit the file"},
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "tool-before-crash", "type": "function",
                    "function": {"name": "edit_file", "arguments": "{}"},
                }]},
            ],
            "events": [{"t": "ask", "id": approval_id, "title": "edit file"}],
        })
        (self.data / ("task_%s.json" % task_id)).write_text(
            json.dumps(interrupted, ensure_ascii=False), encoding="utf-8"
        )
        approval = {
            "id": approval_id, "task_id": task_id, "created_at": 1,
            "expires_at": 9999999999, "status": "pending", "choice": 3, "note": "",
        }
        self.assertTrue(server.save_approval_state(approval_id, approval))
        server.TASKS.clear()

        server.load_all()

        recovered = server.TASKS[task_id]
        self.assertFalse(recovered["running"])
        self.assertFalse(recovered["awaiting"])
        self.assertIn("interrompida", recovered["last"].lower())
        tool_result = next(m for m in recovered["messages"] if m.get("tool_call_id") == "tool-before-crash")
        self.assertIn("OUTCOME UNKNOWN", tool_result["content"])
        state = server.load_approval_state(approval_id)
        self.assertEqual(state["status"], "cancelled")
        self.assertTrue(any(e.get("t") == "asked" and e.get("id") == approval_id for e in recovered["events"]))
        self.assertTrue(any(e.get("t") == "error" for e in recovered["events"]))

        persisted = json.loads((self.data / ("task_%s.json" % task_id)).read_text("utf-8"))
        self.assertFalse(persisted["running"])
        self.assertTrue(any(m.get("tool_call_id") == "tool-before-crash" for m in persisted["messages"]))

        event_count = len(recovered["events"])
        server.load_all()
        self.assertEqual(len(server.TASKS[task_id]["events"]), event_count)

    def test_new_task_is_not_exposed_when_initial_checkpoint_fails(self):
        before = set(server.TASKS)
        with patch.object(server, "save", return_value=False):
            with self.assertRaises(OSError):
                server.new_task("must not exist")
        self.assertEqual(set(server.TASKS), before)

    def test_api_send_persists_user_event_before_starting_worker(self):
        instance = None

        def worker_started():
            stored = json.loads((self.data / "task_safety001.json").read_text("utf-8"))
            self.assertTrue(stored["running"])
            self.assertEqual(stored["events"][-1]["t"], "user")
            self.assertEqual(stored["events"][-1]["text"], "continue the task")

        with patch.object(server.threading, "Thread") as thread_factory:
            instance = thread_factory.return_value
            instance.start.side_effect = worker_started
            status, result = server.api_send({}, {
                "id": self.task["id"], "text": "continue the task",
                "mode": "Pedir aprovação", "atts": [],
            })
        self.assertEqual(status, 200, result)
        thread_factory.assert_called_once()
        instance.start.assert_called_once()

    def test_api_send_does_not_start_worker_when_user_event_checkpoint_fails(self):
        original_title = self.task["title"]
        original_updated = self.task["updated"]
        with patch.object(server, "save", return_value=False), \
             patch.object(server.threading, "Thread") as thread_factory:
            status, result = server.api_send({}, {
                "id": self.task["id"], "text": "must be saved first",
                "mode": "Pedir aprovação", "atts": [],
            })
        self.assertEqual(status, 500)
        self.assertIn("Nenhum modelo ou ferramenta", result["error"])
        self.assertFalse(self.task["running"])
        self.assertEqual(self.task["title"], original_title)
        self.assertEqual(self.task["updated"], original_updated)
        self.assertEqual(self.task["events"], [])
        thread_factory.assert_not_called()

    def test_agent_persists_user_message_before_calling_model(self):
        checkpoints = []

        def checkpoint(task):
            checkpoints.append(json.loads(json.dumps(task, ensure_ascii=False)))
            return True

        def model_turn(task, state, mode, stop):
            self.assertTrue(checkpoints)
            self.assertEqual(checkpoints[0]["messages"][0]["role"], "user")
            self.assertEqual(checkpoints[0]["messages"][0]["content"], "hello agent")
            return "hello back", []

        with patch.object(server, "fallback_chain", return_value=["provider"]), \
             patch.object(server, "resolve", return_value=("provider", "http://local", "model", "")), \
             patch.object(server, "_selected_skill_context", return_value=""), \
             patch.object(server, "save", side_effect=checkpoint), \
             patch.object(server, "stream_chain", side_effect=model_turn):
            server.agent(self.task, "hello agent", "Pedir aprovação", None, [])
        self.assertGreaterEqual(len(checkpoints), 2)
        self.assertEqual(self.task["last"], "hello back")

    def test_agent_never_dispatches_tool_call_when_assistant_checkpoint_fails(self):
        checkpoints = []

        def checkpoint(task):
            checkpoints.append(json.loads(json.dumps(task, ensure_ascii=False)))
            return len(checkpoints) != 2

        call = {"id": "call-safety", "name": "read_file",
                "args": json.dumps({"path": "sample.txt"})}
        dispatched = []

        def model_turn(task, state, mode, stop):
            return "", [call]

        original_tool = server.TOOLS["read_file"]

        def fake_tool(*args):
            dispatched.append(args)
            return True, "read", {}

        server.TOOLS["read_file"] = fake_tool
        try:
            with patch.object(server, "fallback_chain", return_value=["provider"]), \
                 patch.object(server, "resolve", return_value=("provider", "http://local", "model", "")), \
                 patch.object(server, "_selected_skill_context", return_value=""), \
                 patch.object(server, "save", side_effect=checkpoint), \
                 patch.object(server, "stream_chain", side_effect=model_turn):
                server.agent(self.task, "read sample.txt", "Pedir aprovação", None, [])
        finally:
            server.TOOLS["read_file"] = original_tool
        self.assertEqual(len(checkpoints), 3)
        self.assertEqual(checkpoints[1]["messages"][-1].get("tool_calls", [])[0]["id"], "call-safety")
        self.assertEqual(dispatched, [])
        self.assertTrue(any(e.get("t") == "error" for e in self.task["events"]))

    def test_empty_successful_llm_stream_is_a_provider_failure_and_is_closed(self):
        class EmptyResponse:
            status_code = 200
            closed = False

            def iter_lines(self):
                return iter([b"data: [DONE]"])

            def close(self):
                self.closed = True

        response = EmptyResponse()
        with patch.object(server, "SYSTEM", "test system"), \
             patch.object(server, "api_history", return_value=[]), \
             patch.object(server, "_post_cancelable", return_value=response), \
             patch.object(server, "_watch_stop"):
            with self.assertRaisesRegex(server.LLMFail, "sem conteúdo"):
                server.stream_llm(
                    self.task, "http://local", "model", "", "Pedir aprovação",
                    self.stop, provider_id="test-provider",
                )
        self.assertTrue(response.closed)

    def test_empty_stream_failure_triggers_fallback_provider(self):
        state = {"chain": ["provider-first", "provider-fallback"], "i": 0, "cfg": None}
        resolutions = [
            ("provider-first", "http://first", "model-first", ""),
            ("provider-fallback", "http://fallback", "model-fallback", ""),
        ]
        with patch.object(server, "resolve", side_effect=resolutions), \
             patch.object(server, "stream_llm",
                          side_effect=[server.LLMFail("empty stream"),
                                       ("fallback answer", [])]) as stream, \
             patch.object(server, "emit"):
            result = server.stream_chain(self.task, state, "Pedir aprovação", self.stop)
        self.assertEqual(result, ("fallback answer", []))
        self.assertEqual(state["i"], 1)
        self.assertEqual(stream.call_args.kwargs["provider_id"], "provider-fallback")

    def test_todo_plan_is_not_changed_when_checkpoint_fails(self):
        self.task["todos"] = [{"text": "existing", "status": "pending"}]
        before = list(self.task["todos"])
        with patch.object(server, "save", return_value=False):
            ok, message, extra = server.tool_todo(
                self.task,
                {"items": [{"text": "new step", "status": "in_progress"}]},
                "Pedir aprovação", self.stop,
            )
        self.assertFalse(ok)
        self.assertIn("salvar o plano", message)
        self.assertEqual(extra["detail"], "checkpoint do plano falhou")
        self.assertEqual(self.task["todos"], before)
        self.assertEqual(self.task["events"], [])

    def test_atomic_write_leaves_complete_file_and_no_temp_file(self):
        target = self.workspace / "atomic.txt"
        self.assertTrue(server._atomic_write_bytes(target, b"complete payload"))
        self.assertEqual(target.read_bytes(), b"complete payload")
        self.assertEqual(list(self.workspace.glob("atomic.txt.*.tmp")), [])

    def test_failed_task_checkpoint_preserves_previous_journal(self):
        self.assertTrue(server.save(self.task))
        journal = self.data / "task_safety001.json"
        before = journal.read_bytes()
        self.task["title"] = "new state"
        with patch.object(server.os, "replace", side_effect=OSError("simulated disk failure")):
            self.assertFalse(server.save(self.task))
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(list(self.data.glob("task_safety001.json.*.tmp")), [])

    def test_write_persists_original_snapshot_and_expected_hash_before_finish(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            ok, _, _ = self.write_tool("sample.txt", "updated")
        self.assertTrue(ok)
        self.assertEqual(target.read_text(encoding="utf-8"), "updated")
        record = self.task["changes"][str(target)]
        self.assertEqual(record["orig"], "original")
        self.assertEqual(record["last_hash"], server._disk_hash(target))
        stored = json.loads((self.data / "task_safety001.json").read_text("utf-8"))
        self.assertEqual(stored["changes"][str(target)]["orig"], "original")
        self.assertEqual(stored["changes"][str(target)]["last_hash"], server._disk_hash(target))

    def test_write_does_not_touch_file_when_checkpoint_cannot_be_saved(self):
        target = self.workspace / "sample.txt"
        target.write_text("keep me", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")), \
             patch.object(server, "_atomic_write_bytes", return_value=False):
            ok, message, _ = self.write_tool("sample.txt", "do not write")
        self.assertFalse(ok)
        self.assertIn("ponto de restauração", message)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")

    def test_failed_atomic_source_write_rolls_back_task_snapshot(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")), \
             patch.object(server, "wr", side_effect=OSError("simulated replace failure")):
            ok, message, _ = self.write_tool("sample.txt", "updated")
        self.assertFalse(ok)
        self.assertIn("simulated replace failure", message)
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        self.assertNotIn(str(target), self.task["changes"])
        stored = json.loads((self.data / "task_safety001.json").read_text("utf-8"))
        self.assertNotIn(str(target), stored["changes"])

    def test_stop_after_approval_prevents_write(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")

        def approve_and_stop(*args, **kwargs):
            self.stop.set()
            return True, ""

        with patch.object(server, "approve", side_effect=approve_and_stop):
            ok, message, extra = self.write_tool("sample.txt", "should not apply")
        self.assertFalse(ok)
        self.assertEqual(extra.get("detail"), "interrompido")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        self.assertNotIn(str(target), self.task["changes"])

    def test_failed_second_checkpoint_preserves_previous_expected_hash(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("sample.txt", "first edit")[0])
        expected = self.task["changes"][str(target)]["last_hash"]
        with patch.object(server, "approve", return_value=(True, "")), \
             patch.object(server, "_atomic_write_bytes", return_value=False):
            ok, _, _ = self.write_tool("sample.txt", "second edit")
        self.assertFalse(ok)
        self.assertEqual(target.read_text(encoding="utf-8"), "first edit")
        self.assertEqual(self.task["changes"][str(target)]["last_hash"], expected)
        self.assertFalse(server.changes(self.task)[0]["conflict"])

    def test_write_aborts_when_file_changes_while_approval_is_pending(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")

        def approval_then_user_edit(*args, **kwargs):
            target.write_text("user's newer edit", encoding="utf-8")
            return True, ""

        with patch.object(server, "approve", side_effect=approval_then_user_edit):
            ok, message, extra = self.write_tool("sample.txt", "agent's stale edit")
        self.assertFalse(ok)
        self.assertEqual(extra.get("detail"), "conflito externo")
        self.assertIn("mudou enquanto aguardava", message)
        self.assertEqual(target.read_text(encoding="utf-8"), "user's newer edit")
        self.assertNotIn(str(target), self.task["changes"])

    def test_external_change_is_reported_as_conflict(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("sample.txt", "agent edit")[0])
        target.write_text("manual user edit", encoding="utf-8")
        changed = server.changes(self.task)
        self.assertEqual(len(changed), 1)
        self.assertTrue(changed[0]["conflict"])
        self.assertIn("fora do JARVIS", changed[0]["conflict_reason"])

    def test_revert_refuses_to_overwrite_external_changes(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("sample.txt", "agent edit")[0])
        target.write_text("manual user edit", encoding="utf-8")
        status, result = server.api_revert({}, {"id": self.task["id"]})
        self.assertEqual(status, 409)
        self.assertIn("Reversão bloqueada", result["error"])
        self.assertEqual(target.read_text(encoding="utf-8"), "manual user edit")

    def test_revert_restores_file_when_agent_change_is_unchanged(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("sample.txt", "agent edit")[0])
        status, result = server.api_revert({}, {"id": self.task["id"]})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        self.assertEqual(self.task["changes"], {})

    def test_legacy_snapshot_without_hash_is_not_reverted(self):
        target = self.workspace / "old.txt"
        target.write_text("current content", encoding="utf-8")
        self.task["changes"][str(target)] = {"orig": "old content", "crlf": False}
        changed = server.changes(self.task)
        self.assertTrue(changed[0]["conflict"])
        status, result = server.api_revert({}, {"id": self.task["id"]})
        self.assertEqual(status, 409)
        self.assertEqual(target.read_text(encoding="utf-8"), "current content")

    def test_commit_refuses_conflicting_file_before_git_stage(self):
        target = self.workspace / "sample.txt"
        target.write_text("original", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("sample.txt", "agent edit")[0])
        target.write_text("manual user edit", encoding="utf-8")
        with patch.object(server, "git") as git:
            status, result = server.api_commit({}, {"id": self.task["id"]})
        self.assertEqual(status, 409)
        self.assertIn("Commit bloqueado", result["error"])
        git.assert_not_called()

    def test_commit_refuses_preexisting_unstaged_user_changes(self):
        target = self.workspace / "sample.txt"
        target.write_text("user's preexisting work", encoding="utf-8")
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("sample.txt", "agent update")[0])

        def fake_git(*args, **kwargs):
            if args[:1] == ("ls-files",):
                return 0, "sample.txt"
            if args[:1] == ("show",):
                return 0, "clean HEAD version"
            self.fail("Git add/commit must not run when baseline contains user work")

        with patch.object(server, "git", side_effect=fake_git) as git:
            status, result = server.api_commit({}, {"id": self.task["id"]})
        self.assertEqual(status, 409)
        self.assertIn("já tinha alterações antes", result["error"])
        self.assertFalse(any(call.args and call.args[0] == "add" for call in git.call_args_list))

    def test_commit_can_commit_a_clean_new_file_using_git(self):
        with patch.object(server, "approve", return_value=(True, "")):
            self.assertTrue(self.write_tool("new.py", "print('agent')\n")[0])

        def fake_git(*args, **kwargs):
            if args[:1] == ("ls-files",):
                return 1, "not tracked yet"
            if args[:2] == ("diff", "--cached"):
                return 0, ""
            if args[:1] in (("add",), ("commit",)):
                return 0, "committed"
            self.fail("unexpected Git command: %r" % (args,))

        with patch.object(server, "git", side_effect=fake_git) as git:
            status, result = server.api_commit({}, {"id": self.task["id"]})
        self.assertEqual(status, 200)
        self.assertTrue(result["checkpoint_saved"])
        self.assertEqual(self.task["changes"], {})
        self.assertTrue(any(call.args[:1] == ("add",) for call in git.call_args_list))
        self.assertTrue(any(call.args[:1] == ("commit",) for call in git.call_args_list))

    def test_browser_audit_is_listed_as_a_callable_model_tool(self):
        names = {
            item["function"]["name"]
            for item in server.TOOL_DEFS
        }
        self.assertIn("browser_audit", names)
        self.assertIn("browser_audit", server.TOOLS)

    def test_browser_audit_requires_approval_before_running(self):
        with patch.object(server, "approve", return_value=(False, "user declined")), \
             patch("core.browser_qa.audit_web_project") as audit:
            ok, message, extra = server.tool_browser_audit(
                self.task, {"path": str(self.workspace)}, "Pedir aprovação", self.stop
            )
        self.assertFalse(ok)
        self.assertEqual(message, "user declined")
        self.assertEqual(extra.get("detail"), "auditoria não autorizada")
        audit.assert_not_called()

    def test_browser_audit_returns_verified_quality_gate_report(self):
        fake = {
            "supported": True,
            "ok": True,
            "framework": "static",
            "summary": {"passed": 9, "failed": 0, "warnings": 1, "total": 10},
            "diagnostics": [],
            "warnings": ["Visual model unavailable"],
            "evidence_dir": str(self.data / "evidence"),
            "screenshots": [],
            "visual_review": {"available": False, "issues": [], "note": "provider offline"},
        }
        with patch.object(server, "approve", return_value=(True, "")), \
             patch("core.browser_qa.audit_web_project", return_value=fake) as audit:
            ok, message, extra = server.tool_browser_audit(
                self.task, {"path": str(self.workspace), "visual_review": False},
                "Pedir aprovação", self.stop
            )
        self.assertTrue(ok)
        self.assertIn("9 verificações aprovadas", message)
        self.assertEqual(extra["audit_summary"]["summary"]["passed"], 9)
        audit.assert_called_once()

    def test_browser_audit_runs_real_playwright_for_a_supported_static_project(self):
        project = self.workspace / "web-project"
        project.mkdir()
        (project / "index.html").write_text(
            "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<title>Teste local</title></head><body><main><h1>JARVIS QA</h1>"
            "<button type='button'>Ação de teste</button></main></body></html>",
            encoding="utf-8",
        )
        with patch.object(server, "approve", return_value=(True, "")):
            ok, message, extra = server.tool_browser_audit(
                self.task, {"path": str(project), "visual_review": False},
                "Pedir aprovação", self.stop
            )
        self.assertTrue(ok, message)
        report = extra["audit_summary"]
        self.assertGreaterEqual(report["summary"]["passed"], 8)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(len(report["screenshots"]), 2)
        self.assertTrue((Path(report["evidence_dir"]) / "report.json").is_file())

    def test_browser_audit_fails_closed_when_project_type_is_unsupported(self):
        fake = {"supported": False, "ok": True, "reason": "no recognized entry point"}
        with patch.object(server, "approve", return_value=(True, "")), \
             patch("core.browser_qa.audit_web_project", return_value=fake):
            ok, message, extra = server.tool_browser_audit(
                self.task, {"path": str(self.workspace)}, "Pedir aprovação", self.stop
            )
        self.assertFalse(ok)
        self.assertIn("não foi possível auditar", message.lower())
        self.assertEqual(extra["detail"], "projeto não suportado")


if __name__ == "__main__":
    unittest.main()
