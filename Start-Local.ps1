# Starts the app on THIS Windows PC. Requires Docker Desktop running Linux containers.
param([ValidateRange(1024,65535)][int]$Port=8080,[switch]$SkipWindowsAgent,[switch]$Demo)
$ErrorActionPreference='Stop'
$project=$PSScriptRoot
Set-Location -LiteralPath $project
. (Join-Path $project 'deploy\local\Docker-Tools.ps1')
$dockerTools=Get-FileGuardDockerTools
$dockerPath=$dockerTools.DockerPath
if (-not $dockerPath) {
  if ($dockerTools.DesktopPath) {
    Start-Process -FilePath $dockerTools.DesktopPath
    throw 'Docker Desktop was found, but docker.exe is missing. Complete its setup or repair the installation to include the Docker CLI, then retry Start-Console-Only.bat.'
  }
  throw 'docker.exe was not found on PATH or in the usual Docker Desktop installation folders. Open Docker Desktop and finish setup, close and reopen this terminal, then retry Start-Console-Only.bat. If it still fails, repair the Docker Desktop installation.'
}
# Credential helpers and child processes also need Docker's bin directory.
# This affects only the launcher process; it does not edit the system/user PATH.
$env:Path=(Split-Path -Parent $dockerPath)+';'+$env:Path
Write-Host "Docker CLI found: $dockerPath"
$ErrorActionPreference='Continue'
$engine=& $dockerPath info --format '{{.OSType}}' 2>$null
$engineExit=$LASTEXITCODE
$ErrorActionPreference='Stop'
if ($engineExit -ne 0) {
  $desktop=$dockerTools.DesktopPath
  if ($desktop) {
    Write-Host 'Starting Docker Desktop...'
    Start-Process $desktop
    for ($attempt=0;$attempt -lt 60;$attempt++) {
      Start-Sleep -Seconds 2
      $ErrorActionPreference='Continue'
      $engine=& $dockerPath info --format '{{.OSType}}' 2>$null
      $engineExit=$LASTEXITCODE
      $ErrorActionPreference='Stop'
      if ($engineExit -eq 0) { break }
    }
  }
}
if ($engineExit -ne 0) { throw 'Docker Engine is unavailable. Finish Docker Desktop/WSL setup and start Docker Desktop, then rerun the launcher.' }
if (($engine | Out-String).Trim() -ne 'linux') { throw 'In Docker Desktop, switch to Linux containers, then rerun the launcher.' }
& $dockerPath compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required. Update Docker Desktop.' }
$private=Join-Path $project '.local'
New-Item -ItemType Directory -Force $private | Out-Null
$identitySid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $private /inheritance:r /grant:r "${identitySid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect local configuration output.' }
function New-Secret {
  $bytes=New-Object byte[] 32
  $generator=[Security.Cryptography.RandomNumberGenerator]::Create()
  try {$generator.GetBytes($bytes)} finally {$generator.Dispose()}
  return -join ($bytes | ForEach-Object {$_.ToString('x2')})
}
$environmentFile=Join-Path $project '.env'
if (-not (Test-Path $environmentFile)) {
  $values=[ordered]@{
    MYSQL_DATABASE='nilehope_fileguard';MYSQL_USER='dlp_app';MYSQL_PASSWORD=(New-Secret);MYSQL_ROOT_PASSWORD=(New-Secret)
    SECRET_KEY=(New-Secret);ENROLL_TOKEN=(New-Secret);BOOTSTRAP_ADMIN_USER='admin';BOOTSTRAP_ADMIN_PASSWORD=(New-Secret)
    FC_ENV='testing';CONSOLE_ENVIRONMENT='local';PUBLIC_CONSOLE_URL="http://localhost:$Port";FRONTEND_PORT=[string]$Port
    FRONTEND_BIND_ADDRESS='127.0.0.1';MYSQL_HOST_PORT='13306';MYSQL_BIND_ADDRESS='127.0.0.1'
  }
  if ($Demo) { $values.CONSOLE_ENVIRONMENT='test' }
  ($values.GetEnumerator() | ForEach-Object {"$($_.Key)=$($_.Value)"}) | Set-Content $environmentFile -Encoding ASCII
}
& icacls.exe $environmentFile /inheritance:r /grant:r "${identitySid}:(F)" '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect .env.' }
$config=@{}
foreach ($line in (Get-Content $environmentFile)) {
  if ($line -match '^([A-Z_]+)=(.*)$') {$config[$matches[1]]=$matches[2]}
}
if (-not $config.MYSQL_PASSWORD -or -not $config.BOOTSTRAP_ADMIN_PASSWORD -or $config.FC_ENV -eq 'production') {
  throw 'This folder contains another deployment configuration. Extract the local bundle into a new folder; existing configuration was preserved.'
}
if ($PSBoundParameters.ContainsKey('Port')) {
  $lines=Get-Content $environmentFile
  $lines=$lines -replace '^FRONTEND_PORT=.*$',"FRONTEND_PORT=$Port"
  $lines=$lines -replace '^PUBLIC_CONSOLE_URL=.*$',"PUBLIC_CONSOLE_URL=http://localhost:$Port"
  $lines | Set-Content $environmentFile -Encoding ASCII
  $config.FRONTEND_PORT=[string]$Port
}
$url="http://localhost:$($config.FRONTEND_PORT)"
$projectName=if ($Demo) {'nile-local-demo'} else {'nile-local-pc'}
Set-Content (Join-Path $private 'compose-project.txt') $projectName -Encoding ASCII
$compose=@('compose','-p',$projectName,'-f','docker-compose.yml','-f','compose.local.yml')
$lanConfig=Join-Path $private 'lan-config.json'
if (Test-Path $lanConfig) {
  $lan=Get-Content $lanConfig -Raw | ConvertFrom-Json
  $env:LOCAL_AGENT_HOSTNAME=$lan.Host
  $compose+=@('-f','compose.local-lan.yml')
}
if ($Demo) {
  if ($config.CONSOLE_ENVIRONMENT -ne 'test') { throw 'Use a fresh bundle folder for a separate demo profile. The existing local configuration was preserved.' }
  $compose+=@('--profile','demo')
}
Write-Host "Building and starting your LOCAL console at $url ..."
$startup=Start-Process -FilePath $dockerPath -ArgumentList ($compose+@('up','-d','--build','--wait','--wait-timeout','240')) -WorkingDirectory $project -NoNewWindow -Wait -PassThru -RedirectStandardOutput (Join-Path $private 'startup.log') -RedirectStandardError (Join-Path $private 'startup-errors.log')
if ($startup.ExitCode -ne 0) { throw 'The local containers did not become healthy. Review .local\startup.log and Docker Desktop; the browser was not opened as a false success.' }
$health=Invoke-RestMethod "$url/healthz" -TimeoutSec 15
$frontend=Invoke-RestMethod "$url/frontend-health" -TimeoutSec 15
if (-not $health.ok -or $frontend.service -ne 'frontend') { throw 'The expected frontend/database health check failed.' }
$loginPath=Join-Path $private 'login.txt'
@"
Nile of Hope LOCAL console
URL: $url
Username: $($config.BOOTSTRAP_ADMIN_USER)
Password: $($config.BOOTSTRAP_ADMIN_PASSWORD)

