#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][ValidateSet('Monitoring','Recovery')][string]$Phase,
  [string]$InstallRoot=(Join-Path $env:ProgramData 'NileHopeRecoveryPilot'),
  [ValidateRange(10,120)][int]$TimeoutSeconds=30
)
. (Join-Path $PSScriptRoot 'Recovery-PilotTools.ps1')
$pilot=Read-RecoveryPilot $InstallRoot
if ([bool]$pilot.Config.autoRestore -ne ($Phase -eq 'Recovery')) { throw 'The installed mode does not match the requested test phase.' }
if ((Get-Service $pilot.Record.serviceName).Status -ne 'Running') { throw 'Start the pilot service first.' }
$name='fileguard-pilot-test-'+[guid]::NewGuid().ToString('N')+'.txt'
$path=Join-Path $pilot.Config.protectedRoot $name
$manifest=Join-Path $pilot.Config.stateRoot 'manifest.json'
function Wait-PilotCondition([scriptblock]$Check,[string]$Failure) {
  $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  do { if (& $Check) { return }; Start-Sleep -Milliseconds 250 } while ([DateTime]::UtcNow -lt $deadline)
  throw $Failure
}
function Test-CapturedHash([string]$Hash) {
  if (-not (Test-Path -LiteralPath $manifest)) { return $false }
  $history=(Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).PSObject.Properties[$name]
  return $history -and $history.Value.versions.Count -gt 0 -and $history.Value.versions[-1].sha256 -eq $Hash
}
[IO.File]::WriteAllText($path,'Disposable pilot version one.')
$first=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
Wait-PilotCondition { Test-CapturedHash $first } 'The first version was not captured. Review the service account and worker logs.'
[IO.File]::WriteAllText($path,'Disposable pilot version two.')
$second=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
Wait-PilotCondition { Test-CapturedHash $second } 'The updated version was not captured.'
# This script removes ONLY the unique disposable file it just created.
Remove-Item -LiteralPath $path
$expected=if ($Phase -eq 'Recovery') {'restored'} else {'delete_observed'}
Wait-PilotCondition {
  $auditPath=Join-Path $pilot.Config.stateRoot 'audit.jsonl'
  if (-not (Test-Path -LiteralPath $auditPath)) { return $false }
  return @(Get-Content -LiteralPath $auditPath | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.relativePath -eq $name -and $_.kind -eq $expected }).Count -gt 0
} "The service did not report $expected."
if ($Phase -eq 'Recovery') {
  if (-not (Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $second) { throw 'Restored content failed verification.' }
  Write-Host "PASS: latest captured version restored and SHA-256 verified. Disposable file retained: $path"
} else {
  Start-Sleep -Seconds ([Math]::Max(3,2*[int]$pilot.Config.scanSeconds))
  if (Test-Path -LiteralPath $path) { throw 'The file was restored while monitoring was selected.' }
  Write-Host "PASS: deletion observed without restoring. Relative path: $name"
}
