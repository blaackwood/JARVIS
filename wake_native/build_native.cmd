@echo off
setlocal
set "ROOT=%~dp0.."
set "VSDEVCMD=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
if not exist "%VSDEVCMD%" (
  echo Visual Studio 2022 Build Tools with C++ workload is required.
  exit /b 2
)
call "%VSDEVCMD%" -arch=x64
if errorlevel 1 exit /b %errorlevel%
cd /d "%ROOT%"
if not exist "wake_native\deps\ort\build\native\include\onnxruntime_c_api.h" (
  echo ONNX Runtime dependency is missing; restoring pinned version...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "wake_native\restore_onnxruntime.ps1"
  if errorlevel 1 exit /b %errorlevel%
)
if not exist "wake_native\build" mkdir "wake_native\build"
cl /nologo /std:c++17 /O2 /EHsc /MT /I "wake_native\deps\ort\build\native\include" "wake_native\src\wake_daemon.cpp" /link /LIBPATH:"wake_native\deps\ort\runtimes\win-x64\native" onnxruntime.lib winmm.lib user32.lib shell32.lib /OUT:"wake_native\build\JarvisWakeNative.exe"
if errorlevel 1 exit /b %errorlevel%
copy /Y "wake_native\deps\ort\runtimes\win-x64\native\onnxruntime.dll" "wake_native\build\onnxruntime.dll" >nul
if errorlevel 1 exit /b %errorlevel%
echo Native wake daemon built successfully.
