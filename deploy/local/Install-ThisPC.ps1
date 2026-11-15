#Requires -RunAsAdministrator
param([string]$ProjectRoot=(Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))
$ErrorActionPreference='Stop'
$config=@{}
foreach ($line in (Get-Content (Join-Path $ProjectRoot '.env'))) {
  if ($line -match '^([A-Z_]+)=(.*)$') {$config[$matches[1]]=$matches[2]}
}
if (-not $config.ENROLL_TOKEN -or -not $config.FRONTEND_PORT) { throw 'Run Start-Local.bat first.' }
$url="http://127.0.0.1:$($config.FRONTEND_PORT)"
$health=Invoke-RestMethod "$url/healthz" -TimeoutSec 10
if (-not $health.ok) { throw 'The local console is unavailable.' }
& (Join-Path $ProjectRoot 'agents\windows-monitor\Install-LocalAgent.ps1') -ServerUrl $url -EnrollToken $config.ENROLL_TOKEN -Role workstation -Ring pilot -AllowInsecureLocalhost -InstanceName local-test
Write-Host 'The separate local-test task is started. Confirm this PC in Devices after its first heartbeat.'
