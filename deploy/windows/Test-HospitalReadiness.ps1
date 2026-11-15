# Read-only preflight. No app/process command lines, credentials, registry writes or file contents are collected.
param([string]$OutputPath=(Join-Path ([Environment]::GetFolderPath('Desktop')) 'hospital-readiness.json'))
$ErrorActionPreference='Stop'
$report=[ordered]@{Computer=$env:COMPUTERNAME;ExpectedServer='EXAMPLE-FILE01';Timestamp=(Get-Date).ToUniversalTime().ToString('o')}
$report.OS=(Get-CimInstance Win32_OperatingSystem).Caption
$pc=Get-CimInstance Win32_ComputerSystem
$report.Domain=$pc.Domain
$report.DomainJoined=$pc.PartOfDomain
$os=Get-CimInstance Win32_OperatingSystem
$report.Memory=@{TotalKiB=$os.TotalVisibleMemorySize;FreeKiB=$os.FreePhysicalMemory}
$report.ExpectedHost=($env:COMPUTERNAME -ieq 'EXAMPLE-FILE01')
$report.IPv4=@(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
$report.Python=@(Get-Command python.exe,py.exe -ErrorAction SilentlyContinue | Select-Object Name,Source)
$report.Caddy=@(Get-Command caddy.exe -ErrorAction SilentlyContinue | Select-Object Name,Source)
$report.ExistingPaths=@('C:\FileControlCenter\fcc',"$env:ProgramData\NileHopeDLP","$env:ProgramData\FileControl" | ForEach-Object {
  [pscustomobject]@{Path=$_;Exists=(Test-Path -LiteralPath $_)}
})
$report.Shares=@(Get-SmbShare -ErrorAction SilentlyContinue | Where-Object {-not $_.Special} | Select-Object Name,Path)
$report.EPathExists=Test-Path -LiteralPath 'E:\'
$report.ReadinessWarnings=@()
try {
  $report.Listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -in @(443,8000,5000,3306)} | ForEach-Object {
    $name=$null
    try {$name=(Get-Process -Id $_.OwningProcess -ErrorAction Stop).ProcessName} catch {}
    [pscustomobject]@{Address=$_.LocalAddress;Port=$_.LocalPort;PID=$_.OwningProcess;Process=$name}
  })
} catch {$report.ReadinessWarnings += 'Listener inventory unavailable; rerun elevated.'}
try {
  $report.ExistingTasks=@(Get-ScheduledTask -ErrorAction Stop | Where-Object {$_.TaskName -match 'NileHope|FileControl|DLP'} | Select-Object TaskName,TaskPath,State)
} catch {$report.ReadinessWarnings += 'Scheduled task inventory unavailable.'}
$report.RelevantServices=@(Get-Service | Where-Object {$_.Name -match 'caddy|postgres|mysql|w3svc|filecontrol|nilehope' -or $_.DisplayName -match 'FileControl|NileHope'} | Select-Object Name,DisplayName,Status)
try {$report.ConsoleDns=@(Resolve-DnsName 'fileguard.example.local' -Type A -ErrorAction Stop | Where-Object IPAddress | Select-Object -ExpandProperty IPAddress)}
catch {$report.ReadinessWarnings += 'Console hostname did not resolve.'}
try {
  $root=[ADSI]'LDAP://RootDSE'
  $report.AD=[ordered]@{DefaultNamingContext=[string]$root.defaultNamingContext;DnsHostName=[string]$root.dnsHostName}
} catch {$report.ReadinessWarnings += 'Read-only AD RootDSE lookup unavailable.'}
$report.Disks=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace)
$report | ConvertTo-Json -Depth 7 | Set-Content $OutputPath -Encoding UTF8
Write-Host "Saved $OutputPath. Review it before uploading. No installation or configuration changes were made."
