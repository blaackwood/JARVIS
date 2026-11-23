$ErrorActionPreference = "Stop"
$P = Split-Path -Parent $MyInvocation.MyCommand.Path
$B = Join-Path $P "installer_build"
$D = Join-Path $B "dist"
$W = Join-Path $B "work"
$Py = Join-Path $P ".venv\Scripts\python.exe"
Set-Location $P
$Out = Join-Path $B "package"
foreach ($Path in @($D,$W,$Out)) { if (Test-Path $Path) { Remove-Item $Path -Recurse -Force } }
New-Item -ItemType Directory -Force -Path $D,$W | Out-Null

Write-Host "Building JARVIS desktop application..."
& $Py -m PyInstaller --noconfirm --clean --onedir --windowed --name JARVIS --contents-directory . --distpath "$D\main" --workpath "$W\main" --specpath $B --icon "$P\config\jarvis.ico" --add-data "$P\actions;actions" --add-data "$P\agents;agents" --add-data "$P\plugins;plugins" --add-data "$P\providers;providers" --add-data "$P\core\prompt.txt;core" --add-data "$P\core\face_model.obj;core" --add-data "$P\config\jarvis.ico;config" --collect-all google.genai --collect-all openwakeword --collect-all cv2 --hidden-import win32timezone --hidden-import pywintypes --hidden-import pythoncom --hidden-import memory.semantic_index --hidden-import actions.semantic_memory --hidden-import core.visual_board main.py
if ($LASTEXITCODE -ne 0) { throw "JARVIS application build failed ($LASTEXITCODE)" }

Write-Host "Building isolated wake-word/tray process..."
& $Py -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Wake --distpath "$D\wake" --workpath "$W\wake" --specpath $B --collect-all openwakeword --collect-all PyQt6 --hidden-import sounddevice --hidden-import numpy wake_daemon.py
if ($LASTEXITCODE -ne 0) { throw "Wake daemon build failed ($LASTEXITCODE)" }

Write-Host "Building isolated background-task process..."
& $Py -m PyInstaller --noconfirm --clean --onefile --windowed --name JARVIS-Tasks --distpath "$D\tasks" --workpath "$W\tasks" --specpath $B --collect-submodules core.tasks --collect-submodules core.routines --collect-all google.genai --hidden-import httpx task_worker.py
if ($LASTEXITCODE -ne 0) { throw "Task worker build failed ($LASTEXITCODE)" }

New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item "$D\main\JARVIS\*" $Out -Recurse -Force
Copy-Item "$D\wake\JARVIS-Wake.exe" $Out -Force
Copy-Item "$D\tasks\JARVIS-Tasks.exe" $Out -Force
Write-Host "Package assembly complete."
Get-ChildItem $Out -File | Measure-Object Length -Sum | ForEach-Object { "Package root files: $($_.Count); bytes: $($_.Sum)" }

$ISCC = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) { throw "Inno Setup compiler not found: $ISCC" }
$InstallerScript = Join-Path $B "installer.iss"
if (-not (Test-Path $InstallerScript)) { throw "Installer script missing: $InstallerScript" }
Write-Host "Compiling JARVIS installer with Windows auto-start enabled..."
$BuiltSetup = Join-Path $B "release\JARVIS-Setup.exe"
if (Test-Path $BuiltSetup) {
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $BuiltSetup "$BuiltSetup.before-autostart-$Stamp.exe" -Force
    Remove-Item $BuiltSetup -Force
}
& $ISCC /Qp $InstallerScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed ($LASTEXITCODE)" }

$DesktopSetup = Join-Path ([Environment]::GetFolderPath("Desktop")) "JARVIS-Setup.exe"
if (Test-Path $DesktopSetup) {
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $BackupSetup = Join-Path ([Environment]::GetFolderPath("Desktop")) "JARVIS-Setup-before-autostart-$Stamp.exe"
    Copy-Item $DesktopSetup $BackupSetup -Force
    Write-Host "Previous desktop installer backed up to $BackupSetup"
}
Copy-Item $BuiltSetup $DesktopSetup -Force
Write-Host "Updated desktop installer: $DesktopSetup"

