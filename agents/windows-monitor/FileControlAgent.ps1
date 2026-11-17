# Windows PowerShell 5.1+. Collects metadata; does not change share ACLs.
param(
  [Parameter(Mandatory=$true)][string]$Server,
  [string]$EnrollToken = '',
  [ValidateSet('pilot','ring20','ring50','all')][string]$Ring = 'pilot',
  [ValidateSet('workstation','fileserver')][string]$Role = 'workstation',
  [switch]$AllowInsecureLocalhost,
  [switch]$DirectConnection,
  [string]$StateDir=''
)
$ErrorActionPreference = 'Stop'
$Server = $Server.TrimEnd('/')
$uri = [uri]$Server
if ($uri.Scheme -ne 'https' -and -not ($AllowInsecureLocalhost -and $uri.IsLoopback)) {
  throw 'Use HTTPS with a certificate trusted by this computer.'
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if ($DirectConnection -and $PSVersionTable.PSVersion.Major -lt 6) {
  # Process-local setting for this explicit internal-console connection only.
  [Net.WebRequest]::DefaultWebProxy = $null
}
$Dir = if ($StateDir) { $StateDir } else { Join-Path $env:ProgramData 'FileControl' }
$KeyFile = Join-Path $Dir 'key.txt'
$CursorFile = Join-Path $Dir 'event-record.txt'
$ResultFile = Join-Path $Dir 'pending-result.json'
$UsbFile = Join-Path $Dir 'usb-before.json'
$LogFile = Join-Path $Dir 'agent.log'
$Device = $env:COMPUTERNAME
$script:Folders = @()
New-Item -ItemType Directory -Force $Dir | Out-Null
function Write-AgentLog($Message) {
  if ((Test-Path $LogFile) -and (Get-Item $LogFile).Length -gt 5MB) { Move-Item $LogFile "$LogFile.1" -Force }
  Add-Content $LogFile "$(Get-Date -Format s) $Message"
}
function Send($path, $body, $auth = $true, $method = 'Post') {
  $headers = @{}
  if ($auth) { $headers = @{ 'X-Device'=$Device; 'X-Api-Key'=(Get-Content $KeyFile -Raw).Trim() } }
  $params = @{ Method=$method; Uri="$Server$path"; Headers=$headers; TimeoutSec=20 }
  if ($DirectConnection -and $PSVersionTable.PSVersion.Major -ge 6) { $params.NoProxy=$true }
  if ($method -eq 'Post') {
    $params.ContentType = 'application/json; charset=utf-8'
    $params.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6 -Compress))
  }
  Invoke-RestMethod @params
}
function Ensure-Enrolled {
  if (Test-Path $KeyFile) { return }
  $token = $EnrollToken
  $tokenFile = Join-Path $Dir 'enroll-token.txt'
  if (-not $token -and (Test-Path $tokenFile)) { $token = (Get-Content $tokenFile -Raw).Trim() }
  if (-not $token) { throw 'Enrollment token missing. Re-run the installer with -EnrollToken.' }
  $r = Send '/api/agent/enroll' @{token=$token;hostname=$Device;ring=$Ring} $false
  Set-Content $KeyFile $r.key -NoNewline
  if (Test-Path $tokenFile) { Remove-Item $tokenFile -Force }
}
function Flush-Result {
  if (Test-Path $ResultFile) {
    $result = Get-Content $ResultFile -Raw | ConvertFrom-Json
    Send '/api/agent/command-result' $result | Out-Null
    Remove-Item $ResultFile -Force
  }
}
function Process-Command($cmd) {
  if (-not $cmd) { return }
  $output = ''; $success = $true
  try {
    switch ($cmd.command) {
      'sync_policy' {
        $output = (& gpupdate.exe /target:computer /force /wait:60 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) { throw "gpupdate returned $LASTEXITCODE. $output" }
      }
      'lock_usb' {
        $reg = 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR'
        if (-not (Test-Path $UsbFile)) {
          @{Start=(Get-ItemProperty $reg -Name Start).Start} | ConvertTo-Json | Set-Content $UsbFile
        }
        Set-ItemProperty $reg -Name Start -Value 4
        $output = 'USBSTOR startup set to disabled. Already connected devices may remain usable until reconnect/reboot.'
      }
      'restore_usb' {
        if (-not (Test-Path $UsbFile)) { throw 'No saved USBSTOR setting. Automatic restore is unavailable.' }
        $previous = (Get-Content $UsbFile -Raw | ConvertFrom-Json).Start
        Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR' -Name Start -Value ([int]$previous)
        Remove-Item $UsbFile -Force
        $output = "USBSTOR startup restored to saved value $previous. Domain policy may override it."
      }
      'isolate_smb' {
        if ($Role -ne 'fileserver') { throw 'SMB disconnection is supported only on a file-server agent.' }
        $sessions = @(Get-SmbSession)
        $sessions | Close-SmbSession -Force
        $output = "Closed $($sessions.Count) active SMB sessions. Clients may reconnect; this is not persistent network isolation."
      }
      'collect_logs' {
        $output = (Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5145} -MaxEvents 3 |
          Select-Object TimeCreated,Id,RecordId,MachineName | ConvertTo-Json -Compress)
      }
      default { throw 'Unsupported command.' }
    }
  } catch { $success = $false; $output = "Command failed: $($_.Exception.Message)" }
  @{command_id=[int]$cmd.id;output=[string]$output;success=$success} |
    ConvertTo-Json -Depth 4 | Set-Content $ResultFile -Encoding UTF8
  Flush-Result
}
function Refresh-Config {
  $config = Send '/api/agent/config' $null $true 'Get'
  $script:Folders = @($config.folders)
}
function Heartbeat {
  $nic = Get-NetAdapter | Where-Object Status -eq 'Up' | Sort-Object -Property @{Expression='HardwareInterface';Descending=$true},InterfaceIndex | Select-Object -First 1
  $ip = $null
  if ($nic) { $ip = (Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 | Select-Object -First 1).IPAddress }
  $user = (Get-CimInstance Win32_ComputerSystem).UserName
  $body = @{win_user=$user;ip=$ip;mac=$nic.MacAddress;agent_version='1.3.0';os_family='windows';architecture=$env:PROCESSOR_ARCHITECTURE}
  try {
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$env:SystemDrive'"
    $body.os_version = "$($os.Caption) $($os.Version)"
    if ($null -ne $cpu) { $body.cpu_percent = [Math]::Round([double]$cpu,1) }
    $body.memory_total_mb = [long][Math]::Floor($os.TotalVisibleMemorySize / 1024)
    $body.memory_used_mb = [long][Math]::Floor(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory) / 1024)
    if ($disk) {
      $body.disk_total_mb = [long][Math]::Floor($disk.Size / 1MB)
      $body.disk_used_mb = [long][Math]::Floor(($disk.Size-$disk.FreeSpace) / 1MB)
    }
    $body.uptime_seconds = [long](((Get-Date)-$os.LastBootUpTime).TotalSeconds)
    $body.monitoring_status = 'healthy'
    $body.monitoring_message = $(if ($Role -eq 'fileserver') {'Windows inventory and configured SMB audit scope.'} else {'Windows inventory and system health; no file restrictions are applied by monitoring.'})
  } catch {
    $body.monitoring_status = 'partial'
    $body.monitoring_message = 'Heartbeat is available; some Windows health metrics could not be read.'
  }
  $resp = Send '/api/agent/heartbeat' $body
  Process-Command $resp.command
}
function In-Scope($path) {
  # Compare share and relative path; FQDN/NetBIOS host spelling can differ.
  $relative = ($path -split '\\',4)[3]
  foreach ($root in $script:Folders) {
    $base = (($root -split '\\',4)[3]).TrimEnd('\')
    if ($relative.Equals($base,[StringComparison]::OrdinalIgnoreCase) -or
        $relative.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)) { return $true }
  }
  return $false
}
function Forward-Events {
  if ($script:Folders.Count -eq 0) { return }
  if (Test-Path $CursorFile) {
    $last = [long](Get-Content $CursorFile -Raw).Trim()
    $newest = Get-WinEvent -LogName Security -MaxEvents 1
    if ($newest.RecordId -lt $last) { throw 'Security log was cleared. Review the log and reset event-record.txt manually.' }
    $filter = "*[System[EventID=5145 and EventRecordID > $last]]"
  } else {
    $last = 0
    $filter = '*[System[EventID=5145 and TimeCreated[timediff(@SystemTime) <= 120000]]]'
  }
  $found = @()
  try { $found = @(Get-WinEvent -LogName Security -FilterXPath $filter -Oldest -MaxEvents 200) }
  catch { if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }; return }
  $events = @()
  foreach ($event in $found) {
    $data = @{}
    ([xml]$event.ToXml()).Event.EventData.Data | ForEach-Object { $data[$_.Name] = $_.'#text' }
    if ($data['AccessList'] -notmatch '%%1537' -and (([Convert]::ToInt64(($data['AccessMask'] -replace '^0x',''),16) -band 0x10000) -eq 0)) { continue }
    $share = ($data['ShareName'] -split '\\')[-1]
    $path = "\\$Device\$share\$($data['RelativeTargetName'])".TrimEnd('\')
    if (-not (In-Scope $path)) { continue }
    $events += @{
      ts=$event.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');win_user=$data['SubjectUserName']
      ip=$data['IpAddress'];action='Delete access check';file=$path;process='SMB'
      result=$(if (($event.Keywords -band 0x0010000000000000) -ne 0) {'blocked'} else {'allowed'})
    }
  }
  if ($events.Count -gt 0) { Send '/api/agent/events' @{events=@($events)} | Out-Null }
  # Commit cursor only after the whole batch was acknowledged. These are access checks, not proof of deletion.
  if ($found.Count -gt 0) { Set-Content $CursorFile ([string]$found[-1].RecordId) }
}
function Probe {
  $deleteRights = [Security.AccessControl.FileSystemRights]'Delete,DeleteSubdirectoriesAndFiles'
  foreach ($folder in $script:Folders) {
    $result = 'review_required'
    try {
      $acl = Get-Acl -LiteralPath $folder
      $risky = @($acl.Access | Where-Object {
        $_.AccessControlType -eq 'Allow' -and
        $_.IdentityReference.Value -match 'Domain Users|Authenticated Users|Everyone|BUILTIN\\Users|Staff' -and
        ($_.FileSystemRights -band $deleteRights)
      })
      if ($risky.Count -gt 0) { $result = 'broad_delete_detected' }
    } catch { $result = 'unreadable' }
    Send '/api/agent/probe' @{folder=$folder;result=$result} | Out-Null
  }
}
$tick = 0
while ($true) {
  try {
    Ensure-Enrolled
    Flush-Result
    if ($tick % 2 -eq 0) { Refresh-Config }
    Heartbeat
    if ($Role -eq 'fileserver') {
      Forward-Events
      if ($tick % 120 -eq 0) { Probe }
    }
  } catch { Write-AgentLog $_.Exception.Message }
  $tick++
  Start-Sleep -Seconds 30
}
