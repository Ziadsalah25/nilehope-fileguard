# Windows regression checks; no Docker daemon, installation, or administrator rights needed.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'deploy\local\Docker-Tools.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('fileguard-discovery-'+[guid]::NewGuid().ToString('N'))
$savedPath=$env:Path
$savedProgramFiles=$env:ProgramFiles
$savedProgramW6432=$env:ProgramW6432
$savedLocalAppData=$env:LOCALAPPDATA
$checks=0
function Assert-Discovery($condition,[string]$message) {
  if (-not $condition) { throw $message }
}
function Add-TestFile([string]$file) {
  New-Item -ItemType Directory -Force (Split-Path $file -Parent) | Out-Null
  [IO.File]::WriteAllText($file,'Test discovery only; never execute this file.')
}
try {
  New-Item -ItemType Directory -Path $testRoot | Out-Null
  $env:Path=''
  $systemRoot=Join-Path $testRoot 'Program Files\Docker\Docker'
  $systemCli=Join-Path $systemRoot 'resources\bin\docker.exe'
  $systemDesktop=Join-Path $systemRoot 'Docker Desktop.exe'
  Add-TestFile $systemCli
  Add-TestFile $systemDesktop
  $tools=Get-FileGuardDockerTools -InstallRoots @($systemRoot)
  Assert-Discovery ($tools.DockerPath -eq $systemCli) 'Must locate a system installation when Docker is absent from PATH.'
  Assert-Discovery ($tools.DesktopPath -eq $systemDesktop) 'Must locate the Desktop launcher alongside the system CLI.'
  $checks++; Write-Output 'PASS: system install without PATH, including spaces'

  $userRoot=Join-Path $testRoot 'User Profile\Programs\DockerDesktop'
  $userCli=Join-Path $userRoot 'resources\bin\docker.exe'
  Add-TestFile $userCli
  Add-TestFile (Join-Path $userRoot 'Docker Desktop.exe')
  $tools=Get-FileGuardDockerTools -InstallRoots @((Join-Path $testRoot 'absent'),$userRoot)
  Assert-Discovery ($tools.DockerPath -eq $userCli) 'Must locate a per-user installation when Docker is absent from PATH.'
  $checks++; Write-Output 'PASS: per-user install without PATH'

  $pathCli=Join-Path $testRoot 'custom cli\docker.exe'
  Add-TestFile $pathCli
  $env:Path=Split-Path $pathCli -Parent
  $tools=Get-FileGuardDockerTools -InstallRoots @($systemRoot,$userRoot)
  Assert-Discovery ($tools.DockerPath -eq $pathCli) 'The Docker CLI already selected on PATH must take precedence.'
  $checks++; Write-Output 'PASS: existing PATH selection takes precedence'

  $env:Path=''
  $tools=Get-FileGuardDockerTools -InstallRoots @((Join-Path $testRoot 'absent'))
  Assert-Discovery (-not $tools.DockerPath -and -not $tools.DesktopPath) 'A missing installation must not return a pretend executable.'
  $checks++; Write-Output 'PASS: missing installation reported accurately'

  $desktopOnly=Join-Path $testRoot 'desktop only'
  Add-TestFile (Join-Path $desktopOnly 'Docker Desktop.exe')
  $tools=Get-FileGuardDockerTools -InstallRoots @($desktopOnly)
  Assert-Discovery (-not $tools.DockerPath -and $tools.DesktopPath) 'Desktop alone must not be mistaken for the Docker CLI.'
  $checks++; Write-Output 'PASS: incomplete installation distinguishes Desktop from CLI'

  # Exercise the actual default discovery paths, without writing to real installation folders.
  $env:ProgramFiles=Join-Path $testRoot 'Program Files'
  $env:ProgramW6432=$env:ProgramFiles
  $env:LOCALAPPDATA=Join-Path $testRoot 'User Profile'
  $tools=Get-FileGuardDockerTools
  Assert-Discovery ($tools.DockerPath -eq $systemCli) 'Default discovery must recognize Program Files.'
  Remove-Item -LiteralPath $systemCli
  $tools=Get-FileGuardDockerTools
  Assert-Discovery ($tools.DockerPath -eq $userCli) 'Default discovery must also recognize the per-user directory.'
  $checks++; Write-Output 'PASS: default system and per-user installation paths'

  $repo=Split-Path $PSScriptRoot -Parent
  foreach ($script in @(Get-ChildItem -LiteralPath $repo -Filter '*.ps1') + @(Get-ChildItem -LiteralPath (Join-Path $repo 'deploy\local') -Filter '*.ps1')) {
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($script.FullName,[ref]$tokens,[ref]$errors) | Out-Null
    Assert-Discovery ($errors.Count -eq 0) ('PowerShell syntax error in '+$script.Name)
  }
  $checks++; Write-Output 'PASS: Windows launcher and helper syntax'
  Write-Output "$checks Windows launcher checks passed."
} finally {
  $env:Path=$savedPath
  $env:ProgramFiles=$savedProgramFiles
  $env:ProgramW6432=$savedProgramW6432
  $env:LOCALAPPDATA=$savedLocalAppData
  Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
