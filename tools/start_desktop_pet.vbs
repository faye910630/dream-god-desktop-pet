' 無主控台啟動夢境神明桌寵（供手動或開機啟動使用）
Option Explicit
Dim sh, fso, dir, root
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(dir)
sh.CurrentDirectory = root
sh.Run "pythonw """ & root & "\fairy_pet.pyw""", 0, False
