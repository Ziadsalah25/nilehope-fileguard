param(
  [string]$DotnetPath='dotnet',
  [string]$OutputDirectory
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $projectRoot ('.local\recovery-pilot-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
$output=[IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a new output directory; an existing package was preserved.' }
$worker=Join-Path $output 'worker'
New-Item -ItemType Directory -Path $worker -Force | Out-Null
& $DotnetPath publish (Join-Path $projectRoot 'agents\windows-recovery\FileGuard.Recovery.csproj') -c Release -r win-x64 --self-contained true -o $worker --nologo
if ($LASTEXITCODE -ne 0) { throw 'Recovery package build failed.' }
$tools=Join-Path $output 'tools'
New-Item -ItemType Directory -Path $tools | Out-Null
foreach ($name in @('Recovery-PilotTools.ps1','Install-RecoveryPilot.ps1','Set-RecoveryPilotMode.ps1','Test-RecoveryPilot.ps1')) {
  Copy-Item -LiteralPath (Join-Path $projectRoot ('agents\windows-recovery\'+$name)) -Destination $tools
}
$monitor=Join-Path $output 'monitoring-agent'
New-Item -ItemType Directory -Path $monitor | Out-Null
foreach ($name in @('FileControlAgent.ps1','Install-LocalAgent.ps1')) {
  Copy-Item -LiteralPath (Join-Path $projectRoot ('agents\windows-monitor\'+$name)) -Destination $monitor
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\MANUAL-RECOVERY-PILOT.md') -Destination (Join-Path $output 'README.md')
$archive=$output+'.zip'
Compress-Archive -LiteralPath $worker,$tools,$monitor,(Join-Path $output 'README.md') -DestinationPath $archive
Write-Host "Manual Windows file-server pilot package: $archive"
Write-Host 'Extract on the file server; follow README.md. No GPO or replacement of the monitoring agent is required.'
