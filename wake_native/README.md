# Native wake-word listener (Windows)

The optional native listener keeps the local Hey JARVIS wake-word process
lightweight while the full desktop assistant is hibernated. It is Windows-only
and is not required to run the main JARVIS application.

Build prerequisites:
- Windows 10/11 x64
- Visual Studio 2022 Build Tools with the C++ workload
- PowerShell
- Network access for the pinned ONNX Runtime package restored by
  restore_onnxruntime.ps1

From the repository root, run:

    wake_native\build_native.cmd

The build creates local binaries under wake_native/build/. They are ignored by
Git and must not be committed. Without a native build, JARVIS uses its Python
wake-word path when the optional model/runtime has been installed from the UI.
