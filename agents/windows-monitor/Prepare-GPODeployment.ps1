# Generates a GPO startup deployment bundle. Does not create/link a GPO or edit AD.
param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [Parameter(Mandatory=$true)][string]$EnrollToken,
  [string[]]$FileServers=@(),
  [ValidateSet('pilot','ring20','ring50','all')][string]$Ring='pilot',
  [string]$OutputDir=(Join-Path $PWD 'gpo-deployment')
)
$ErrorActionPreference = 'Stop'
if (([uri]$ServerUrl).Scheme -ne 'https') { throw 'ServerUrl must use HTTPS.' }
New-Item -ItemType Directory -Force $OutputDir | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'FileControlAgent.ps1') $OutputDir -Force
Copy-Item (Join-Path $PSScriptRoot 'Install-LocalAgent.ps1') $OutputDir -Force
@{ServerUrl=$ServerUrl;EnrollToken=$EnrollToken;Ring=$Ring;FileServers=@($FileServers)} |
  ConvertTo-Json | Set-Content (Join-Path $OutputDir 'deployment.json') -Encoding UTF8
$startup = @'
$ErrorActionPreference = 'Stop'
$config = Get-Content (Join-Path $PSScriptRoot 'deployment.json') -Raw | ConvertFrom-Json
$role = 'workstation'
$names = @($config.FileServers | ForEach-Object { ($_ -split '\.')[0] })
if ($names -contains $env:COMPUTERNAME) { $role='fileserver' }
$installed = Join-Path $env:ProgramData 'FileControl\FileControlAgent.ps1'
$source = Join-Path $PSScriptRoot 'FileControlAgent.ps1'
if ((Test-Path $installed) -and (Get-ScheduledTask -TaskName NileHopeFileControl -ErrorAction SilentlyContinue)) {
  $localConfigPath = Join-Path $env:ProgramData 'FileControl\agent-config.json'
  if (Test-Path $localConfigPath) {
    $localConfig = Get-Content $localConfigPath -Raw | ConvertFrom-Json
    if ((Get-FileHash $installed).Hash -eq (Get-FileHash $source).Hash -and $localConfig.Role -eq $role -and $localConfig.ServerUrl -eq $config.ServerUrl -and $localConfig.Ring -eq $config.Ring) { return }
  }
}
& (Join-Path $PSScriptRoot 'Install-LocalAgent.ps1') -ServerUrl $config.ServerUrl -EnrollToken $config.EnrollToken -Ring $config.Ring -Role $role
'@
Set-Content (Join-Path $OutputDir 'Startup-Agent.ps1') $startup -Encoding UTF8
Write-Host "Bundle created in $OutputDir. It contains an enrollment credential."
Write-Host 'Use GPMC: create a GPO linked to the intended computer OU; Computer Configuration -> Windows Settings -> Scripts -> Startup -> PowerShell Scripts -> Show Files.'
Write-Host 'Copy all four generated files into that directory, then Add Startup-Agent.ps1. Merely copying a script to SYSVOL does not register it.'
Write-Host 'Keep SYSVOL write access restricted to administrators. Computers applying the GPO need read access. Deploy certificate trust before the agent.'
Write-Host 'Apply first to a pilot OU, verify heartbeats, then extend to the remaining PC OUs. Use a separate file-server GPO if server OUs differ.'
Write-Host 'After enrollment completes, set ENROLLMENT_ENABLED=0 on the console and rotate the bootstrap token before the next enrollment window.'

