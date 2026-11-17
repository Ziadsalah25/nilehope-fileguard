# Shared by the manual pilot installer, mode switch, and disposable-file check.
$ErrorActionPreference='Stop'
function Assert-PilotLocalPath([string]$Path) {
  if ($Path -notmatch '^[A-Za-z]:\\.+' -or $Path -match '["\r\n]') { throw 'Use an absolute local data directory, not a UNC path or volume root.' }
  $full=[IO.Path]::GetFullPath($Path).TrimEnd('\')
  for ($item=$full; $item; $item=Split-Path -Parent $item) {
    if ((Test-Path -LiteralPath $item) -and ((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Links/reparse points are outside the pilot: $item" }
  }
  return $full
}
function Set-PilotDirectoryAccess([string]$Path,[string]$ServiceAccount,[string]$Rights) {
  $acl=New-Object Security.AccessControl.DirectorySecurity
  $acl.SetAccessRuleProtection($true,$false)
  foreach ($sid in @('S-1-5-18','S-1-5-32-544')) {
    $identity=New-Object Security.Principal.SecurityIdentifier($sid)
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
  }
  if ($ServiceAccount) { $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($ServiceAccount,$Rights,'ContainerInherit,ObjectInherit','None','Allow'))) }
  Set-Acl -LiteralPath $Path -AclObject $acl
}
function Write-PilotJson([string]$Path,$Value) {
  $temp=$Path+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
  try {
    [IO.File]::WriteAllText($temp,($Value | ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temp -Destination $Path -Force
  } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp } }
}
function Read-RecoveryPilot([string]$InstallRoot) {
  $install=Assert-PilotLocalPath $InstallRoot
  $record=Get-Content -LiteralPath (Join-Path $install 'pilot-install.json') -Raw | ConvertFrom-Json
  if ($record.serviceName -ne 'NileHopeFileGuardRecoveryPilot') { throw 'Not a recognized recovery pilot installation.' }
  $base=Assert-PilotLocalPath $record.pilotRoot
  $configPath=Join-Path $install 'recovery-config.json'
  $config=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
  foreach ($entry in @{protectedRoot='protected';repositoryRoot='repository';stateRoot='state'}.GetEnumerator()) {
    if ((Assert-PilotLocalPath $config.($entry.Key)) -ne (Join-Path $base $entry.Value)) { throw 'Pilot paths differ from the installer record. Review locally before continuing.' }
  }
  return @{Install=$install;Record=$record;Config=$config;ConfigPath=$configPath}
}
