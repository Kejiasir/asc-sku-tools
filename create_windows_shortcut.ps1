# Desktop shortcut for Windows. Run once:
#   powershell -ExecutionPolicy Bypass -File create_windows_shortcut.ps1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop "ASC SKU.lnk"))
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = '"' + (Join-Path $root "ASC SKU.vbs") + '"'
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7
$icon = Join-Path $root "assets\icon.ico"
if (Test-Path $icon) {
    $shortcut.IconLocation = $icon
}
$shortcut.Description = "ASC SKU"
$shortcut.Save()
Write-Host "Created $desktop\ASC SKU.lnk"
