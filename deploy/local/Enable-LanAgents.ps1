#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.-]*$')][string]$AgentHost,
  [Parameter(Mandatory=$true)][string[]]$AllowedClientNetworks,
  [string]$ProjectRoot=(Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
)
$ErrorActionPreference='Stop'
Set-Location $ProjectRoot
if (-not (Test-Path '.env')) { throw 'Run Start-Local.bat first.' }
$env:LOCAL_AGENT_HOSTNAME=$AgentHost
$marker=Join-Path $ProjectRoot '.local\compose-project.txt'
$projectName=if (Test-Path $marker) {(Get-Content $marker -Raw).Trim()} else {'nile-local-pc'}
if ($projectName -notin @('nile-local-pc','nile-local-demo')) { throw 'Unexpected local project identity.' }
$compose=@('compose','-p',$projectName,'-f','docker-compose.yml','-f','compose.local.yml','-f','compose.local-lan.yml')
& docker @compose up -d --no-build lan-gateway
if ($LASTEXITCODE -ne 0) { throw 'The LAN HTTPS gateway could not start. Check whether TCP 8443 is already in use.' }
$root=Join-Path $ProjectRoot '.local\console-root-ca.crt'
$certificate=$null
for ($attempt=0;$attempt -lt 15;$attempt++) {
  $certificate=& docker @compose exec -T lan-gateway cat /data/caddy/pki/authorities/local/root.crt 2>$null
  if ($LASTEXITCODE -eq 0 -and ($certificate -join "`n") -match 'BEGIN CERTIFICATE') { break }
  Start-Sleep -Seconds 2
}
if ($LASTEXITCODE -ne 0) { throw 'The gateway started, but its public root certificate is not ready. Inspect its logs.' }
$certificate | Set-Content $root -Encoding ASCII
$ruleName='NileHope-Local-Agent-HTTPS'
$existing=Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existing) { $existing | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress $AllowedClientNetworks }
else { New-NetFirewallRule -Name $ruleName -DisplayName 'Nile of Hope Local Agent HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -RemoteAddress $AllowedClientNetworks -Profile Any | Out-Null }
@{Host=$AgentHost;AllowedClientNetworks=$AllowedClientNetworks} | ConvertTo-Json | Set-Content (Join-Path $ProjectRoot '.local\lan-config.json') -Encoding UTF8
Write-Host "Agent URL: https://${AgentHost}:8443"
Write-Host "Public CA certificate: $root . Copy only this certificate to clients and trust it before enrolling."
Write-Host 'No file-share permissions, DNS records or endpoint restrictions were changed. The HTTP UI and MySQL remain loopback-only.'
