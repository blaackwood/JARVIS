from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerAutostartTests(unittest.TestCase):
    def test_both_inno_scripts_register_windows_startup(self):
        scripts = [
            ROOT / "installer.iss",
            ROOT / "installer_build" / "installer.iss",
        ]
        for script in scripts:
            with self.subTest(script=str(script)):
                text = script.read_text(encoding="utf-8")
                self.assertIn("[Registry]", text)
                self.assertIn('Root: HKCU; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Run"', text)
                self.assertIn('ValueName: "JARVIS_AI"', text)
                self.assertIn('ValueData: """{app}\\JARVIS-Wake.exe"""', text)
                self.assertIn("Flags: uninsdeletevalue", text)

    def test_startup_entry_is_removed_on_uninstall(self):
        for script in (ROOT / "installer.iss", ROOT / "installer_build" / "installer.iss"):
            with self.subTest(script=str(script)):
                text = script.read_text(encoding="utf-8")
                line = next(line for line in text.splitlines() if 'ValueName: "JARVIS_AI"' in line)
                self.assertIn("uninsdeletevalue", line)

    def test_build_script_preserves_installer_script_and_compiles_setup(self):
        text = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        self.assertNotIn("Remove-Item $B -Recurse -Force", text)
        self.assertIn('$ISCC = Join-Path $env:LOCALAPPDATA "Programs\\Inno Setup 6\\ISCC.exe"', text)
        self.assertIn("& $ISCC /Qp $InstallerScript", text)
        self.assertIn("Copy-Item $BuiltSetup $DesktopSetup -Force", text)


    def test_windows_autostart_uses_lightweight_wake_daemon(self):
        text = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        self.assertIn('"JARVIS-Wake.exe"', text)
        self.assertIn('"wake_daemon_bootstrap.py"', text)
        self.assertIn("lightweight wake listener", text)

    def test_native_autostart_uses_hidden_wscript_launcher(self):
        text = (ROOT / "gui" / "window.py").read_text(encoding="utf-8")
        launcher = (ROOT / "wake_native" / "launch_hidden.vbs").read_text(encoding="utf-8")
        self.assertIn('launch_hidden.vbs', text)
        self.assertIn('wscript.exe', text)
        self.assertIn('//B //NoLogo', text)
        self.assertIn('shell.Run command, 0, False', launcher)
        self.assertIn('JarvisWakeNative.exe', launcher)
        self.assertNotIn('command = f\'"{native_daemon}" --daemon', text)

    def test_healthcheck_detects_direct_console_startup_as_warning(self):
        text = (ROOT / "core" / "healthcheck.py").read_text(encoding="utf-8")
        self.assertIn('launch_hidden.vbs', text)
        self.assertIn('pode abrir terminal', text)

    def test_background_worker_is_built_without_a_console(self):
        build = (ROOT / "installer_build.ps1").read_text(encoding="utf-8-sig")
        spec = (ROOT / "installer_build" / "JARVIS-Tasks.spec").read_text(encoding="utf-8")
        worker = (ROOT / "task_worker.py").read_text(encoding="utf-8")
        self.assertIn('--onefile --windowed --name JARVIS-Tasks', build)
        self.assertIn('console=False', spec)
        self.assertIn('install_no_console_policy()', worker)

    def test_wake_daemon_uses_the_same_hidden_process_policy(self):
        worker = (ROOT / "wake_daemon.py").read_text(encoding="utf-8")
        self.assertIn('install_no_console_policy()', worker)
        source = (ROOT / "wake_native" / "src" / "wake_daemon.cpp").read_text(encoding="utf-8")
        self.assertIn('CREATE_NO_WINDOW', source)


if __name__ == "__main__":
    unittest.main()

