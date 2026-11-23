Option Explicit

Dim fso, shell, base, daemon, pythonw, command, logPath, logFile

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' The script is inside <JARVIS>\wake_native. Launch the console-subsystem
' native daemon with SW_HIDE so its long-lived listener never opens a terminal.
base = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
daemon = base & "\wake_native\build\JarvisWakeNative.exe"
logPath = base & "\memory\wake_daemon.log"

If WScript.Arguments.Count < 1 Then
    WriteLog "hidden startup launcher: pythonw.exe argument missing"
    WScript.Quit 2
End If

pythonw = WScript.Arguments(0)

If Not fso.FileExists(daemon) Then
    WriteLog "hidden startup launcher: native daemon executable not found"
    WScript.Quit 3
End If

If Not fso.FileExists(pythonw) Then
    WriteLog "hidden startup launcher: pythonw.exe path not found"
    WScript.Quit 4
End If

command = Quote(daemon) & " --daemon " & Quote(base) & " 0 " & Quote(pythonw)

On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
    WriteLog "hidden startup launcher: Shell.Run failed (" & CStr(Err.Number) & ")"
    WScript.Quit 5
End If
On Error GoTo 0

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function

Sub WriteLog(message)
    On Error Resume Next
    Set logFile = fso.OpenTextFile(logPath, 8, True)
    logFile.WriteLine CStr(Now) & " " & message
    logFile.Close
    On Error GoTo 0
End Sub
