' Ejecuta stop_app.ps1 sin ventana de PowerShell.
Option Explicit

Dim fso, sh, scriptDir, ps1, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("Wscript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = scriptDir & "\stop_app.ps1"

If Not fso.FileExists(ps1) Then
    MsgBox "No se encontro stop_app.ps1 en:" & vbCrLf & scriptDir, vbCritical, "EvaluaERP"
    WScript.Quit 1
End If

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
sh.Run cmd, 0, False
