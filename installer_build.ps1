$ErrorActionPreference = "Stop"
$P = Split-Path -Parent $MyInvocation.MyCommand.Path
$B = Join-Path $P "installer_build"
$D = Join-Path $B "dist"
$W = Join-Path $B "work"
$Out = Join-Path $B "package"
$Py = Join-Path $P ".venv\Scripts\python.exe"
Set-Location $P

# A reproducible build environment: Python 3.13 is the tested release target.
if (-not (Test-Path $Py)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python Launcher not found. Install Python 3.13 x64, then retry."
    }
    & py -3.13 -m venv (Join-Path $P ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python 3.13 build environment." }
}
$PythonVersion = & $Py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($PythonVersion.Trim() -ne "3.13") {
    throw "Release builds require Python 3.13; found $PythonVersion."
}

Write-Host "Installing JARVIS runtime and packaging dependencies..."
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed ($LASTEXITCODE)" }
& $Py -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "JARVIS build dependencies failed to install ($LASTEXITCODE)" }

foreach ($Path in @($D,$W,$Out)) {
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $D,$W,$Out | Out-Null

# Bundle only the Chromium Headless Shell required by local browser QA.
# Interactive browser automation launches the user's own installed Chrome/Edge/Firefox.
# Use a clean cache so the browser revision always matches the installed Playwright.
$BrowserStore = Join-Path $B "browser-store"
if (Test-Path $BrowserStore) { Remove-Item $BrowserStore -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BrowserStore | Out-Null
$PreviousBrowserPath = $env:PLAYWRIGHT_BROWSERS_PATH
$env:PLAYWRIGHT_BROWSERS_PATH = $BrowserStore
Write-Host "Downloading the Playwright Chromium Headless Shell for the installer..."
& $Py -m playwright install --only-shell chromium
$BrowserInstallExit = $LASTEXITCODE
if ($PreviousBrowserPath) {
    $env:PLAYWRIGHT_BROWSERS_PATH = $PreviousBrowserPath
} else {
    Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
}
if ($BrowserInstallExit -ne 0) { throw "Playwright Chromium Headless Shell download failed ($BrowserInstallExit)" }
$HeadlessBrowser = Get-ChildItem $BrowserStore -Directory -Filter "chromium_headless_shell-*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $HeadlessBrowser) {
    throw "Playwright Chromium Headless Shell was not installed into $BrowserStore."
}
$HeadlessExecutable = Get-ChildItem $HeadlessBrowser.FullName -Recurse -File -Filter "chrome-headless-shell.exe" | Select-Object -First 1
$HeadlessLicense = Get-ChildItem $HeadlessBrowser.FullName -Recurse -File -Filter "LICENSE.headless_shell" | Select-Object -First 1
if (-not $HeadlessExecutable -or -not $HeadlessLicense) {
    throw "The Playwright Headless Shell executable or its third-party licence is missing."
}

Write-Host "Building JARVIS desktop application..."
& $Py -m PyInstaller --noconfirm --clean --onedir --windowed --name JARVIS --contents-directory . --distpath "$D\main" --workpath "$W\main" --specpath $B --icon "$P\config\jarvis.ico" --add-data "$P\actions;actions" --add-data "$P\agents;agents" --add-data "$P\plugins;plugins" --add-data "$P\providers;providers" --add-data "$P\dashboard;dashboard" --add-data "$P\tools;tools" --add-data "$P\.agents;.agents" --add-data "$P\core\prompt.txt;core" --add-data "$P\core\face_model.obj;core" --add-data "$P\config\jarvis.ico;config" --collect-all google.genai --collect-all openwakeword --collect-all cv2 --collect-submodules core --collect-submodules memory --collect-submodules gui --collect-submodules visual_novo --hidden-import win32timezone --hidden-import pywintypes --hidden-import pythoncom main.py
if ($LASTEXITCODE -ne 0) { throw "JARVIS application build failed ($LASTEXITCODE)" }

Write-Host "Building isolated wake-word/tray process..."
& $Py -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Wake --distpath "$D\wake" --workpath "$W\wake" --specpath $B --collect-all openwakeword --collect-all ai_edge_litert --hidden-import sounddevice --hidden-import numpy --hidden-import core.wake_startup --hidden-import core.windows_process --hidden-import core.wake_tray_win32 wake_daemon.py
if ($LASTEXITCODE -ne 0) { throw "Wake daemon build failed ($LASTEXITCODE)" }

Write-Host "Building isolated background-task process..."
& $Py -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Tasks --distpath "$D\tasks" --workpath "$W\tasks" --specpath $B --collect-submodules core.tasks --collect-submodules core.routines --collect-all google.genai --hidden-import httpx task_worker.py
if ($LASTEXITCODE -ne 0) { throw "Task worker build failed ($LASTEXITCODE)" }

Copy-Item "$D\main\JARVIS\*" $Out -Recurse -Force
Copy-Item "$D\wake\JARVIS-Wake.exe" $Out -Force
Copy-Item "$D\tasks\JARVIS-Tasks.exe" $Out -Force
$BundledBrowserDir = Join-Path $Out "ms-playwright"
New-Item -ItemType Directory -Force -Path $BundledBrowserDir | Out-Null
Copy-Item $HeadlessBrowser.FullName $BundledBrowserDir -Recurse -Force
if (-not (Get-ChildItem $BundledBrowserDir -Recurse -File -Filter "chrome-headless-shell.exe")) {
    throw "Bundled Playwright Chromium Headless Shell is missing from the installer package."
}
if (-not (Get-ChildItem $BundledBrowserDir -Recurse -File -Filter "LICENSE.headless_shell")) {
    throw "Bundled Chromium third-party licence is missing from the installer package."
}

# Skills are runtime content (not Python modules) and must remain next to the app,
# including each upstream SKILL.md and its original licence/attribution files.
if (-not (Test-Path (Join-Path $Out ".agents\skills"))) {
    throw "Bundled Skills directory is missing from the frozen application."
}
foreach ($Document in @("LICENSE","THIRD_PARTY_NOTICES.md","SKILLS.md","README.pt-BR.md","SECURITY.md","FEATURES.md")) {
    Copy-Item (Join-Path $P $Document) $Out -Force
}
# Retain the Python runtime licence and Playwright's own upstream notices.
$PythonLicense = Join-Path (& $Py -c "import sys; print(sys.base_prefix)") "LICENSE.txt"
if (Test-Path $PythonLicense) {
    Copy-Item $PythonLicense (Join-Path $Out "PYTHON-LICENSE.txt") -Force
}
$PlaywrightLicense = Join-Path $Out "playwright\driver\LICENSE"
$PlaywrightPackageDir = Join-Path $Out "playwright\driver\package"
foreach ($Name in @("LICENSE","NOTICE","ThirdPartyNotices.txt")) {
    $Source = if ($Name -eq "LICENSE") { $PlaywrightLicense } else { Join-Path $PlaywrightPackageDir $Name }
    if (Test-Path $Source) {
        $Destination = if ($Name -eq "LICENSE") { Join-Path $Out "PLAYWRIGHT-LICENSE.txt" } else { Join-Path $Out ("PLAYWRIGHT-" + $Name.ToUpperInvariant()) }
        Copy-Item $Source $Destination -Force
    }
}
$SitePackages = Join-Path $P ".venv\Lib\site-packages"
$PyInstallerDist = Get-ChildItem $SitePackages -Directory -Filter "pyinstaller-*.dist-info" | Select-Object -First 1
if ($PyInstallerDist) {
    $PyInstallerCopying = Join-Path $PyInstallerDist.FullName "licenses\COPYING.txt"
    if (Test-Path $PyInstallerCopying) {
        Copy-Item $PyInstallerCopying (Join-Path $Out "PYINSTALLER-COPYING.txt") -Force
    }
}
$HooksDist = Get-ChildItem $SitePackages -Directory -Filter "pyinstaller_hooks_contrib-*.dist-info" | Select-Object -First 1
if ($HooksDist) {
    $HooksLicense = Join-Path $HooksDist.FullName "licenses\LICENSE"
    if (Test-Path $HooksLicense) {
        Copy-Item $HooksLicense (Join-Path $Out "PYINSTALLER-HOOKS-CONTRIB-LICENSE.txt") -Force
    }
}

$PackageStats = Get-ChildItem $Out -Recurse -File | Measure-Object Length -Sum
Write-Host ("Package files: {0}; bytes: {1}" -f $PackageStats.Count,$PackageStats.Sum)

$ISCC = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) {
    $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Compiler) { $ISCC = $Compiler.Source }
    else { throw "Inno Setup 6 compiler not found. Install Inno Setup 6 and retry." }
}
$InstallerScript = Join-Path $B "installer.iss"
if (-not (Test-Path $InstallerScript)) { throw "Installer script missing: $InstallerScript" }

Write-Host "Compiling JARVIS Windows x64 installer..."
$BuiltSetup = Join-Path $B "release\JARVIS-Setup.exe"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BuiltSetup) | Out-Null
if (Test-Path $BuiltSetup) { Remove-Item $BuiltSetup -Force }
& $ISCC /Qp $InstallerScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed ($LASTEXITCODE)" }
if (-not (Test-Path $BuiltSetup)) { throw "Inno Setup returned success but no installer was produced." }

$Hash = (Get-FileHash $BuiltSetup -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  JARVIS-Setup.exe" | Set-Content -Encoding ascii (Join-Path (Split-Path -Parent $BuiltSetup) "JARVIS-Setup.exe.sha256")
$Size = (Get-Item $BuiltSetup).Length
Write-Host ("Installer ready: {0} ({1:N1} MB)" -f $BuiltSetup,($Size / 1MB))
Write-Host ("SHA256: {0}" -f $Hash)

