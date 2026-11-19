#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][uri]$PublicConsoleUrl,
  [Parameter(Mandatory=$true)][string]$BindAddress,
  [Parameter(Mandatory=$true)][string]$TlsCertificatePath,
  [Parameter(Mandatory=$true)][string]$TlsPrivateKeyPath,
  [int]$HttpsPort = 443,
  [string]$PythonPath = 'python.exe',
  [string]$InstallDir = "$env:ProgramData\NileHopeDLP",
  [string]$DatabaseUrl = '',
  [switch]$EnableRemoteCommands,
  [switch]$EnableDirectoryApprovals,
  [string]$LdapUri = '',
  [string]$LdapBindDn = '',
  [string]$LdapBaseDn = '',
  [string]$AdGroupBase = '',
  [string]$LdapCaCertificate = ''
)
$ErrorActionPreference = 'Stop'
if ($PublicConsoleUrl.Scheme -ne 'https' -or $PublicConsoleUrl.Port -ne $HttpsPort -or $PublicConsoleUrl.Query -or $PublicConsoleUrl.Fragment) {
  throw 'PublicConsoleUrl must be an HTTPS origin whose port matches HttpsPort.'
}
if (-not (Test-Path $TlsCertificatePath -PathType Leaf) -or -not (Test-Path $TlsPrivateKeyPath -PathType Leaf)) {
  throw 'Provide the PEM server certificate chain and matching private key.'
}
$bindIp = $null
if (-not [Net.IPAddress]::TryParse($BindAddress, [ref]$bindIp) -or
    $bindIp.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
    $bindIp.Equals([Net.IPAddress]::Any) -or $bindIp.Equals([Net.IPAddress]::Loopback)) {
  throw 'BindAddress must be the server LAN IPv4 address, not 0.0.0.0 or loopback.'
}
if (-not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress $BindAddress -ErrorAction SilentlyContinue)) {
  throw "BindAddress $BindAddress is not assigned to this server."
}
if ((Get-Content $TlsCertificatePath -Raw) -notmatch '-----BEGIN CERTIFICATE-----' -or
    (Get-Content $TlsPrivateKeyPath -Raw) -notmatch '-----BEGIN (?:EC |RSA )?PRIVATE KEY-----') {
  throw 'The certificate and key must be PEM files.'
}
$source = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if ([IO.Path]::GetFullPath($source).TrimEnd('\') -eq [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')) { throw 'Extract the package outside InstallDir first.' }
& $PythonPath -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
if ($EnableDirectoryApprovals -and (-not $LdapUri.StartsWith('ldaps://') -or -not $LdapBindDn -or -not $LdapBaseDn -or -not $AdGroupBase)) {
  throw 'Supply LDAPS URI, bind DN, base DN and AD group OU before enabling directory approvals.'
}
New-Item -ItemType Directory -Force $InstallDir | Out-Null
# Only Administrators/SYSTEM can modify code or secrets. LOCAL SERVICE can read configuration.
& icacls.exe $InstallDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-19:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot secure console installation directory.' }
if (Test-Path (Join-Path $InstallDir 'runtime.json')) {
  $backupDir = Join-Path $InstallDir ('backups\direct-https-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -ItemType Directory -Force $backupDir | Out-Null
  foreach ($file in @('runtime.json','Caddyfile','deploy\windows\Start-ConsoleProcess.ps1')) {
    $sourceFile = Join-Path $InstallDir $file
    if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
      $targetFile = Join-Path $backupDir $file
      New-Item -ItemType Directory -Force (Split-Path $targetFile -Parent) | Out-Null
      Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
    }
  }
}
foreach ($taskName in @('NileHopeDLP-Web','NileHopeDLP-Worker','NileHopeDLP-Proxy')) {
  if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $taskName }
}
foreach ($name in @('services','deploy','requirements.txt')) { Copy-Item (Join-Path $source $name) $InstallDir -Recurse -Force }
$dataDir = Join-Path $InstallDir 'data'
New-Item -ItemType Directory -Force $dataDir | Out-Null
& icacls.exe $dataDir /grant:r '*S-1-5-19:(OI)(CI)M' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot grant runtime data access.' }
$tlsDir = Join-Path $dataDir 'tls'
New-Item -ItemType Directory -Force $tlsDir | Out-Null
Copy-Item $TlsCertificatePath (Join-Path $tlsDir 'server-fullchain.pem') -Force
Copy-Item $TlsPrivateKeyPath (Join-Path $tlsDir 'server.key') -Force
& icacls.exe $tlsDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-19:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot secure the HTTPS private key directory.' }
$venv = Join-Path $InstallDir '.venv'
& $PythonPath -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install -r (Join-Path $InstallDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
function New-Secret {
  $bytes = New-Object byte[] 32
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}
$configPath = Join-Path $InstallDir 'runtime.json'
$old = $null
if (Test-Path $configPath) { $old = Get-Content $configPath -Raw | ConvertFrom-Json }
if (-not $DatabaseUrl) {
  if ($old) { $DatabaseUrl = $old.DATABASE_URL }
  else { $DatabaseUrl = 'sqlite:///' + (Join-Path $dataDir 'file_control.db').Replace('\','/') }
}
$secret = New-Secret; $enroll = New-Secret
if ($old) { $secret = $old.SECRET_KEY; $enroll = $old.ENROLL_TOKEN }
$config = @{
  FC_ENV='production'; SECRET_KEY=$secret; ENROLL_TOKEN=$enroll; DATABASE_URL=$DatabaseUrl
  ENABLE_REMOTE_COMMANDS='0'; ENABLE_DIRECTORY_WRITES='0'; STAFF_REQUESTS_ENABLED='0'; AD_GROUP_PREFIX='FC-'
  TLS_CERTIFICATE_FILE=(Join-Path $tlsDir 'server-fullchain.pem')
  TLS_PRIVATE_KEY_FILE=(Join-Path $tlsDir 'server.key')
  TLS_BIND_ADDRESS=$BindAddress; TLS_PORT=[string]$HttpsPort
  PUBLIC_CONSOLE_URL=$PublicConsoleUrl.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
}
# Preserve established directory connectivity on reinstall so the expiry worker can still revoke grants.
if ($old) {
  foreach ($name in @('ENABLE_DIRECTORY_WRITES','LDAP_URI','LDAP_BIND_DN','LDAP_PASSWORD','LDAP_BASE_DN','AD_GROUP_BASE','LDAP_CA_CERT_FILE','ENROLLMENT_ENABLED','STAFF_REQUESTS_ENABLED')) {
    if ($old.PSObject.Properties.Name -contains $name) { $config[$name] = [string]$old.$name }
  }
}
if ($EnableRemoteCommands) { $config.ENABLE_REMOTE_COMMANDS='1' }
if ($EnableDirectoryApprovals) {
  $credential = Get-Credential -UserName $LdapBindDn -Message 'Delegated AD group-membership account (not Domain Admin)'
  if (-not $credential) { throw 'No AD credential supplied.' }
  $config.ENABLE_DIRECTORY_WRITES='1'; $config.LDAP_URI=$LdapUri; $config.LDAP_BIND_DN=$LdapBindDn
  $config.LDAP_PASSWORD=$credential.GetNetworkCredential().Password
  $config.LDAP_BASE_DN=$LdapBaseDn; $config.AD_GROUP_BASE=$AdGroupBase
  if ($LdapCaCertificate) {
    Copy-Item $LdapCaCertificate (Join-Path $InstallDir 'ad-ca.pem') -Force
    $config.LDAP_CA_CERT_FILE=Join-Path $InstallDir 'ad-ca.pem'
  }
}
$config | ConvertTo-Json | Set-Content $configPath -Encoding UTF8
Set-Location $InstallDir
$env:PYTHONPATH = Join-Path $InstallDir 'services\management'
& $python (Join-Path $InstallDir 'deploy\windows\run_runtime.py') $configPath init-db
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
Write-Host 'Create or reset the console administrator. Password input is hidden.'
& $python (Join-Path $InstallDir 'deploy\windows\run_runtime.py') $configPath create-admin admin
if ($LASTEXITCODE -ne 0) { throw 'Admin creation failed.' }
$principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::Zero) -RestartCount 100 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew
$trigger = New-ScheduledTaskTrigger -AtStartup
if (Get-ScheduledTask -TaskName 'NileHopeDLP-Proxy' -ErrorAction SilentlyContinue) {
  Disable-ScheduledTask -TaskName 'NileHopeDLP-Proxy' | Out-Null
}
foreach ($mode in @('Web','Worker')) {
  $launcher = Join-Path $InstallDir 'deploy\windows\Start-ConsoleProcess.ps1'
  $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -InstallDir "{1}" -Mode {2}' -f $launcher,$InstallDir,$mode
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $InstallDir
  Register-ScheduledTask -TaskName "NileHopeDLP-$mode" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName "NileHopeDLP-$mode"
}
Write-Host "Direct HTTPS console started at $($PublicConsoleUrl.GetLeftPart([UriPartial]::Authority)). Verify the TLS certificate and /healthz."
Write-Host 'The application server terminates TLS directly. Do not expose the loopback-only HTTP development listener.'
Write-Host 'Create a narrowly scoped LAN firewall rule only after confirming the console health and certificate.'
Write-Host 'The enrollment token is stored in protected runtime.json. Do not share that file.'
Write-Host 'Staff self-service is disabled until authenticated staff access is designed. AD approval configuration is optional and explicit.'