These credentials belong to this Windows-PC test installation.
MySQL Workbench: 127.0.0.1:13306, schema nilehope_fileguard.
Database account details are stored in the protected .env file.
"@ | Set-Content $loginPath -Encoding UTF8
Write-Host "Console is healthy. Login details: $loginPath"
Start-Process $url
Start-Process notepad.exe -ArgumentList "`"$loginPath`""
if (-not $SkipWindowsAgent) {
  try {
    $helper=Join-Path $project 'deploy\local\Install-ThisPC.ps1'
    $arguments='-NoProfile -ExecutionPolicy Bypass -File "{0}" -ProjectRoot "{1}"' -f $helper,$project
    Write-Host 'Installing a separate read-only LOCAL TEST Windows agent. Windows may show its normal administrator prompt.'
    $install=Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -Wait -PassThru
    if ($install.ExitCode -ne 0) { Write-Warning 'The console is running, but local-agent installation did not complete. Run deploy\local\Install-ThisPC.ps1 as Administrator when ready.' }
  } catch { Write-Warning 'The console is running. Local-agent setup needs administrator access; run deploy\local\Install-ThisPC.ps1 as Administrator.' }
}
Write-Host 'Use docs\LOCAL-WINDOWS.md to connect Linux/other Windows devices through the optional trusted LAN endpoint.'
