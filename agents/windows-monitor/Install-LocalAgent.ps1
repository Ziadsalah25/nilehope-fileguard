#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [Parameter(Mandatory=$true)][string]$EnrollToken,
  [ValidateSet('pilot','ring20','ring50','all')][string]$Ring = 'pilot',
  [ValidateSet('workstation','fileserver')][string]$Role = 'workstation',
  [switch]$AllowInsecureLocalhost,
  [switch]$DirectConnection,
  [ValidateSet('hospital','local-test')][string]$InstanceName='hospital'
)
$ErrorActionPreference = 'Stop'
if (([uri]$ServerUrl).Scheme -ne 'https' -and -not ($AllowInsecureLocalhost -and ([uri]$ServerUrl).Scheme -eq 'http' -and ([uri]$ServerUrl).IsLoopback)) { throw 'Use HTTPS, or explicitly allow a loopback-only HTTP test.' }
$target = Join-Path $env:ProgramData $(if ($InstanceName -eq 'local-test') {'NileHopeLocalAgent'} else {'FileControl'})
New-Item -ItemType Directory -Force $target | Out-Null
& icacls.exe $target /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot secure agent directory.' }
@{ServerUrl=$ServerUrl;Role=$Role;Ring=$Ring;DirectConnection=[bool]$DirectConnection} | ConvertTo-Json | Set-Content (Join-Path $target 'agent-config.json') -Encoding UTF8
$taskName = if ($InstanceName -eq 'local-test') {'NileHopeFileControl-LocalTest'} else {'NileHopeFileControl'}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $taskName }
Copy-Item (Join-Path $PSScriptRoot 'FileControlAgent.ps1') (Join-Path $target 'FileControlAgent.ps1') -Force
# Persist the bootstrap token only in the protected folder. Remove it after enrollment.
if (-not (Test-Path (Join-Path $target 'key.txt'))) {
  Set-Content (Join-Path $target 'enroll-token.txt') $EnrollToken -NoNewline
}
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Server "{1}" -Ring {2} -Role {3}' -f (Join-Path $target 'FileControlAgent.ps1'),$ServerUrl,$Ring,$Role
$arguments += ' -StateDir "' + $target + '"'
if ($AllowInsecureLocalhost) { $arguments += ' -AllowInsecureLocalhost' }
if ($DirectConnection) { $arguments += ' -DirectConnection' }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::Zero) -RestartCount 100 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host 'Agent task started. Confirm its heartbeat in the console; startup alone does not prove enrollment.'
