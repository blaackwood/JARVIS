import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import dev_agent
from actions.dev_agent import (
    _has_error, _install_dependencies, _project_python, _run_project, _safe_project_path,
)
from core.code_checks import detect_stack, resolve_project_command, run_tests


class DevAgentQualityTests(unittest.TestCase):
    def run_script(self, source, timeout=5):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'check.py'
            script.write_text(source, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                return _run_project('python check.py', Path(tmp), timeout=timeout)

    def test_nonzero_exit_is_not_reported_as_success(self):
        output = self.run_script('raise SystemExit(7)')
        self.assertIn('[JARVIS_EXIT_CODE: 7]', output)
        self.assertTrue(_has_error(output, 'python app.py'))

    def test_zero_exit_is_accepted(self):
        output = self.run_script('print(123)')
        self.assertIn('[JARVIS_EXIT_CODE: 0]', output)
        self.assertFalse(_has_error(output, 'python app.py'))

    def test_quoted_paths_with_spaces_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'script with spaces.py'
            script.write_text('print(456)', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                output = _run_project('python "script with spaces.py"', Path(tmp), timeout=5)
        self.assertIn('[JARVIS_EXIT_CODE: 0]', output)
        self.assertIn('456', output)

    def test_empty_output_is_not_assumed_successful(self):
        self.assertTrue(_has_error('', 'python app.py'))

    def test_timeout_is_not_reported_as_success(self):
        output = self.run_script('import time; time.sleep(2)', timeout=0.2)
        self.assertIn('[JARVIS_TIMEOUT]', output)
        self.assertTrue(_has_error(output, 'python app.py'))

    def test_path_traversal_and_absolute_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'
            root.mkdir()
            self.assertIsNone(_safe_project_path(root, '../outside.txt'))
            self.assertIsNone(_safe_project_path(root, 'C:/outside.txt'))
            self.assertIsNone(_safe_project_path(root, '/outside.txt'))

    def test_nested_relative_path_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'
            root.mkdir()
            result = _safe_project_path(root, 'src/main.py')
            self.assertEqual(result, (root / 'src' / 'main.py').resolve())

    def test_python_interpreter_is_project_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_python = root / '.venv' / 'Scripts' / 'python.exe'
            local_python.parent.mkdir(parents=True)
            local_python.write_bytes(b'')
            self.assertEqual(_project_python(root), str(local_python))

    def test_dependencies_install_into_the_project_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def create_env(env_dir):
                local_python = Path(env_dir) / 'Scripts' / 'python.exe'
                local_python.parent.mkdir(parents=True)
                local_python.write_bytes(b'test stub')
            with patch.object(dev_agent.venv, 'EnvBuilder') as builder, patch.object(dev_agent.subprocess, 'run') as run:
                builder.return_value.create.side_effect = create_env
                run.return_value.returncode = 0
                run.return_value.stderr = ''
                result = _install_dependencies(['requests>=2.31'], root)
            self.assertIn('Installed in isolated environment', result)
            self.assertIn(str(root / '.venv' / 'Scripts' / 'python.exe'), run.call_args.args[0][0])

    def test_invalid_dependency_specification_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def create_env(env_dir):
                local_python = Path(env_dir) / 'Scripts' / 'python.exe'
                local_python.parent.mkdir(parents=True)
                local_python.write_bytes(b'test stub')
            with patch.object(dev_agent.venv, 'EnvBuilder') as builder, patch.object(dev_agent.subprocess, 'run') as run:
                builder.return_value.create.side_effect = create_env
                result = _install_dependencies(['--index-url=https://evil.invalid'], root)
            self.assertIn('refused an invalid dependency', result)
            run.assert_not_called()

    def _build_smoke_project(self, root, name):
        plan = {
            'project_name': name,
            'entry_point': 'main.py',
            'run_command': 'python main.py',
            'dependencies': [],
            'files': [
                {'path': 'main.py', 'description': 'Application entry point', 'imports': []},
                {'path': 'test_main.py', 'description': 'Smoke test', 'imports': []},
            ],
        }
        sources = {
            'main.py': 'print("JARVIS_SMOKE_OK")\n',
            'test_main.py': (
                'import unittest\n\n'
                'class TestSmoke(unittest.TestCase):\n'
                '    def test_math(self):\n'
                '        self.assertEqual(2 + 2, 4)\n'
            ),
        }

        def writer(file_info, project_description, all_files, language, project_dir, already_written):
            rel = file_info['path']
            target = _safe_project_path(project_dir, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sources[rel], encoding='utf-8')
            return sources[rel]

        with patch.object(dev_agent, 'PROJECTS_DIR', root), \
             patch.object(dev_agent, '_plan_project', return_value=plan), \
             patch.object(dev_agent, '_write_file', side_effect=writer), \
             patch.object(dev_agent, '_open_vscode', return_value=False):
            with contextlib.redirect_stdout(io.StringIO()):
                return dev_agent._build_project('smoke test project', 'python', name, 5)

    def test_build_runs_syntax_tests_and_entry_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._build_smoke_project(Path(tmp), 'smoke_app')
        self.assertIn("Project 'smoke_app' is working", result)
        self.assertIn('Syntax validation passed', result)
        self.assertIn('completed successfully', result)
        self.assertIn('JARVIS_SMOKE_OK', result)

    def test_build_does_not_overwrite_existing_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'smoke_app'
            original.mkdir()
            marker = original / 'keep.txt'
            marker.write_text('preserve me', encoding='utf-8')
            result = self._build_smoke_project(root, 'smoke_app')
            self.assertIn("Project 'smoke_app_2' is working", result)
            self.assertEqual(marker.read_text(encoding='utf-8'), 'preserve me')
            self.assertTrue((root / 'smoke_app_2' / 'main.py').is_file())

    def test_build_rejects_path_traversal_from_planner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = {
                'project_name': 'unsafe', 'entry_point': '../outside.py',
                'run_command': 'python ../outside.py', 'dependencies': [],
                'files': [{'path': '../outside.py', 'description': 'escape', 'imports': []}],
            }
            with patch.object(dev_agent, 'PROJECTS_DIR', root), \
                 patch.object(dev_agent, '_plan_project', return_value=plan):
                result = dev_agent._build_project('unsafe project', 'python', 'unsafe', 5)
            self.assertIn('unsafe file path', result)
            self.assertFalse((root.parent / 'outside.py').exists())


    def test_node_builtin_tests_run_without_node_modules(self):
        if os.name != "nt":
            self.skipTest("Exercises the Windows npm.cmd launcher.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "node-builtin-test",
                "private": True,
                "type": "module",
                "scripts": {"test": "node --test"},
            }), encoding="utf-8")
            (root / "app.test.js").write_text(
                os.linesep.join([
                    "import test from 'node:test';",
                    "import assert from 'node:assert/strict';",
                    "test('built-in test runner works', () => {",
                    "  assert.equal(2 + 2, 4);",
                    "  console.log('PASS_NODE_BUILTIN');",
                    "});",
                ]) + os.linesep,
                encoding="utf-8",
            )

            stack = detect_stack(root)
            self.assertEqual(stack["test_name"], "npm test")
            self.assertTrue(stack["test_cmd"])
            self.assertFalse((root / "node_modules").exists())

            result = run_tests(root, stack)
            self.assertIsNotNone(result)
            self.assertTrue(result["ok"], result["output"])
            self.assertIn("PASS_NODE_BUILTIN", result["output"])

    def test_node_tests_with_missing_declared_dependencies_are_not_run(self):
        if os.name != "nt":
            self.skipTest("Exercises Windows Node stack detection.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "node-missing-deps",
                "private": True,
                "scripts": {"test": "vitest run"},
                "devDependencies": {"vitest": "^3.0.0"},
            }), encoding="utf-8")
            stack = detect_stack(root)
            self.assertIsNone(stack["test_cmd"])
            self.assertTrue(any("node_modules is missing" in note for note in stack["notes"]))

    def test_windows_npm_shim_resolves_to_node_without_cmd_shell(self):
        if os.name != "nt":
            self.skipTest("Exercises Windows Node CLI resolution.")
        resolved = resolve_project_command(["npm", "test", "--silent"])
        self.assertIsNotNone(resolved)
        self.assertEqual(Path(resolved[0]).name.lower(), "node.exe")
        self.assertEqual(Path(resolved[1]).name.lower(), "npm-cli.js")
        self.assertEqual(resolved[2:], ["test", "--silent"])

    def test_unknown_windows_batch_wrapper_is_refused(self):
        if os.name != "nt":
            self.skipTest("Exercises Windows command-wrapper policy.")
        with patch("core.code_checks.shutil.which", return_value=r"C:\\Tools\\unknown.cmd"):
            self.assertIsNone(resolve_project_command(["unknown", "run"]))

    def test_shell_metacharacters_remain_plain_node_cli_arguments(self):
        if os.name != "nt":
            self.skipTest("Exercises Windows Node CLI resolution.")
        argument = "test & echo SHOULD_NOT_RUN"
        resolved = resolve_project_command(["npm", argument])
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[2:], [argument])

    def test_build_run_command_supports_windows_npm_cmd_shim(self):
        if os.name != "nt":
            self.skipTest("Exercises the Windows npm.cmd launcher.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "name": "npm-shim-smoke",
                "private": True,
                "scripts": {"test": "node -p 40+2"},
            }), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                output = _run_project("npm test", root, timeout=20)
            self.assertIn("[JARVIS_EXIT_CODE: 0]", output)
            self.assertIn("42", output)
            self.assertFalse(_has_error(output, "npm test"))


if __name__ == '__main__':
    unittest.main()
