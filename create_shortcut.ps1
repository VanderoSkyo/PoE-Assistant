# The shortcut points to run.bat (not to a Python path), so it keeps working when Python is updated:
# run.bat repairs the environment if needed.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop 'PoE Assistant.lnk'))
$lnk.TargetPath = Join-Path $root 'run.bat'
$lnk.WorkingDirectory = $root
$lnk.WindowStyle = 7
$lnk.Description = 'PoE Assistant'
$lnk.Save()
Write-Host "Shortcut created on the desktop."
