#Requires -RunAsAdministrator
<#
.SYNOPSIS
Switches an installed Windows console from the legacy Caddy proxy to direct TLS.
.DESCRIPTION
Backs up runtime.json, issues a server certificate from the local FileGuard CA,
stops and disables the legacy proxy task, starts the application server with TLS,
and validates /healthz using normal certificate verification. If validation fails,
the prior runtime configuration and running proxy task are restored. An optional
firewall rule is restricted to one supplied IPv4 client address.
#>
[CmdletBinding()]
param(
  [string]$InstallDir = "$env:ProgramData\NileHopeDLP",
  [Parameter(Mandatory=$true)][string]$BindAddress,
  [Parameter(Mandatory=$true)][uri]$PublicConsoleUrl,
  [int]$HttpsPort = 443,
  [string]$AllowClientIp = '',
  [string]$FirewallRuleName = 'NileHopeDLP-DirectHTTPS-Test'
)
$ErrorActionPreference = 'Stop'

$runtimePath = Join-Path $InstallDir 'runtime.json'
$python = Join-Path $InstallDir '.venv\Scripts\python.exe'
$issueScript = Join-Path $InstallDir 'deploy\windows\issue_server_certificate.py'
$webTask = 'NileHopeDLP-Web'
$workerTask = 'NileHopeDLP-Worker'
$proxyTask = 'NileHopeDLP-Proxy'
$caDir = Join-Path $InstallDir 'data\caddy\caddy\pki\authorities\local'
$caCertificate = Join-Path $caDir 'root.crt'
$caPrivateKey = Join-Path $caDir 'root.key'
$tlsDir = Join-Path $InstallDir 'data\tls'
$serverCertificate = Join-Path $tlsDir 'server.crt'
$serverPrivateKey = Join-Path $tlsDir 'server.key'
$rootDerCertificate = Join-Path $tlsDir 'root-ca-public.cer'
$healthUrl = $PublicConsoleUrl.GetLeftPart([UriPartial]::Authority).TrimEnd('/') + '/healthz'
$backupDir = Join-Path $InstallDir ('backups\direct-https-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$ruleAdded = $false

if (-not (Test-Path -LiteralPath $runtimePath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $issueScript -PathType Leaf) -or
    -not (Test-Path -LiteralPath $caCertificate -PathType Leaf) -or
    -not (Test-Path -LiteralPath $caPrivateKey -PathType Leaf)) {
  throw 'The installed console, certificate authority, or direct HTTPS dependencies are missing.'
}
if ($PublicConsoleUrl.Scheme -ne 'https' -or $PublicConsoleUrl.Port -ne $HttpsPort -or
    $PublicConsoleUrl.Query -or $PublicConsoleUrl.Fragment) {
  throw 'PublicConsoleUrl must be an HTTPS origin whose port matches HttpsPort.'
}
$bindIp = $null
if (-not [Net.IPAddress]::TryParse($BindAddress, [ref]$bindIp) -or
    $bindIp.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
    $bindIp.Equals([Net.IPAddress]::Any) -or $bindIp.Equals([Net.IPAddress]::Loopback) -or
    -not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress $BindAddress -ErrorAction SilentlyContinue)) {
  throw 'BindAddress must be this server LAN IPv4 address.'
}
if ($AllowClientIp) {
  $clientIp = $null
  if (-not [Net.IPAddress]::TryParse($AllowClientIp, [ref]$clientIp) -or
      $clientIp.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
      $clientIp.Equals([Net.IPAddress]::Any) -or $clientIp.Equals([Net.IPAddress]::Loopback)) {
    throw 'AllowClientIp must be one exact client IPv4 address.'
  }
}
foreach ($task in @($webTask,$workerTask)) {
  if (-not (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue)) { throw "Required task $task is missing." }
}

New-Item -ItemType Directory -Force $backupDir | Out-Null
Copy-Item -LiteralPath $runtimePath -Destination (Join-Path $backupDir 'runtime.json')
$proxyWasRunning = $false
$proxy = Get-ScheduledTask -TaskName $proxyTask -ErrorAction SilentlyContinue
if ($proxy) { $proxyWasRunning = $proxy.State -eq 'Running' }
$rootKeyAcl = Get-Acl -LiteralPath $caPrivateKey
Set-Content -LiteralPath (Join-Path $backupDir 'ca-root-key-acl.sddl') -Value $rootKeyAcl.Sddl -Encoding ASCII

