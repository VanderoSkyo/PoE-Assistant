$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop 'PoE Assistant.lnk'))
$lnk.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
$lnk.Arguments = '"' + (Join-Path $root 'poe_assistant.py') + '"'
$lnk.WorkingDirectory = $root
$lnk.Description = 'PoE Assistant'
$lnk.Save()
Write-Host "Shortcut created on the desktop."
