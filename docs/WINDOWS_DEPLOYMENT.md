> Earlier monitoring deployment reference. The root README and ARCHITECTURE.md define the current FileGuard scope. Recovery is configured separately in its disposable lab.

# Windows VM deployment and hospital agent rollout

## 1. Discover the actual environment

Run this on the Windows VM in PowerShell under an account allowed to inspect its configuration:

```powershell
Set-Location 'C:\path\to\extracted-project'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Discover-HospitalEnvironment.ps1
```

The script writes `hospital-discovery\environment.json` and `shares.csv`. It reads OS/domain/IP information and locally hosted non-administrative SMB shares. It does not discover shares hosted elsewhere unless you name those file servers:

```powershell
.\scripts\Discover-HospitalEnvironment.ps1 -FileServers 'FILE01','FILE02'
```

Remote share inventory uses CIM/WinRM and the current Windows account. Read `share-discovery-errors.txt` for unavailable hosts. This inventory does not scan subnets, read documents, change ACLs, or modify AD/GPO. Review the two output files before returning them in chat. Do not upload `runtime.json`, passwords, tokens, private keys or patient files.

DFS namespaces, aliases and clustered SMB identities need mapping to their actual file-server agents; the automatic host match currently supports NetBIOS/FQDN variations of the same computer name only.

## 2. Prepare the VM

You need:

- Windows VM OS/version confirmed by discovery, administrator rights for installation, and sufficient free disk space.
- Python 3.11+ installed **for all users** so LOCAL SERVICE can use its base Python runtime. Use a maintained Python release and an explicit path if multiple versions are present.
- The official Windows `caddy.exe` binary from https://caddyserver.com/download, extracted locally.
- A hospital DNS name for the console, pointing to the VM's hospital LAN address.
- A database choice. SQLite is included for an initial single-VM pilot. For hospital-wide deployment, use a backed-up PostgreSQL service and supply its connection URL. PostgreSQL is not silently installed by this script.
- Outbound LDAPS connectivity and the hospital AD CA chain if approvals will be enabled.

No hospital VM credentials or network access are present in this Codex workspace. Installation and the first live agent test therefore need to be run on your VM.

## 3. Install the console

In an elevated Windows PowerShell window, from the extracted project:

```powershell
.\deploy\windows\Install-Console.ps1 `
  -Hostname 'dlp.your-hospital-domain.example' `
  -CaddyPath 'C:\Tools\caddy.exe' `
  -PythonPath 'C:\Program Files\Python312\python.exe'
```

Use your actual hostname and Python location. The default data folder is `C:\ProgramData\NileHopeDLP`. The installer:

1. Restricts the installation folder to Administrators, SYSTEM, and read access for LOCAL SERVICE.
2. Installs the application dependencies into a virtual environment.
3. Generates cryptographic secrets and writes protected runtime configuration. On reinstallation, it preserves the enrollment token, session secret, and database URL.
4. Initializes the configured database and prompts for the `admin` password (12+ characters, hidden input).
5. Registers web, expiry-worker and HTTPS proxy startup tasks as LOCAL SERVICE with restart behavior.
6. Starts those tasks. Waitress listens only on loopback port 8000; Caddy serves HTTPS on port 443.

The initial test leaves remote commands and directory writes disabled. Use `-EnableRemoteCommands` for a later control test; supply real LDAPS settings for approvals. An installer message that tasks started is not proof that HTTPS or hospital connectivity works; perform the checks below.

For PostgreSQL, pass `-DatabaseUrl` with your actual connection URL, supplied locally from a protected input/variable. URL-encode special characters in credentials, and configure database TLS as required by the hospital. Do not paste the URL into chat. The installer does not migrate an existing database.

## 4. Configure HTTPS trust, DNS, and network access

The supplied Caddy configuration uses an internal CA, suitable for an intranet pilot. The first certificate issuance creates a root certificate under the console data folder:

```powershell
Get-ChildItem 'C:\ProgramData\NileHopeDLP\data\caddy' -Filter root.crt -Recurse
```

Distribute **only the public root certificate** to intended computers through the hospital's trusted-root certificate policy. Do not distribute the CA private key. Alternatively configure Caddy with a certificate from the hospital's existing PKI before deployment.

Create a DNS record for your selected hostname. Permit TCP 443 to the console only from the intended hospital client/server subnets. The installer leaves firewall scope and DNS changes to your actual network configuration; it does not guess them or publish the console on the internet. Keep port 8000 private and do not expose the database port to PCs.

Verify from a certificate-trusting hospital computer:

```powershell
Invoke-RestMethod 'https://YOUR-CONSOLE-HOSTNAME/healthz'
```

Expected: `ok: True`. Open the same HTTPS hostname in a browser and sign in. Review `%ProgramData%\NileHopeDLP\data\Web.log`, `Worker.log`, `Proxy.log` and Task Scheduler if a task fails. Logs rotate on restart when larger than 10 MB; install continuous log retention/rotation appropriate to hospital operations before broad rollout.

## 5. Register actual hospital shares

You can add exact paths such as `\\FILE01\Finance` under Settings, or import discovery output on the VM:

```powershell
Set-Location 'C:\ProgramData\NileHopeDLP'
& '.\.venv\Scripts\python.exe' '.\deploy\windows\run_runtime.py' '.\runtime.json' import-shares 'C:\path\to\shares.csv'
```

Imports are validated before writing, are deduplicated, and only register monitoring targets. Wildcards such as `\\FILE01\*` are not supported. Registration does not change any file permissions or start file scanning.

## 6. Install one PC agent and one file-server agent

Copy the `agent` folder to an approved deployment location. On one pilot PC, in elevated PowerShell:

```powershell
$token = Read-Host 'Enrollment token from the protected console runtime configuration'
.\agents\windows-monitor\Install-LocalAgent.ps1 -ServerUrl 'https://YOUR-CONSOLE-HOSTNAME' -EnrollToken $token -Ring pilot
Remove-Variable token
```

Repeat on one actual file server with `-Role fileserver`. The agent polls every 30 seconds, retrieves share paths for its own hostname, and forwards metadata only for those registered paths. Endpoint agents do not automatically see file-server Security logs: deploy a file-server agent for share auditing.

On the file server, enable **Advanced Audit Policy: Detailed File Share** success/failure auditing under the hospital's existing GPO process. Validate both allowed and denied DELETE access checks using disposable files on a test share. Event volume and Security log capacity must be reviewed before extending auditing to all shares. No audit policy or NTFS permissions are changed by the agent installer.

Check:

- Both devices appear online within 90 seconds.
- Only registered share paths produce stored events.
- ACL observations show review/warnings and never claim effective protection.
- A log-collection command returns actual event metadata or a visible failure.
- USB blocking and restore work on a test PC, without contradicting domain policy.
- SMB disconnection is tested only during an approved test window: it closes all sessions on the target server and can interrupt open files. It is not permanent network isolation.

Agent keys, bootstrap token, pending results and logs live in `%ProgramData%\FileControl`, restricted to SYSTEM/Administrators. The bootstrap token is deleted after enrollment. The command result is retried if delivery fails; disruptive commands are not automatically re-executed after a lost heartbeat response. A command stuck at `sent` needs investigation before any manual requeue.

## 7. Enable AD approvals after validating their scope

Create dedicated security groups such as `FC-Delete-Approved`, `FC-Upload-Approved`, and `FC-Send-Approved` in the chosen group OU. Delegate only membership management to the application account; do not use Domain Admin credentials. Review Windows ACL/GPO integration separately.

Then rerun the console installer with its normal arguments plus:

```powershell
-EnableDirectoryApprovals `
-LdapUri 'ldaps://dc.your-domain.example:636' `
-LdapBindDn 'CN=svc-dlp,OU=ServiceAccounts,DC=your-domain,DC=example' `
-LdapBaseDn 'DC=your-domain,DC=example' `
-AdGroupBase 'OU=FileControl,DC=your-domain,DC=example' `
-LdapCaCertificate 'C:\Certificates\hospital-ad-ca.pem'
```

