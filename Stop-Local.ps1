param()
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$marker=Join-Path $PSScriptRoot '.local\compose-project.txt'
if (-not (Test-Path $marker)) { throw 'No local installation marker was found.' }
$name=(Get-Content $marker -Raw).Trim()
if ($name -notin @('nile-local-pc','nile-local-demo')) { throw 'Unexpected local project identity.' }
$containers=@(& docker ps -q --filter "label=com.docker.compose.project=$name")
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not available.' }
if ($containers.Count -gt 0) { & docker stop @containers }
Write-Host 'The local app containers are stopped. Database volumes and credentials were retained.'
try {
  $task=Get-ScheduledTask -TaskName 'NileHopeFileControl-LocalTest' -ErrorAction SilentlyContinue
  if ($task) { Stop-ScheduledTask -TaskName 'NileHopeFileControl-LocalTest' -ErrorAction Stop }
} catch { Write-Warning 'Stopping the separate local-test agent task requires an Administrator PowerShell window.' }
