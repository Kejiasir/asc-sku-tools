Option Explicit
Dim fso, sh, root, pyw
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root
pyw = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = root & "\.venv\Scripts\python.exe"
If Not fso.FileExists(pyw) Then
  MsgBox "找不到 .venv。请先创建虚拟环境并安装 requirements.txt", 16, "ASC SKU"
  WScript.Quit 1
End If
sh.Run """" & pyw & """ """ & root & "\create_subscriptions.py""", 0, False