try {
  New-Item -ItemType Directory -Force $tlsDir | Out-Null
  & $python $issueScript --ca-certificate $caCertificate --ca-private-key $caPrivateKey `
    --server-name $PublicConsoleUrl.DnsSafeHost --certificate-output $serverCertificate `
    --private-key-output $serverPrivateKey --valid-days 365
  if ($LASTEXITCODE -ne 0) { throw 'Could not issue the direct HTTPS server certificate.' }

  & icacls.exe $tlsDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-19:(OI)(CI)RX' | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the TLS private-key directory.' }

  $pem = Get-Content -LiteralPath $caCertificate -Raw
  $base64 = $pem -replace '-----BEGIN CERTIFICATE-----|-----END CERTIFICATE-----|\s', ''
  [IO.File]::WriteAllBytes($rootDerCertificate, [Convert]::FromBase64String($base64))
  $rootCert = [Security.Cryptography.X509Certificates.X509Certificate2]::new($rootDerCertificate)
  $trusted = Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $rootCert.Thumbprint
  if (-not $trusted) {
    Import-Certificate -FilePath $rootDerCertificate -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
  }

  $config = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
  $config | Add-Member -Force -NotePropertyName TLS_CERTIFICATE_FILE -NotePropertyValue $serverCertificate
  $config | Add-Member -Force -NotePropertyName TLS_PRIVATE_KEY_FILE -NotePropertyValue $serverPrivateKey
  $config | Add-Member -Force -NotePropertyName TLS_BIND_ADDRESS -NotePropertyValue $BindAddress
  $config | Add-Member -Force -NotePropertyName TLS_PORT -NotePropertyValue ([string]$HttpsPort)
  $config | Add-Member -Force -NotePropertyName PUBLIC_CONSOLE_URL -NotePropertyValue ($PublicConsoleUrl.GetLeftPart([UriPartial]::Authority).TrimEnd('/'))

  foreach ($task in @($webTask,$proxyTask)) {
    if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $task }
  }
  if ($proxy) { Disable-ScheduledTask -TaskName $proxyTask | Out-Null }
  $deadline = (Get-Date).AddSeconds(20)
  do {
    $oldListener = Get-NetTCPConnection -LocalAddress $BindAddress -LocalPort $HttpsPort -State Listen -ErrorAction SilentlyContinue
    if (-not $oldListener) { break }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)
  if ($oldListener) { throw "TCP $HttpsPort is still occupied on $BindAddress after stopping the old proxy." }
  $config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $runtimePath -Encoding UTF8
  Start-ScheduledTask -TaskName $webTask
  $deadline = (Get-Date).AddSeconds(30)
  do {
    $newListener = Get-NetTCPConnection -LocalAddress $BindAddress -LocalPort $HttpsPort -State Listen -ErrorAction SilentlyContinue
    if ($newListener) { break }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  if (-not $newListener) { throw "Direct HTTPS did not listen on $BindAddress`:$HttpsPort." }

  $healthCode = & $python -c 'import ssl,sys,urllib.request; c=ssl.create_default_context(cafile=sys.argv[2]); r=urllib.request.urlopen(sys.argv[1],context=c,timeout=12); print(r.status); print(r.read().decode())' $healthUrl $caCertificate
  if ($LASTEXITCODE -ne 0 -or ($healthCode -join "`n") -notmatch '200\s+\{"ok":true\}') {
    throw "Direct HTTPS health check failed: $($healthCode -join ' ')"
  }

  if ($AllowClientIp) {
    if (Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue) {
      throw "Firewall rule $FirewallRuleName already exists; inspect it before retrying."
    }
    New-NetFirewallRule -Name $FirewallRuleName -DisplayName 'NileHope FileGuard direct HTTPS test device' `
      -Description 'Temporary LAN test access for one explicitly selected client IPv4 address.' `
      -Direction Inbound -Action Allow -Enabled True -Profile Domain -Protocol TCP `
      -LocalAddress $BindAddress -LocalPort $HttpsPort -RemoteAddress $AllowClientIp `
      -Program $python | Out-Null
    $ruleAdded = $true
  }

  # Once the proxy is stopped, keep the CA private key unavailable to the web task.
  & icacls.exe $caPrivateKey /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the CA private key after issuing the server certificate.' }

  [pscustomobject]@{
    Result='Direct HTTPS active'
    Health=($healthCode -join ' ')
    CertificateThumbprint=$rootCert.Thumbprint
    ServerUrl=$PublicConsoleUrl.GetLeftPart([UriPartial]::Authority)
    ProxyTask=$(if ($proxy) { (Get-ScheduledTask -TaskName $proxyTask).State } else { 'Not installed' })
    FirewallRule=$(if ($AllowClientIp) { $FirewallRuleName } else { 'Not changed' })
    Backup=$backupDir
  } | Format-List
}
catch {
  if ($ruleAdded) { Remove-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue }
  if ($rootKeyAcl) { Set-Acl -LiteralPath $caPrivateKey -AclObject $rootKeyAcl -ErrorAction SilentlyContinue }
  Stop-ScheduledTask -TaskName $webTask -ErrorAction SilentlyContinue
  Copy-Item -LiteralPath (Join-Path $backupDir 'runtime.json') -Destination $runtimePath -Force
  if ($proxyWasRunning) {
    Enable-ScheduledTask -TaskName $proxyTask -ErrorAction SilentlyContinue | Out-Null
    Start-ScheduledTask -TaskName $proxyTask -ErrorAction SilentlyContinue
  }
  Start-ScheduledTask -TaskName $webTask -ErrorAction SilentlyContinue
  throw
}
