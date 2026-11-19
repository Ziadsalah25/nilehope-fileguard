param([Parameter(Mandatory=$true)][string]$InstallDir,
      [Parameter(Mandatory=$true)][ValidateSet('Web','Worker','Proxy')][string]$Mode)
$ErrorActionPreference = 'Stop'
Set-Location $InstallDir
$env:PYTHONPATH = $InstallDir
$env:PYTHONUNBUFFERED = '1'
$env:XDG_DATA_HOME = Join-Path $InstallDir 'data\caddy'
$env:XDG_CONFIG_HOME = Join-Path $InstallDir 'data\caddy-config'
$log = Join-Path $InstallDir "data\$Mode.log"
if ((Test-Path $log) -and (Get-Item $log).Length -gt 10MB) { Move-Item $log "$log.1" -Force }
if ($Mode -eq 'Proxy') {
  # Caddy writes informational logs to stderr; Windows PowerShell can treat native stderr as an error.
  # Continue so normal Caddy output is captured without terminating the scheduled task.
  $ErrorActionPreference = 'Continue'
  & (Join-Path $InstallDir 'caddy.exe') run --config (Join-Path $InstallDir 'Caddyfile') 2>&1 | Out-File $log -Append -Encoding utf8
} else {
  & (Join-Path $InstallDir '.venv\Scripts\python.exe') (Join-Path $InstallDir 'deploy\windows\run_runtime.py') (Join-Path $InstallDir 'runtime.json') $Mode.ToLower() 2>&1 | Out-File $log -Append -Encoding utf8
}
exit $LASTEXITCODE
