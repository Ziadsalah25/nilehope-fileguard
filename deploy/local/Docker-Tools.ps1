# Shared Windows Docker Desktop discovery. No registry or permanent PATH changes.
function Get-FileGuardDockerTools {
  [CmdletBinding()]
  param([string[]]$InstallRoots)

  if (-not $PSBoundParameters.ContainsKey('InstallRoots')) {
    $InstallRoots=@()
    foreach ($programRoot in @($env:ProgramFiles,$env:ProgramW6432)) {
      if ($programRoot) { $InstallRoots+=Join-Path $programRoot 'Docker\Docker' }
    }
    if ($env:LOCALAPPDATA) {
      $InstallRoots+=Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop'
    }
  }
  $InstallRoots=@($InstallRoots | Where-Object { $_ } | Select-Object -Unique)
  $dockerPath=$null
  $desktopPath=$null
  $command=Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($command) { $dockerPath=$command.Path }
  foreach ($installRoot in $InstallRoots) {
    if (-not $dockerPath) {
      $candidate=Join-Path $installRoot 'resources\bin\docker.exe'
      if (Test-Path -LiteralPath $candidate -PathType Leaf) { $dockerPath=$candidate }
    }
    if (-not $desktopPath) {
      $candidate=Join-Path $installRoot 'Docker Desktop.exe'
      if (Test-Path -LiteralPath $candidate -PathType Leaf) { $desktopPath=$candidate }
    }
  }
  [pscustomobject]@{DockerPath=$dockerPath;DesktopPath=$desktopPath}
}
