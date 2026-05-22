Set oWS = WScript.CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

' OneDriveのデスクトップを優先、なければ通常のデスクトップ
sOneDrive = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\OneDrive\Desktop"
sNormal   = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\Desktop"

If oFSO.FolderExists(sOneDrive) Then
    sDesktop = sOneDrive
Else
    sDesktop = sNormal
End If

sLink = sDesktop & "\GH_System.lnk"
Set oLink = oWS.CreateShortcut(sLink)
oLink.TargetPath       = "C:\Program Files\Python314\pythonw.exe"
oLink.Arguments        = """C:\Users\Public\gh_system\launcher.py"""
oLink.WorkingDirectory = "C:\Users\Public\gh_system"
oLink.Save()

MsgBox "Shortcut saved to: " & sLink