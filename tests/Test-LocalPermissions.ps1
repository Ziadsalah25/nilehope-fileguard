# Exercise the actual Windows ACL operation on disposable files, without Docker.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'deploy\local\Local-Permissions.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('fileguard permissions '+[guid]::NewGuid().ToString('N'))
$currentSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowedSids=@(@($currentSid,'S-1-5-18','S-1-5-32-544') | Select-Object -Unique)
$fullControl=[Security.AccessControl.FileSystemRights]::FullControl
$allow=[Security.AccessControl.AccessControlType]::Allow
function Assert-Permission($condition,[string]$message) {
  if (-not $condition) { throw $message }
}
function Assert-PrivateAcl([string]$target,[bool]$directory) {
  $acl=Get-Acl -LiteralPath $target
  Assert-Permission $acl.AreAccessRulesProtected 'Configuration must not inherit broader parent-directory access.'
  $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
  foreach ($rule in $rules) {
    Assert-Permission ($allowedSids -contains $rule.IdentityReference.Value) 'Unexpected identity can access protected configuration.'
    Assert-Permission ($rule.AccessControlType -eq $allow -and -not $rule.IsInherited) 'Expected only explicit allow rules.'
  }
  foreach ($sid in $allowedSids) {
    $matching=@($rules | Where-Object { $_.IdentityReference.Value -eq $sid })
    Assert-Permission ($matching.Count -eq 1) ('Expected one explicit permission for SID '+$sid)
    Assert-Permission (($matching[0].FileSystemRights -band $fullControl) -eq $fullControl) 'Owner/System/Administrators must retain full control.'
    if ($directory) {
      $inherit=[Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
      Assert-Permission (($matching[0].InheritanceFlags -band $inherit) -eq $inherit) 'Private-directory permissions must protect newly created children.'
    }
  }
}
try {
  New-Item -ItemType Directory -Path $testRoot | Out-Null
  $private=Join-Path $testRoot '.local'
  New-Item -ItemType Directory -Path $private | Out-Null
  Protect-FileGuardLocalPath -LiteralPath $private -Directory
  Assert-PrivateAcl $private $true
  Write-Output 'PASS: actual current-user SID grant, protected directory, and path containing spaces'

  $inherited=Join-Path $private 'login.txt'
  [IO.File]::WriteAllText($inherited,'Disposable fixture, no actual login details.')
  $childRules=@((Get-Acl -LiteralPath $inherited).GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
  Assert-Permission (@($childRules | Where-Object { $allowedSids -notcontains $_.IdentityReference.Value }).Count -eq 0) 'Private children must not inherit unrelated users.'
  Assert-Permission (@($childRules | Where-Object { $_.IdentityReference.Value -eq $currentSid }).Count -gt 0) 'Current user must be able to read generated login details.'
  Write-Output 'PASS: generated login files inherit restricted access'

  $environmentFile=Join-Path $testRoot '.env'
  [IO.File]::WriteAllText($environmentFile,'DISPOSABLE_TEST_VALUE=unchanged')
  $before=(Get-FileHash -LiteralPath $environmentFile -Algorithm SHA256).Hash
  Protect-FileGuardLocalPath -LiteralPath $environmentFile
  Assert-PrivateAcl $environmentFile $false
  Assert-Permission ((Get-FileHash -LiteralPath $environmentFile -Algorithm SHA256).Hash -eq $before) 'Protecting .env must preserve its contents.'
  Write-Output 'PASS: real .env ACL application preserves configuration contents'

  Protect-FileGuardLocalPath -LiteralPath $private -Directory
  Protect-FileGuardLocalPath -LiteralPath $environmentFile
  Assert-PrivateAcl $private $true
  Assert-PrivateAcl $environmentFile $false
  Assert-Permission ((Get-FileHash -LiteralPath $environmentFile -Algorithm SHA256).Hash -eq $before) 'Rerunning startup must preserve existing credentials.'
  Write-Output 'PASS: permission application is repeatable and preserves existing files'
  Write-Output '4 native Windows permission checks passed.'
} finally {
  Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
