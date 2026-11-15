#Requires -RunAsAdministrator
# Server-specific entry point. Start with -PreflightOnly to inspect the existing installation.
param(
  [switch]$PreflightOnly,
  [string]$CaddyPath='',
  [string]$PythonPath='python.exe',
  [string]$DatabaseUrl='',
  [switch]$EnableRemoteCommands,
  [switch]$InstallFileServerAgent,
  [switch]$EnableDirectoryApprovals,
  [string]$LdapUri='',
  [string]$LdapBindDn='',
  [string]$AdGroupBase='',
  [string]$LdapCaCertificate=''
)
$ErrorActionPreference='Stop'
$profile=Get-Content (Join-Path $PSScriptRoot 'hospital-profile.json') -Raw | ConvertFrom-Json
if ($env:COMPUTERNAME -ine $profile.ComputerName) { throw "Run this on $($profile.ComputerName), not $env:COMPUTERNAME." }
$domain=(Get-CimInstance Win32_ComputerSystem).Domain
if ($domain -ine $profile.Domain) { throw "Expected domain $($profile.Domain); found $domain." }
& (Join-Path $PSScriptRoot 'Test-HospitalReadiness.ps1')
if ($PreflightOnly) { return }
if (-not $CaddyPath -or -not (Test-Path $CaddyPath -PathType Leaf)) { throw 'Supply -CaddyPath pointing to the official Windows caddy.exe binary.' }
if (-not (Test-Path 'E:\')) { throw 'The configured E: monitoring volume is not present.' }
$busy=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -in @(443,8000)})
if ($busy.Count -gt 0) { throw 'Port 443 or 8000 already has a listener. Inspect hospital-readiness.json before updating an existing console or choosing a proxy integration. No existing process was stopped.' }
$params=@{Hostname=$profile.ConsoleHostname;CaddyPath=$CaddyPath;PythonPath=$PythonPath}
if (-not $DatabaseUrl -or -not ($DatabaseUrl.StartsWith('mysql://') -or $DatabaseUrl.StartsWith('mysql+pymysql://'))) { throw 'This hospital profile requires a prepared MySQL database. Supply -DatabaseUrl using the application account.' }
$params.DatabaseUrl=$DatabaseUrl
if ($EnableRemoteCommands) { $params.EnableRemoteCommands=$true }
if ($EnableDirectoryApprovals) {
  $params.EnableDirectoryApprovals=$true
  $params.LdapUri=$LdapUri; $params.LdapBindDn=$LdapBindDn
  $params.LdapBaseDn=$profile.DirectoryBaseDnCandidate
  $params.AdGroupBase=$AdGroupBase; $params.LdapCaCertificate=$LdapCaCertificate
}
& (Join-Path $PSScriptRoot 'Install-Console.ps1') @params
$installDir=Join-Path $env:ProgramData 'NileHopeDLP'
$python=Join-Path $installDir '.venv\Scripts\python.exe'
$configPath=Join-Path $installDir 'runtime.json'
& $python (Join-Path $installDir 'deploy\windows\run_runtime.py') $configPath import-shares (Join-Path $PSScriptRoot 'hospital-shares.csv')
if ($LASTEXITCODE -ne 0) { throw 'Console installed but share registration failed. Inspect the error before continuing.' }
if ($InstallFileServerAgent) {
  # Requires functioning, trusted HTTPS. No certificate checks are disabled.
  $health=Invoke-RestMethod "$($profile.ConsoleUrl)/healthz" -TimeoutSec 15
  if (-not $health.ok) { throw 'Console health check failed. Agent installation was not started.' }
  $config=Get-Content $configPath -Raw | ConvertFrom-Json
  $agentInstaller=Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'agents\windows-monitor\Install-LocalAgent.ps1'
  & $agentInstaller -ServerUrl $profile.ConsoleUrl -EnrollToken $config.ENROLL_TOKEN -Ring pilot -Role fileserver
}
Write-Host "Share monitoring target registered: $($profile.MonitoringPaths -join ', ')"
Write-Host "Console URL: $($profile.ConsoleUrl). Validate HTTPS trust and real file-server events before wider rollout."