The credential prompt is local and hidden. Server certificate validation remains enabled.

Before broad use, test approval, rejection, expiry, revocation, an unavailable DC, and Windows access-token refresh. **These groups grant action-wide access wherever the group has rights, rather than limiting access to a requested file path.** If per-file approvals are needed, keep writes disabled until that authorization model is implemented. Group removal alone does not guarantee immediate revocation of an already-open file or SMB session.

Administrators can enter reviewed requests at `/request` while signed in. Anonymous staff requests remain disabled; hospital SSO and staff identity verification are still an integration choice.

## 8. Deploy agents to all intended computer OUs using GPO

Prepare the bundle locally:

```powershell
$token = Read-Host 'Enrollment token'
.\agents\windows-monitor\Prepare-GPODeployment.ps1 -ServerUrl 'https://YOUR-CONSOLE-HOSTNAME' `
  -EnrollToken $token -FileServers 'FILE01','FILE02' -Ring pilot
Remove-Variable token
```

The bundle contains an enrollment credential. Restrict write access to administrators; the target computers need read access. In Group Policy Management:

1. Create a GPO linked to your pilot computer OU.
2. Under Computer Configuration -> Windows Settings -> Scripts -> Startup -> PowerShell Scripts, choose **Show Files**.
3. Copy all generated files there, then **Add `Startup-Agent.ps1`** as the startup script.
4. Ensure computer startup can read the policy files, and deploy certificate trust before the agent startup policy.
5. Reboot pilot devices and verify installation/heartbeats. The bundle assigns `fileserver` role only to explicitly named server computer names.
6. Extend the validated policy to the intended PC OUs and appropriate file-server OUs. Ring labels are inventory labels; the backend does not automatically limit policy enforcement by ring.

This package generates files and instructions. It does not claim a GPO exists merely because files were copied to SYSVOL. GPMC registration/linking must be performed in your actual domain.

When initial enrollment is complete, set `ENROLLMENT_ENABLED` to `0` in protected `runtime.json` and restart the web task. Existing device keys continue working. Use a new enrollment token and window for later device additions; treat the initial enrollment token as visible to enrolled computers.

## 9. Backups and recovery

Back up the database, protected runtime configuration, and Caddy data/PKI using hospital-controlled encrypted backups. Test recovery into an isolated VM. For the SQLite pilot, use Python's SQLite backup API or stop web/worker tasks before copying the database and its WAL state; do not copy a live database file alone. PostgreSQL should use the hospital's database backup process.

Stop console tasks before replacing program files. Keep the previous package and database backup for rollback. Agent rollback should preserve `key.txt`; removing that key requires a coordinated re-enrollment.

No real Windows execution, AD membership changes, GPO deployment, share auditing, or hospital-wide load validation has been performed from the isolated Codex environment. Those are the remaining live verification steps.
