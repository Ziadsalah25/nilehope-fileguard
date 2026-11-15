# Read-only. Queries only named servers; does not scan subnets, read file contents, or alter AD/GPO/ACLs.
param([string[]]$FileServers=@(), [string]$OutputDir=(Join-Path $PWD 'hospital-discovery'))
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$computer = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$ad = $null
$notes = @()
try {
  $domain = [DirectoryServices.ActiveDirectory.Domain]::GetComputerDomain()
  $ad = @{DnsRoot=$domain.Name; DomainControllers=@($domain.DomainControllers | ForEach-Object Name)}
} catch { $notes += 'AD discovery unavailable from this account/device.' }
$localShares = @()
try { $localShares = @(Get-SmbShare | Where-Object { -not $_.Special } | Select-Object Name,Path,Description) }
catch { $notes += 'Local SMB share inventory unavailable.' }
$mappedShares = @()
try { $mappedShares = @(Get-SmbMapping | Select-Object LocalPath,RemotePath,Status) }
catch { $notes += 'Mapped SMB share inventory unavailable for this Windows account.' }
$details = [ordered]@{
  ComputerName=$env:COMPUTERNAME; Domain=$computer.Domain; DomainJoined=$computer.PartOfDomain
  OperatingSystem=$os.Caption; OSVersion=$os.Version
  IPv4=@(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -ne '127.0.0.1'} | Select-Object IPAddress,InterfaceAlias)
  AD=$ad; LocalShares=$localShares; MappedShares=$mappedShares
  Python=@(Get-Command python.exe,py.exe -ErrorAction SilentlyContinue | Select-Object Name,Source)
  Notes=$notes
}
$details | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutputDir 'environment.json') -Encoding UTF8
$shares = @(); $failures = @()
# Always include this machine's non-administrative shares. Remote servers must be explicitly named.
foreach ($share in $localShares) {
  $shares += [pscustomobject]@{Server=$env:COMPUTERNAME;Name=$share.Name;Path="\\$env:COMPUTERNAME\$($share.Name)";LocalPath=$share.Path}
}
foreach ($mapping in $mappedShares) {
  $parts = $mapping.RemotePath.TrimStart('\') -split '\\',3
  if ($parts.Count -ge 2) {
    $shares += [pscustomobject]@{Server=$parts[0];Name=$parts[1];Path=$mapping.RemotePath;LocalPath=''}
  }
}
foreach ($server in ($FileServers | Sort-Object -Unique)) {
  $session = $null
  try {
    $session = New-CimSession -ComputerName $server
    foreach ($share in (Get-SmbShare -CimSession $session | Where-Object { -not $_.Special })) {
      $shares += [pscustomobject]@{Server=$server;Name=$share.Name;Path="\\$server\$($share.Name)";LocalPath=$share.Path}
    }
  } catch { $failures += "$server : $($_.Exception.Message)" }
  finally { if ($session) { Remove-CimSession $session } }
}
if ($shares.Count -gt 0) { $shares | Sort-Object Path -Unique | Export-Csv (Join-Path $OutputDir 'shares.csv') -NoTypeInformation -Encoding UTF8 }
else { 'Server,Name,Path,LocalPath' | Set-Content (Join-Path $OutputDir 'shares.csv') -Encoding UTF8 }
$failures | Set-Content (Join-Path $OutputDir 'share-discovery-errors.txt') -Encoding UTF8
Write-Host "Discovery saved to $OutputDir. Review before uploading environment.json and shares.csv. These contain internal hostnames and paths, not credentials or file contents."
