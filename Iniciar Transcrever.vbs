Option Explicit

Dim shell, fileSystem, projectDirectory, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
command = "cmd.exe /d /s /c ""cd /d """ & projectDirectory & """ && uv run transcrever desktop"""
shell.Run command, 0, True
