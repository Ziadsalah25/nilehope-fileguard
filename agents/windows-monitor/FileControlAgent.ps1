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
$CorrelationFile = Join-Path $Dir 'event-correlation.json'
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
  $adapters = @(Get-NetAdapter | Where-Object Status -eq 'Up' | Sort-Object -Property @{Expression='HardwareInterface';Descending=$true},InterfaceIndex)
  $upIndexes = @($adapters | ForEach-Object { $_.ifIndex })
  $ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $upIndexes -contains $_.InterfaceIndex -and $_.IPAddress -ne '0.0.0.0' -and
    $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*'
  } | Sort-Object InterfaceIndex | Select-Object -ExpandProperty IPAddress -Unique | Select-Object -First 16)
  $nic = $adapters | Select-Object -First 1
  $ip = if ($ips.Count -gt 0) { $ips[0] } else { $null }
  if ($nic) {
    $nicIps = @(Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 | Where-Object {
      $_.IPAddress -ne '0.0.0.0' -and $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*'
    } | Select-Object -ExpandProperty IPAddress)
    if ($nicIps.Count -gt 0) { $ip = $nicIps[0] }
  }
  $user = (Get-CimInstance Win32_ComputerSystem).UserName
  $body = @{win_user=$user;ip=$ip;ips=$ips;mac=$nic.MacAddress;agent_version='1.3.1';os_family='windows';architecture=$env:PROCESSOR_ARCHITECTURE}
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
function Get-EventData($event) {
  $data = @{}
  ([xml]$event.ToXml()).Event.EventData.Data | ForEach-Object { $data[$_.Name] = $_.'#text' }
  return $data
}
function Has-DeleteRight($mask, $accessList = '') {
  if ([string]$accessList -match '%%1537') { return $true }
  if ([string]$mask -notmatch '^(0[xX])?[0-9a-fA-F]+$') { return $false }
  try {
    $text = ([string]$mask) -replace '^0[xX]',''
    $value = [Convert]::ToInt64($text,16)
    return (($value -band 0x10000) -ne 0 -or ($value -band 0x40) -ne 0)
  } catch { return $false }
}
function Event-Result($event) {
  if (($event.Keywords -band 0x0010000000000000) -ne 0) { return 'blocked' }
  return 'allowed'
}
function To-SharePath($localPath) {
  if (-not $localPath) { return $null }
  try { $physical = [IO.Path]::GetFullPath(([string]$localPath).Trim()).TrimEnd('\') }
  catch { return $null }
  foreach ($root in $script:Folders) {
    $parts = $root.TrimStart('\') -split '\\',3
    if ($parts.Count -lt 2) { continue }
    $shareName = $parts[1]
    $subPath = if ($parts.Count -gt 2) { $parts[2] } else { '' }
    $share = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $share -or -not $share.Path) { continue }
    $physicalRoot = [string]$share.Path
    if ($subPath) { $physicalRoot = Join-Path $physicalRoot ($subPath -replace '\\',[IO.Path]::DirectorySeparatorChar) }
    try { $physicalRoot = [IO.Path]::GetFullPath($physicalRoot).TrimEnd('\') }
    catch { continue }
    if ($physical.Equals($physicalRoot,[StringComparison]::OrdinalIgnoreCase)) { $relative = '' }
    elseif ($physical.StartsWith($physicalRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { $relative = $physical.Substring($physicalRoot.Length).TrimStart('\') }
    else { continue }
    $mapped = "\\$Device\$shareName"
    if ($subPath) { $mapped += '\' + $subPath }
    if ($relative) { $mapped += '\' + $relative }
    if (In-Scope $mapped) { return $mapped }
  }
  return $null
}
function Read-CorrelationState {
  $state = @{share_checks=@();handles=@()}
  if (-not (Test-Path $CorrelationFile)) { return $state }
  try {
    $saved = Get-Content $CorrelationFile -Raw | ConvertFrom-Json
    $state.share_checks = @($saved.share_checks)
    $state.handles = @($saved.handles)
  } catch { Write-AgentLog 'Ignoring unreadable event-correlation cache.' }
  return $state
}
function Trim-CorrelationState($state) {
  $cutoff = [DateTime]::UtcNow.AddHours(-12)
  $state.share_checks = @($state.share_checks | Where-Object {
    try { [DateTime]::Parse([string]$_.ts).ToUniversalTime() -ge $cutoff } catch { $false }
  } | Select-Object -Last 5000)
  $state.handles = @($state.handles | Where-Object {
    try { [DateTime]::Parse([string]$_.ts).ToUniversalTime() -ge $cutoff } catch { $false }
  } | Select-Object -Last 5000)
}
function Find-ShareCheck($state, $logonId, $path, $eventTime) {
  if (-not $logonId -or -not $path) { return $null }
  $matches = @($state.share_checks | Where-Object {
    if ([string]$_.logon_id -ne [string]$logonId -or -not ([string]$_.file).Equals([string]$path,[StringComparison]::OrdinalIgnoreCase)) { return $false }
    try { [Math]::Abs(($eventTime - [DateTime]::Parse([string]$_.ts).ToUniversalTime()).TotalSeconds) -le 600 }
    catch { $false }
  } | Sort-Object -Property ts -Descending)
  if ($matches.Count -gt 0) { return $matches[0] }
  return $null
}
function Forward-Events {
  if ($script:Folders.Count -eq 0) { return }
  if (Test-Path $CursorFile) {
    $last = [long](Get-Content $CursorFile -Raw).Trim()
    $newest = Get-WinEvent -LogName Security -MaxEvents 1
    if ($newest.RecordId -lt $last) { throw 'Security log was cleared. Review the log and reset event-record.txt manually.' }
    $filter = "*[System[(EventID=5145 or EventID=4656 or EventID=4663 or EventID=4660) and EventRecordID > $last]]"
  } else {
    $last = 0
    $filter = '*[System[(EventID=5145 or EventID=4656 or EventID=4663 or EventID=4660) and TimeCreated[timediff(@SystemTime) <= 120000]]]'
  }
  $found = @()
  try { $found = @(Get-WinEvent -LogName Security -FilterXPath $filter -Oldest -MaxEvents 200) }
  catch { if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }; return }
  $events = @()
  $state = Read-CorrelationState
  foreach ($event in $found) {
    $data = Get-EventData $event
    $eventTime = $event.TimeCreated.ToUniversalTime()
    $timestamp = $eventTime.ToString('o')
    $logonId = [string]$data['SubjectLogonId']
    $handleId = [string]$data['HandleId']
    $user = [string]$data['SubjectUserName']
    if ($data['SubjectDomainName'] -and $data['SubjectDomainName'] -ne '-' -and $user) { $user = "$($data['SubjectDomainName'])\$user" }
    $path = $null
    $shareName = $null
    $sourceIp = $null
    $result = Event-Result $event
    $action = $null
    $accessMask = if ([string]$data['AccessMask']) { [string]$data['AccessMask'] } else { $null }

    if ($event.Id -eq 5145) {
      $shareName = [string]$data['ShareName']
      $shareName = ($shareName -split '\\' | Where-Object { $_ } | Select-Object -Last 1)
      if (-not $shareName) { continue }
      $relative = ([string]$data['RelativeTargetName']).TrimStart('\')
      $path = "\\$Device\$shareName"
      if ($relative) { $path += '\' + $relative }
      if (-not (In-Scope $path)) { continue }
      $sourceIp = [string]$data['IpAddress']
      # Cache every in-scope SMB check so file-system records can be linked to the
      # same server logon session and exact path. Only delete checks are displayed.
      if ($logonId) {
        $state.share_checks += @{logon_id=$logonId;file=$path;ip=$sourceIp;win_user=$user;ts=$timestamp}
      }
      if (-not (Has-DeleteRight $accessMask $data['AccessList'])) { continue }
      $action = 'Delete access check'
    } elseif ($event.Id -eq 4656 -or $event.Id -eq 4663) {
      $path = To-SharePath $data['ObjectName']
      if (-not $path -or -not (In-Scope $path)) { continue }
      if (-not (Has-DeleteRight $accessMask)) { continue }
      $action = if ($event.Id -eq 4656) { 'Delete right requested' } else { 'Delete right used' }
      $related = Find-ShareCheck $state $logonId $path $eventTime
      if ($related) {
        $sourceIp = [string]$related.ip
        if ($related.win_user) { $user = [string]$related.win_user }
      }
      if ($handleId -and $logonId) {
        $state.handles = @($state.handles | Where-Object { [string]$_.key -ne "$logonId|$handleId" })
        $state.handles += @{key="$logonId|$handleId";logon_id=$logonId;handle_id=$handleId;file=$path;share_name=(($path.TrimStart('\') -split '\\')[1]);win_user=$user;ts=$timestamp}
      }
    } elseif ($event.Id -eq 4660) {
      if (-not $handleId -or -not $logonId) { continue }
      $handle = $state.handles | Where-Object { [string]$_.key -eq "$logonId|$handleId" } | Select-Object -Last 1
      if (-not $handle) { continue }
      $path = [string]$handle.file
      if (-not (In-Scope $path)) { continue }
      $shareName = [string]$handle.share_name
      $user = if ($handle.win_user) { [string]$handle.win_user } else { $user }
      $related = Find-ShareCheck $state $logonId $path $eventTime
      if ($related) { $sourceIp = [string]$related.ip }
      $action = 'File deleted'
      $result = 'observed'
      $state.handles = @($state.handles | Where-Object { [string]$_.key -ne "$logonId|$handleId" })
    }

    if (-not $action -or -not $path) { continue }
    $events += @{
      event_id="wse-record-$($event.RecordId)";source_event_id=[int]$event.Id;record_id=[string]$event.RecordId
      logon_id=$(if ($logonId) { $logonId } else { $null });handle_id=$(if ($handleId) { $handleId } else { $null })
      access_mask=$accessMask;share_name=$(if ($shareName) { $shareName } else { $null })
      ts=$timestamp;win_user=$user;ip=$sourceIp;action=$action;file=$path;process='SMB';result=$result
    }
  }
  if ($events.Count -gt 0) { Send '/api/agent/events' @{events=@($events)} | Out-Null }
  # Cache and cursor commit only after the complete event batch was acknowledged.
  Trim-CorrelationState $state
  $state | ConvertTo-Json -Depth 6 | Set-Content $CorrelationFile -Encoding UTF8
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

