# Manual domain-user pilot: monitoring, recovery, and upload approval

This pilot uses the existing Docker console and existing Windows monitoring agent, plus the C# recovery worker on the Windows file server. **GPO is optional.** Known environment: domain `YOUR-AD-DOMAIN`, console laptop LAN IP `CONSOLE_HOST_OR_IP`, file server IP `FILESERVER_IP`. Confirm those addresses are still current before installing.

The package contains `monitoring-agent` for the physical user PC, `worker` for the file server, and `tools` for installing/managing the recovery service. Installation needs a local administrator. The domain user then signs in normally for the file tests.

## 1. Console connectivity and trust

Start the Docker console using `Start-Console-Only.bat`. For agents on other computers, enable the supplied HTTPS LAN gateway from elevated Windows PowerShell on the console PC:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Set-Location 'C:\path\to\project'
.\deploy\local\Enable-LanAgents.ps1 -AgentHost 'CONSOLE_HOST_OR_IP' -AllowedClientNetworks @('FILESERVER_IP','ACTUAL-PILOT-PC-IP')
```

Replace the pilot PC placeholder. The script starts TCP 8443 and exports `.local\console-root-ca.crt`. If an existing gateway uses a different stable DNS name, use that same name throughout instead. Domain policies enforcing signed scripts take precedence over a process-only execution policy.

Copy **only the public certificate** to both pilot devices. On each, in elevated PowerShell:

```powershell
Import-Certificate -FilePath 'C:\FileGuardInstall\console-root-ca.crt' -CertStoreLocation 'Cert:\LocalMachine\Root'
Test-NetConnection 'CONSOLE_HOST_OR_IP' -Port 8443
Invoke-RestMethod 'https://CONSOLE_HOST_OR_IP:8443/healthz'
```

Require a successful TCP test and `ok: True`. Keep certificate validation enabled. The two network ranges need a route and firewall permission from devices to the console. The console PC must remain awake, connected, and running Docker.

## 2. Install the existing monitoring agent on one domain PC

Copy the package's `monitoring-agent` directory to `C:\FileGuardInstall\monitoring-agent`. It contains both `Install-LocalAgent.ps1` and `FileControlAgent.ps1`; one script by itself is not the whole installer. Obtain the `ENROLL_TOKEN` from the console's private `.env` locally. It is different from the console administrator password.

On the **user's PC**, in elevated Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Set-Location 'C:\FileGuardInstall\monitoring-agent'
$secret=Read-Host 'Console enrollment token' -AsSecureString
$token=(New-Object Net.NetworkCredential('', $secret)).Password
.\Install-LocalAgent.ps1 -ServerUrl 'https://CONSOLE_HOST_OR_IP:8443' -EnrollToken $token -Role workstation -Ring pilot
Remove-Variable token,secret
Get-ScheduledTask -TaskName NileHopeFileControl
```

Confirm the PC's hostname and a recent heartbeat in **Devices** within about 90 seconds. Logs are in `%ProgramData%\FileControl\agent.log`. Keep an already enrolled device's key during an upgrade. Do not clone keys between devices. If the hostname was previously enrolled but its local key was lost, investigate the enrollment conflict before retrying.

For SMB audit monitoring, install this same existing agent separately on **FILESERVER_IP** using `-Role fileserver`. The recovery worker below is additional and does not replace it. The existing monitoring agent still needs the Windows audit policies described in `DOMAIN-PILOT-NO-DELETE.md` to report SMB checks.

## 3. Build or copy the self-contained recovery package

The development PC needs the .NET 10 SDK to build. The Windows x64 file server does not need the SDK for the self-contained package:

```powershell
.\scripts\Build-RecoveryPilot.ps1 -DotnetPath 'C:\path\to\dotnet.exe'
```

The command prints a new `.local\recovery-pilot-TIMESTAMP.zip`. Extract it on the file server at `C:\FileGuardInstall\RecoveryPilot`. Signed-executable/application-control policies may require the organization's approval or signing process for the newly built executable; do not disable those policies.

## 4. Install recovery on the FILE SERVER, starting in monitoring mode

