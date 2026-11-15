param()
$path=Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) '.local\login.txt'
if (-not (Test-Path $path)) { throw 'Run Start-Local.bat first.' }
Start-Process notepad.exe -ArgumentList "`"$path`""
