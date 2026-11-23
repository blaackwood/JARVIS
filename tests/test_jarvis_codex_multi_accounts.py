import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "_jarvis_agent_ui"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

spec = importlib.util.spec_from_file_location("jarvis_codex_accounts_test_server", AGENT_DIR / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
import codex_runtime
import codex_agent


class CodexMultiAccountTests(unittest.TestCase):
    def setUp(self):
        server.CODEX_USAGE_CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.accounts = self.root / "codex_accounts"
        self.registry = self.accounts / "accounts.json"
        self.primary = self.root / "primary_home"
        self.primary.mkdir()
        (self.primary / "auth.json").write_text("{}", encoding="utf-8")
        self.patches = [
            patch.object(server, "CODEX_ACCOUNT_DIR", self.accounts),
            patch.object(server, "CODEX_ACCOUNT_REGISTRY", self.registry),
            patch.object(server, "CODEX_PRIMARY_HOME", self.primary),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_primary_profile_uses_existing_codex_home(self):
        self.assertEqual(server._codex_account_home("primary"), self.primary.resolve())
        self.assertTrue(server._codex_accounts_public()[0]["authenticated"])

    def test_invalid_or_unregistered_account_ids_rejected(self):
        for value in ("../escape", "acct_short", "acct_aaaaaaaaaaaa"):
            with self.assertRaises(ValueError):
                server._codex_account_home(value)

    def test_account_profile_is_isolated_and_status_detects_auth(self):
        self.accounts.mkdir()
        profile_id = "acct_123456abcdef"
        home = self.accounts / "profiles" / profile_id
        home.mkdir(parents=True)
        (home / "auth.json").write_text("{}", encoding="utf-8")
        self.registry.write_text(json.dumps({profile_id: {"label": "Reserva", "created": 1}}), encoding="utf-8")
        self.assertEqual(server._codex_account_home(profile_id), home.resolve())
        self.assertTrue(server._codex_accounts_public()[-1]["authenticated"])

    def test_add_account_creates_isolated_file_auth_and_starts_login(self):
        captured = {}
        with patch.object(server, "find_codex_command", return_value=r"C:\Codex\codex.cmd"), patch.object(server.subprocess, "Popen", side_effect=lambda *a, **kw: captured.update(args=a, kwargs=kw)):

            status, result = server.api_codex_add_account({}, {"label": "Reserva"})
        self.assertEqual(status, 200)
        profile_id = result["account"]["id"]
        home = self.accounts / "profiles" / profile_id
        self.assertTrue((home / "config.toml").is_file())
        self.assertIn('cli_auth_credentials_store = "file"', (home / "config.toml").read_text(encoding="utf-8"))
        self.assertIn(str(home), " ".join(captured["args"][0]))
        self.assertIn(profile_id, server._codex_accounts_load())

    def test_rename_account_updates_registry_label(self):
        self.accounts.mkdir()
        profile_id = "acct_123456abcdef"
        (self.accounts / "profiles" / profile_id).mkdir(parents=True)
        self.registry.write_text(json.dumps({profile_id: {"label": "Old", "created": 1}}), encoding="utf-8")
        status, result = server.api_codex_rename_account({}, {"id": profile_id, "label": "Second"})
        self.assertEqual(status, 200)
        self.assertEqual(server._codex_accounts_load()[profile_id]["label"], "Second")


    def test_task_history_is_listed_independently_of_selected_codex_account(self):
        first = {"id": "1111111111", "title": "Conta principal", "created": 1, "updated": 1,
                 "messages": [], "events": [], "codex_threads": {"primary": "thread-a"}}
        second = {"id": "2222222222", "title": "Outra conta", "created": 2, "updated": 2,
                  "messages": [], "events": [], "codex_threads": {"acct_123456abcdef": "thread-b"}}
        old_tasks = server.TASKS
        try:
            server.TASKS = {first["id"]: first, second["id"]: second}
            with patch.object(server, "prov_list", return_value=([], "")), \
                 patch.object(server, "git", return_value=(1, "")), \
                 patch.object(server, "_codex_accounts_public", return_value=[]):
                status, payload = server.api_state({}, {})
            self.assertEqual(status, 200)
            self.assertEqual({item["id"] for item in payload["tasks"]}, {first["id"], second["id"]})
        finally:
            server.TASKS = old_tasks

    def test_conversation_fingerprint_changes_after_another_account_adds_turns(self):
        original = [
            {"role": "user", "content": "Pergunta da conta principal"},
            {"role": "assistant", "content": "Resposta da conta principal"},
        ]
        updated = original + [
            {"role": "user", "content": "Continua??o pela segunda conta"},
            {"role": "assistant", "content": "Resposta da segunda conta"},
        ]
        self.assertEqual(codex_agent._messages_fingerprint(original), codex_agent._messages_fingerprint(list(original)))
        self.assertNotEqual(codex_agent._messages_fingerprint(original), codex_agent._messages_fingerprint(updated))

    def test_codex_app_server_receives_account_home_env(self):
        class FakePipe:
            def close(self):
                pass
        class FakeProc:
            stdin = FakePipe()
            stdout = iter([])
            pid = 1
            returncode = 0
            def poll(self):
                return None
            def wait(self, timeout=None):
                return 0
            def terminate(self):
                pass
            def kill(self):
                pass
        captured = {}
        with patch.object(codex_runtime, "find_codex_command", return_value=r"C:\Codex\codex.cmd"), patch.object(codex_runtime.subprocess, "Popen", side_effect=lambda *a, **kw: captured.update(args=a, kwargs=kw) or FakeProc()):

            client = codex_runtime.CodexAppServer(self.root, codex_home=self.root / "profile")
            client.close()
        self.assertEqual(captured["kwargs"]["env"]["CODEX_HOME"], str((self.root / "profile").resolve()))


    def test_codex_usage_window_formats_official_limit_fields(self):
        window = server._codex_usage_window("primary", {
            "usedPercent": 98,
            "windowDurationMins": 43200,
            "resetsAt": 1795830906,
        })
        self.assertEqual(window["used_percent"], 98)
        self.assertEqual(window["period"], "30 dias")
        self.assertEqual(window["resets_at"], 1795830906)
        self.assertEqual(window["label"], "Principal")

    def test_codex_usage_window_ignores_missing_or_invalid_percentages(self):
        self.assertIsNone(server._codex_usage_window("primary", None))
        self.assertIsNone(server._codex_usage_window("primary", {"usedPercent": 140}))
        self.assertIsNone(server._codex_usage_window("primary", {"usedPercent": "not-a-number"}))

    def test_codex_usage_fetch_uses_selected_profile_and_exposes_only_quota_data(self):
        captured = {}
        class FakeCodex:
            def __init__(self, cwd, codex_home=None):
                captured["cwd"] = cwd
                captured["home"] = codex_home
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def request(self, method, params=None, timeout=0):
                if method == "account/read":
                    return {"account": {"type": "chatgpt", "planType": "plus", "email": "private@example.com"}}
                if method == "account/rateLimits/read":
                    return {"rateLimits": {
                        "primary": {"usedPercent": 42, "windowDurationMins": 300, "resetsAt": 2000000000},
                        "secondary": {"usedPercent": 67, "windowDurationMins": 10080, "resetsAt": 2000000001},
                    }}
                if method == "initialize":
                    return {}
                raise AssertionError("unexpected Codex method: " + method)
            def notify(self, method, params=None):
                captured["initialized"] = method

        profile_id = "acct_123456abcdef"
        self.accounts.mkdir()
        home = self.accounts / "profiles" / profile_id
        home.mkdir(parents=True)
        (home / "auth.json").write_text("{}", encoding="utf-8")
        self.registry.write_text(json.dumps({profile_id: {"label": "Reserva", "created": 1}}), encoding="utf-8")
        with patch.object(server, "CodexAppServer", FakeCodex):
            server._codex_usage_fetch(profile_id)

        snapshot = server.codex_usage_snapshot(profile_id)
        self.assertEqual(captured["home"], home.resolve())
        self.assertEqual(captured["initialized"], "initialized")
        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(snapshot["plan_type"], "plus")
        self.assertEqual([w["used_percent"] for w in snapshot["windows"]], [42, 67])
        serialized = json.dumps(snapshot)
        self.assertNotIn("private@example.com", serialized)
        self.assertNotIn("auth", serialized)

    def test_codex_usage_fetch_marks_unlogged_accounts_without_starting_app_server(self):
        self.accounts.mkdir()
        profile_id = "acct_123456abcdef"
        (self.accounts / "profiles" / profile_id).mkdir(parents=True)
        self.registry.write_text(json.dumps({profile_id: {"label": "Pendente", "created": 1}}), encoding="utf-8")
        with patch.object(server, "CodexAppServer") as app_server:
            server._codex_usage_fetch(profile_id)
        app_server.assert_not_called()
        self.assertEqual(server.codex_usage_snapshot(profile_id)["status"], "not_connected")


if __name__ == "__main__":
    unittest.main()
