#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][ValidateSet('Monitoring','Recovery')][string]$Mode,
  [string]$InstallRoot=(Join-Path $env:ProgramData 'NileHopeRecoveryPilot')
)
. (Join-Path $PSScriptRoot 'Recovery-PilotTools.ps1')
$pilot=Read-RecoveryPilot $InstallRoot
$service=Get-Service -Name $pilot.Record.serviceName
if ($service.Status -ne 'Stopped') { Stop-Service -Name $service.Name; (Get-Service $service.Name).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(30)) }
$pilot.Config.autoRestore=($Mode -eq 'Recovery')
$rights=if ($pilot.Config.autoRestore) {'Modify'} else {'ReadAndExecute'}
# Replace only this service identity's explicit rule; preserve staff/share ACLs.
$acl=Get-Acl -LiteralPath $pilot.Config.protectedRoot
$rule=New-Object Security.AccessControl.FileSystemAccessRule($pilot.Record.serviceAccount,$rights,'ContainerInherit,ObjectInherit','None','Allow')
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $pilot.Config.protectedRoot -AclObject $acl
Write-PilotJson $pilot.ConfigPath $pilot.Config
Add-Content -LiteralPath (Join-Path $pilot.Install 'mode-changes.jsonl') -Value (@{mode=$Mode;at=[DateTime]::UtcNow.ToString('o');actor=[Security.Principal.WindowsIdentity]::GetCurrent().Name} | ConvertTo-Json -Compress)
Start-Service -Name $service.Name
Write-Host "Mode: $Mode. Scope: $($pilot.Config.protectedRoot)"
if ($pilot.Config.autoRestore) { Write-Host 'Missing files with previously captured versions can now be restored, including deletions recorded during monitoring.' }
