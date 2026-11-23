from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerAutostartTests(unittest.TestCase):
    def test_installer_does_not_enable_microphone_or_auto_start_by_default(self):
        scripts = [ROOT / "installer.iss", ROOT / "installer_build" / "installer.iss"]
        for script in scripts:
            with self.subTest(script=str(script)):
                text = script.read_text(encoding="utf-8-sig")
                self.assertNotIn("[Registry]", text)
                self.assertNotIn('ValueName: "JARVIS_AI"', text)
                self.assertNotIn("JARVIS-Wake.exe", text)

    def test_auto_start_remains_an_explicit_in_app_choice(self):
        text = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _toggle_autostart(self)", text)
        self.assertIn('winreg.SetValueEx(reg, "JARVIS_AI"', text)
        self.assertIn('winreg.DeleteValue(reg, "JARVIS_AI")', text)
        self.assertIn('"JARVIS-Wake.exe"', text)

    def test_build_script_creates_a_python313_environment_and_installs_dependencies(self):
        text = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("py -3.13 -m venv", text)
        self.assertIn("pip install -r requirements.txt pyinstaller", text)
        self.assertIn("--collect-submodules core", text)
        self.assertIn('--add-data "$P\\.agents;.agents"', text)
        self.assertIn("Get-FileHash $BuiltSetup -Algorithm SHA256", text)

    def test_build_script_preserves_source_installer_and_compiles_setup(self):
        text = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        self.assertNotIn("Remove-Item $B -Recurse -Force", text)
        self.assertIn('$ISCC = Join-Path $env:LOCALAPPDATA "Programs\\Inno Setup 6\\ISCC.exe"', text)
        self.assertIn("& $ISCC /Qp $InstallerScript", text)
        self.assertNotIn("Copy-Item $BuiltSetup $DesktopSetup", text)

    def test_builder_bundles_only_headless_shell_and_its_license(self):
        build = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("playwright install --only-shell chromium", build)
        self.assertIn("$HeadlessBrowser.FullName $BundledBrowserDir", build)
        self.assertIn('Filter "LICENSE.headless_shell"', build)
        self.assertIn("PYINSTALLER-COPYING.txt", build)
        self.assertIn("PYINSTALLER-HOOKS-CONTRIB-LICENSE.txt", build)
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('Path(_sys.executable).resolve().parent / "ms-playwright"', main)
        self.assertIn('os.environ["PLAYWRIGHT_BROWSERS_PATH"]', main)

    def test_builder_installs_a_fresh_headless_browser_matching_playwright(self):
        build = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('Remove-Item $BrowserStore -Recurse -Force', build)
        self.assertIn("playwright install --only-shell chromium", build)
        self.assertIn('Get-ChildItem $BrowserStore -Directory -Filter "chromium_headless_shell-*"', build)
        self.assertNotIn('Copy-Item $BrowserStore (Join-Path $Out "ms-playwright")', build)

    def test_native_autostart_uses_hidden_wscript_launcher(self):
        text = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        launcher = (ROOT / "wake_native" / "launch_hidden.vbs").read_text(encoding="utf-8")
        self.assertIn("launch_hidden.vbs", text)
        self.assertIn("wscript.exe", text)
        self.assertIn("//B //NoLogo", text)
        self.assertIn("shell.Run command, 0, False", launcher)
        self.assertIn("JarvisWakeNative.exe", launcher)
        self.assertNotIn("command = f'\"{native_daemon}\" --daemon", text)

    def test_healthcheck_detects_direct_console_startup_as_warning(self):
        text = (ROOT / "core" / "healthcheck.py").read_text(encoding="utf-8")
        self.assertIn("launch_hidden.vbs", text)
        self.assertIn("pode abrir terminal", text)

    def test_background_worker_is_built_without_a_console(self):
        build = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        spec = (ROOT / "installer_build" / "JARVIS-Tasks.spec").read_text(encoding="utf-8")
        worker = (ROOT / "task_worker.py").read_text(encoding="utf-8")
        self.assertIn("--onefile --windowed --name JARVIS-Tasks", build)
        self.assertIn("console=False", spec)
        self.assertIn("install_no_console_policy()", worker)

    def test_wake_daemon_uses_the_same_hidden_process_policy(self):
        worker = (ROOT / "wake_daemon.py").read_text(encoding="utf-8")
        self.assertIn("install_no_console_policy()", worker)
        source = (ROOT / "wake_native" / "src" / "wake_daemon.cpp").read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", source)


if ( __name__ == "__main__"):
    unittest.main()