Run this on **FILESERVER_IP**, not the user's workstation. Choose a new nonexistent directory on a suitable local data drive, with enough capacity for protected copies. Example:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Set-Location 'C:\FileGuardInstall\RecoveryPilot'
.\tools\Install-RecoveryPilot.ps1 -PackagePath '.\worker' -PilotRoot 'D:\FileGuardPilotData' -ServerUrl 'https://CONSOLE_HOST_OR_IP:8443'
```

Enter the enrollment token when prompted. The installer:

- Refuses existing pilot/install directories or an existing service rather than overwriting them.
- Creates three sibling directories: `protected`, `repository`, and `state`.
- Installs `NileHopeFileGuardRecoveryPilot` as a Windows service using its dedicated virtual service account.
- Starts with `autoRestore: false` and read access to the protected directory; repository/state remain private and writable to the service.
- Uses a separate device identity such as `FILE01-RECOVERY`, so it can coexist with `FILE01`'s monitoring agent.
- Stores configuration under `%ProgramData%\NileHopeRecoveryPilot`, restricted to Administrators, SYSTEM, and service read access. Keep the bootstrap token/config private.

The service starts automatically with Windows. Check its state and verify the **Recovery & versions > File-server pilots** report shows the actual server, configured protected directory, recent heartbeat, and **Monitoring only** mode. A running service alone is not evidence of console connectivity.

```powershell
Get-Service NileHopeFileGuardRecoveryPilot
```

Monitoring captures stable copies and reports later deletion; it does **not** write a missing file back. It therefore uses repository disk space even before restoration is enabled. The local manifest, audit, and durable outgoing events are under the pilot `state` directory. Service startup errors are also available through Windows Event Viewer.

## 5. Expose only the disposable protected directory

On the file server, use a dedicated ordinary pilot user or group, replacing `DOMAIN\pilotuser` with its real name:

```powershell
icacls 'D:\FileGuardPilotData\protected' /grant 'DOMAIN\pilotuser:(OI)(CI)M'
New-SmbShare -Name 'FG-Pilot' -Path 'D:\FileGuardPilotData\protected' -ChangeAccess 'DOMAIN\pilotuser'
```

Check both commands succeeded. Share **only** `protected`; never share `repository`, `state`, or the configuration/installation folder with staff. The pilot user needs create/edit/delete rights in this disposable folder to test recovery. Do not apply the earlier no-delete restriction to this test folder. Existing live shares and workstation file permissions are outside this installer's scope.

On the file server, run `hostname`. On the user's PC, use `\\ACTUAL-SERVER-NAME\FG-Pilot`. A separate recovery identity ending in `-RECOVERY` does not replace the real server name used in UNC paths. Register that UNC under **Shared folders** if SMB access-check monitoring is also enabled.

## 6. Test monitoring, then explicitly enable recovery

From the user's PC, create a disposable text file on the pilot share. Save version one, wait for its **Version preserved** event in the console, then edit it and wait for a second preserved version. Delete it. In monitoring mode it should remain missing and generate **Deletion observed**. The file content itself stays on the file server; recovery reports contain metadata.

An administrator can also run the repeatable local service check on the file server. It creates/deletes only its own unique disposable text file:

```powershell
.\tools\Test-RecoveryPilot.ps1 -Phase Monitoring
```

After reviewing the monitoring results, explicitly enable recovery:

```powershell
.\tools\Set-RecoveryPilotMode.ps1 -Mode Recovery
.\tools\Test-RecoveryPilot.ps1 -Phase Recovery
```

The switch stops the service, updates local policy and the service's protected-folder permission, records the change, and restarts it. Enabling recovery can restore previously missing files with captured versions, including monitoring-phase deletions. Review the manifest before switching if those earlier missing files should remain absent.

Repeat the user-PC edit/delete test with another disposable file, waiting for a capture before deletion. Expect the latest captured contents to return at the original path and a **Restored & verified** event. The automated recovery-phase test verifies SHA-256 and retains its restored test file so it does not trigger repeated cleanup/restore loops.

The existing safe restore process is retained: verify the repository object, copy to a temporary sibling, verify, then promote without overwriting an existing destination. It is post-delete recovery, not pre-delete blocking. Renames, directory recovery, initiating-user attribution, full NTFS metadata/ADS, retention, immutable storage, and high-volume production behavior require further work. Ordinary users with write access can still overwrite file contents.

Return to monitoring or stop the pilot:

```powershell
.\tools\Set-RecoveryPilotMode.ps1 -Mode Monitoring
# Or stop it completely:
Stop-Service NileHopeFileGuardRecoveryPilot
```

Stopping the service does not remove protected copies, the share, or its user permissions. Remove pilot access/share separately through your reviewed Windows administration process. Preserve state/repository while investigating a failure. No domain-wide rollout is implied by the local checks.

## 7. Browser upload approval is a separate feature

The console has a new **Upload approvals** page. It does not grant AD permissions or intercept direct SMB file copies. It is an administrator-authenticated browser queue for this pilot; ordinary domain-user SSO and separate reviewer roles are not implemented. Use the existing console login to test the workflow; the same administrator can submit and review a request.

Enable it by adding `UPLOAD_APPROVAL_ENABLED=1` to the console's private `.env`, then rebuild/recreate the Docker stack with the existing launcher. The backend stores submitted files in the dedicated private `upload_data` volume; back up that volume with its matching database rows. Do not remove Docker volumes to upgrade.

Test using disposable files:

1. Sign in and open **Upload approvals**.
2. Select a nonempty file up to **10 MiB**, enter a reason, and submit.
3. The pending request exposes metadata; its file cannot be downloaded.
4. Approve one request. Its **Download approved file** action becomes available.
5. Download it and manually copy it to the intended share using an authorized Windows account.
6. Submit another file and reject it. It remains unavailable for download.
7. Review submission, decision, and download entries in **Audit trail**.

Downloads verify the stored SHA-256 and size, require an authenticated administrator and approved state, and are sent as attachments. Approval does not perform malware scanning, place a file on a server, or prevent someone with existing SMB write rights from uploading directly. Browser-only upload enforcement would additionally require server-side access restrictions and an approved delivery identity/workflow.

## Validation boundary

Local automated engine/API tests and the frontend build are separate from the real server/user pilot. The installer and tests must still be exercised on FILESERVER_IP under its actual service, NTFS, certificate, application-control, and SMB configuration before claiming a successful physical-device rollout.
