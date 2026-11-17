#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][string]$PackagePath,
  [Parameter(Mandatory=$true)][string]$PilotRoot,
  [Parameter(Mandatory=$true)][uri]$ServerUrl,
  [securestring]$EnrollmentToken,
  [string]$InstallRoot=(Join-Path $env:ProgramData 'NileHopeRecoveryPilot')
)
. (Join-Path $PSScriptRoot 'Recovery-PilotTools.ps1')
$serviceName='NileHopeFileGuardRecoveryPilot'
$account='NT SERVICE\'+$serviceName
$install=Assert-PilotLocalPath $InstallRoot
$pilot=Assert-PilotLocalPath $PilotRoot
if ($install -eq $pilot -or $install.StartsWith($pilot+'\',[StringComparison]::OrdinalIgnoreCase) -or $pilot.StartsWith($install+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'InstallRoot and PilotRoot must be separate directories.' }
if ($ServerUrl.Scheme -ne 'https' -or $ServerUrl.UserInfo -or $ServerUrl.Query -or $ServerUrl.Fragment -or $ServerUrl.AbsolutePath -ne '/') { throw 'Use a trusted HTTPS console origin, without credentials or a subpath.' }
$package=(Resolve-Path -LiteralPath $PackagePath).Path
if (-not (Test-Path -LiteralPath (Join-Path $package 'FileGuard.Recovery.exe'))) { throw 'Publish the self-contained win-x64 worker before installing.' }
if ((Test-Path -LiteralPath $pilot) -or (Test-Path -LiteralPath $install) -or (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) { throw 'Use new, nonexistent pilot/install directories. Existing data and services were preserved.' }
if (-not $EnrollmentToken) { $EnrollmentToken=Read-Host 'Console enrollment token (input hidden)' -AsSecureString }
$token=(New-Object Net.NetworkCredential('', $EnrollmentToken)).Password
if ($token.Length -lt 16) { throw 'Use the console enrollment token, not the administrator password.' }
New-Item -ItemType Directory -Path $install | Out-Null
Set-PilotDirectoryAccess $install '' 'ReadAndExecute'
New-Item -ItemType Directory -Path $pilot | Out-Null
Set-PilotDirectoryAccess $pilot '' 'ReadAndExecute'
$bin=Join-Path $install 'bin'
New-Item -ItemType Directory -Path $bin | Out-Null
Copy-Item -Path (Join-Path $package '*') -Destination $bin -Recurse
foreach ($folder in @('protected','repository','state')) { New-Item -ItemType Directory -Path (Join-Path $pilot $folder) | Out-Null }
$configPath=Join-Path $install 'recovery-config.json'
$config=@{protectedRoot=(Join-Path $pilot 'protected');repositoryRoot=(Join-Path $pilot 'repository');stateRoot=(Join-Path $pilot 'state');autoRestore=$false;scanSeconds=2;settleMilliseconds=500;maxFileBytes=104857600;maxRestoresPerMinute=3;serverUrl=$ServerUrl.AbsoluteUri.TrimEnd('/');enrollmentToken=$token;hostname=($env:COMPUTERNAME+'-RECOVERY')}
Write-PilotJson $configPath $config
Remove-Variable token
$binary='"'+(Join-Path $bin 'FileGuard.Recovery.exe')+'" --config "'+$configPath+'"'
& sc.exe create $serviceName binPath= $binary start= auto obj= $account DisplayName= 'NileHope FileGuard Recovery Pilot' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Windows service creation failed. The pilot remains stopped; inspect the private installation before retrying.' }
Set-PilotDirectoryAccess $install $account 'ReadAndExecute'
Set-PilotDirectoryAccess $pilot $account 'ReadAndExecute'
Set-PilotDirectoryAccess $config.protectedRoot $account 'ReadAndExecute'
Set-PilotDirectoryAccess $config.repositoryRoot $account 'Modify'
Set-PilotDirectoryAccess $config.stateRoot $account 'Modify'
Write-PilotJson (Join-Path $install 'pilot-install.json') @{serviceName=$serviceName;pilotRoot=$pilot;serviceAccount=$account;createdAt=[DateTime]::UtcNow.ToString('o')}
& sc.exe failure $serviceName reset= 86400 actions= 'restart/60000/restart/60000/restart/60000' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not configure service restart behavior. Review the stopped service.' }
Start-Service -Name $serviceName
Write-Host "Installed MONITORING mode. Protected pilot: $($config.protectedRoot)"
Write-Host "Recovery identity: $($config.hostname). The existing Windows monitoring agent is unchanged."
Write-Host 'Grant your pilot user read/write access ONLY to the protected folder, then expose that folder as a disposable SMB share.'
Write-Host 'Repository, state, and installation remain private. Confirm a recent recovery heartbeat in the console before testing.'
