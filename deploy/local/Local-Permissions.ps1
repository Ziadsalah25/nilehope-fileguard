# Protect local configuration using numeric SIDs, independent of account names/language.
function Protect-FileGuardLocalPath {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$LiteralPath,
    [switch]$Directory
  )
  $identitySid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
  $permissions=if ($Directory) {'(OI)(CI)F'} else {'(F)'}
  $icaclsPath=Join-Path $env:SystemRoot 'System32\icacls.exe'
  # icacls requires '*' before every numeric SID; without it, SID text is
  # interpreted as an account name and fails with "No mapping ... was done".
  & $icaclsPath $LiteralPath /inheritance:r /grant:r "*${identitySid}:$permissions" "*S-1-5-18:$permissions" "*S-1-5-32-544:$permissions" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Could not protect local configuration path: $LiteralPath (icacls exit $LASTEXITCODE)." }
}
