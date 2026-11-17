# Domain agent deployment and file-server deletion pilot

Prepared 2026-11-16 for the existing Docker console. Known file-server IP: **FILESERVER_IP**.

Requested behavior: automatically enroll Windows domain computers; allow ordinary staff to create and edit files in selected SMB shares; deny deletion without an approval workflow. Apply deletion permissions on selected file-server folders only. Workstation agents report device health and do not scan local user folders.

This is an operator guide. No domain, firewall, GPO, file-server permissions, or hospital shares were changed while preparing it. The file-server name, share names, domain, Windows Server version, and console LAN address still need to be confirmed.

## 1. Understand what the current application does

The console is currently reached on its own PC at `http://localhost:8080`. A remote device must use a trusted LAN HTTPS address instead of localhost.

The Windows monitoring agent is a PowerShell script installed as the `NileHopeFileControl` scheduled task, running as SYSTEM at startup. A workstation agent sends health/inventory. A file-server agent also reads selected SMB deletion access checks from its local Security log. It does not change file permissions. Agents poll approximately every 30 seconds; share configuration refreshes approximately every 60 seconds.

Windows NTFS permissions enforce the deletion restriction even if the console or client agent is offline. The restriction also applies to clients without FileGuard installed, when they access the same protected server folders under a restricted account. The console's policy switches and share registration do not install this restriction.

The permission scheme below limits ordinary staff. A privileged administrator can change permissions. Allowing writing also permits overwriting/truncating contents, so deletion denial is not a substitute for tested backups. Some save workflows require deleting or replacing the original file: Microsoft documents this explicitly for Excel. Test the actual business applications before extending the rule beyond a disposable share.

## 2. Identify the server and select a test share

On **FILESERVER_IP**, open Windows PowerShell as Administrator and run these read-only commands:

```powershell
hostname
Get-CimInstance Win32_ComputerSystem | Select-Object Name, Domain, PartOfDomain
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version
Get-SmbShare | Where-Object { -not $_.Special } | Select-Object Name, Path
```

If the host is a NAS or Linux/Samba server, stop the Windows installation/ACL steps and use that platform's supported audit and permission integration. An SMB IP alone does not establish that this is Windows Server.

Record the actual computer name, such as `FILE01`. Register `\\FILE01\ShareName` or its matching FQDN in FileGuard, rather than `\\FILESERVER_IP\ShareName`: the current agent/backend match share ownership to the enrolled Windows computer name. DFS names, aliases, clusters, and the IP form do not automatically map to that computer.

Use a **new, empty pilot directory** on the server's data volume and a new SMB share, for example `D:\FileGuardPilot` exposed as `\\FILE01\FG-Pilot`. These names are examples. Do not start on a volume root, system folder, SYSVOL, or an existing hospital data tree.

## 3. Publish the local console to the LAN using HTTPS

On the **console PC**, find its actual LAN address with `ipconfig`. Use a stable IP/reservation or a DNS name that resolves to that PC. The file-server address `FILESERVER_IP` is not automatically the console address.

In elevated Windows PowerShell, from the project folder, run the following with your real values. The process-only execution policy is for the unsigned pilot scripts where organizational policy permits it; domain-enforced signing rules still apply:

```powershell
Set-Location 'C:\path\to\project'
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\deploy\local\Enable-LanAgents.ps1 -AgentHost 'CONSOLE-IP-OR-DNS' -AllowedClientNetworks @('FILESERVER_IP','PILOT-PC-IP')
```

This starts the Caddy LAN gateway on TCP 8443, creates/updates a firewall rule for those client addresses, and exports the public CA certificate to `.local\console-root-ca.crt`. For later domain rollout, rerun with the actual approved client subnets plus the file server; do not infer a subnet mask from `FILESERVER_IP`.

The resulting agent URL is:

```text
https://CONSOLE-IP-OR-DNS:8443
```

Keep the host component exactly the same in certificates, DNS, tests, and agent configuration. TCP 8443 must be reachable from the devices to the console. Agents initiate the connection; this design does not require opening an inbound management port on every workstation. Keep MySQL loopback-only. Keep the console PC powered on, awake, connected to the LAN, with Docker Desktop and its containers running; this desktop pilot is not evidence of an unattended production server installation.

## 4. Trust the certificate and test the network

Copy **only** `.local\console-root-ca.crt` to the pilot PC and file server through a controlled location. Do not distribute the Caddy private key, `.env`, or `.local\login.txt`.

For the initial two-device pilot, import the public certificate into the **Local Computer** trusted roots on each machine, in elevated PowerShell:

```powershell
Import-Certificate -FilePath 'C:\FileGuardPilotInstall\console-root-ca.crt' -CertStoreLocation 'Cert:\LocalMachine\Root'
Test-NetConnection 'CONSOLE-IP-OR-DNS' -Port 8443
Invoke-RestMethod 'https://CONSOLE-IP-OR-DNS:8443/healthz'
```

Expected: `TcpTestSucceeded : True` and `ok : True`. Importing into only the current user's certificate store is insufficient for the SYSTEM agent. Keep TLS validation enabled.

For automatic deployment, create a computer GPO such as `FileGuard - Console Trust`, linked to the pilot computer/server OUs. In GPMC edit:

```text
Computer Configuration > Policies > Windows Settings > Security Settings
  > Public Key Policies > Trusted Root Certification Authorities > Import
```

Import the public root certificate, apply policy, and confirm HTTPS succeeds before extending agent deployment. A certificate issued by the organization's existing trusted PKI can replace this pilot CA through a separately configured gateway.

## 5. Prepare the agent deployment bundle

On the console PC, open an authorized Windows PowerShell session in the project folder. If local script policy blocks the unsigned pilot scripts, a process-only bypass can be used where organizational policy permits it. A domain-enforced signing requirement takes precedence and needs signed scripts.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$enrollLine = Get-Content -LiteralPath '.env' | Where-Object { $_.StartsWith('ENROLL_TOKEN=') }
if (@($enrollLine).Count -ne 1) { throw 'Expected exactly one ENROLL_TOKEN setting.' }
$enrollToken = $enrollLine.Substring('ENROLL_TOKEN='.Length)
if (-not $enrollToken) { throw 'The enrollment token is empty.' }
.\agents\windows-monitor\Prepare-GPODeployment.ps1 -ServerUrl 'https://CONSOLE-IP-OR-DNS:8443' -EnrollToken $enrollToken -FileServers 'ACTUAL-FILESERVER-NAME' -Ring pilot
Remove-Variable enrollToken,enrollLine
```

Use the actual hostname reported by `hostname` on FILESERVER_IP in `-FileServers`, not its IP. This parameter assigns file-server mode to that computer; other computers get workstation mode.

The `gpo-deployment` folder contains four files:

```text
FileControlAgent.ps1
Install-LocalAgent.ps1
Startup-Agent.ps1
deployment.json
```

The JSON includes a bootstrap enrollment token. Administrators need write permission; only the intended deployment computers/admins need read permission. Do not publish it to a public repository or distribute the entire project configuration. The individual device key is created after enrollment, protected in `%ProgramData%\FileControl`, and the local bootstrap token is removed after successful enrollment. The shared bootstrap token still remains in the deployment bundle.

## 6. Verify one physical PC and the file server first

Copy the bundle to a protected local directory on each pilot machine. On the physical PC, in elevated PowerShell with script execution permitted:

```powershell
Set-Location 'C:\FileGuardPilotInstall\Agent'
$config = Get-Content .\deployment.json -Raw | ConvertFrom-Json
.\Install-LocalAgent.ps1 -ServerUrl $config.ServerUrl -EnrollToken $config.EnrollToken -Ring pilot -Role workstation
Remove-Variable config
```

On **FILESERVER_IP**, repeat with `-Role fileserver` instead. This is the agent that must read the file server's Security log; workstation agents cannot read it automatically.

On both devices, check:

```powershell
Get-ScheduledTask -TaskName NileHopeFileControl | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName NileHopeFileControl
Get-Content "$env:ProgramData\FileControl\agent.log" -Tail 25 -ErrorAction SilentlyContinue
```

A running long-lived task can show a running result rather than a completed `0`. Enrollment success is established by a recent heartbeat in **Devices** and a locally created protected `key.txt`, not by task registration alone. Allow approximately 90 seconds under healthy network conditions.

Do not copy `key.txt` from one machine to another. Keep existing keys during upgrades. If a machine was reimaged with a previously enrolled hostname, investigate the server-side enrollment conflict instead of cloning identities or continually retrying enrollment.

## 7. Register the pilot share and keep the approval workflow unused

In the console at `http://localhost:8080` on the console PC:

1. Confirm both physical devices are online under **Devices**.
2. Open **Shared folders > Register share**.
3. Choose Windows and enter an exact path such as `\\FILE01\FG-Pilot`.
4. Confirm the path uses the file server's real enrolled hostname.
5. Wait for the next configuration refresh.

Registering a path changes observation scope. It does not change SMB or NTFS permissions, grant the agent an approval rule, or prove protection.

The existing Compose configuration sets these values for this pilot:

```text
ENABLE_DIRECTORY_WRITES=0
ENABLE_REMOTE_COMMANDS=0
STAFF_REQUESTS_ENABLED=0
ENROLLMENT_ENABLED=1
```

Keep directory writes and staff requests disabled. No AD approval groups or LDAP write account are required for the static NTFS rule below. The existing console can still display its Approvals page; these instructions do not remove that UI. Merely turning a policy switch on in FileGuard does not deny deletions.

## 8. Configure Windows auditing on the file server

Use a separate GPO linked to the **file-server OU**, rather than all workstations. Configure:

```text
Computer Configuration > Policies > Windows Settings > Security Settings
  > Advanced Audit Policy Configuration > Audit Policies > Object Access
    Audit Detailed File Share: Success and Failure
    Audit File System: Success and Failure
```

Use the organization's advanced audit-policy settings consistently; the Security Option **Audit: Force audit policy subcategory settings ... to override audit policy category settings** is normally used to prevent legacy category settings from overriding them. Confirm effective policy with `auditpol /get /category:*` on the file server. Audit-policy names in command output vary by OS language.

For the chosen pilot folder only, open **Properties > Security > Advanced > Auditing** and add the ordinary-staff group from step 9. Apply to **This folder, subfolders and files**, audit **Success and Failure**, and select **Delete** and **Delete subfolders and files**. This is the SACL; it records operations and does not grant/deny access. Use an account with permission to manage auditing. Review Security log capacity/retention before enabling this on busy shares; Detailed File Share can generate substantial traffic outside the paths FileGuard subsequently filters.

Inspect recent events directly on the server:

```powershell
Get-WinEvent -FilterHashtable @{ LogName='Security'; Id=5145,4656,4663,4660; StartTime=(Get-Date).AddMinutes(-10) } -MaxEvents 30 | Select-Object TimeCreated, Id, Message
```

**Current console limitation:** `FileControlAgent.ps1` forwards only 5145 records containing a DELETE access request for registered shares. Microsoft states that a 5145 failure indicates a denial at the share-permission level, not an NTFS denial. Therefore an NTFS-blocked deletion can lack a corresponding blocked entry in this console, and an allowed share access check can precede an NTFS rejection. Use 4656 failure events with the matching Delete/DELETE_CHILD rights to verify NTFS denial. 4660 identifies a completed deletion but needs correlation with other records for the filename. The current agent does not ingest those file-system events; displaying them accurately needs an implementation change.

## 9. Configure deletion denial on the NEW pilot share

On a domain management machine, create a dedicated security group such as `FC-Share-NoDelete` and add only the ordinary pilot users. Keep privileged admin/service accounts outside it. Avoid an Everyone/Domain Users deny entry: administrative accounts may also be members of broad groups and would inherit the denial. Make staff group membership part of user provisioning before wider deployment.

After group changes, sign the pilot user out and back in and reconnect only that user's pilot SMB mapping so the current access token is used. Do not disconnect all SMB sessions on the file server.

On **FILESERVER_IP**, create the new empty pilot folder/share using Server Manager or Explorer. In **Share permissions**, grant the dedicated staff group **Change** and required administrator accounts **Full Control**. Keep share access scoped to intended users; do not grant staff Full Control. NTFS below supplies the granular deletion restriction.

In **the pilot folder's Properties > Security > Advanced**:

1. Ensure SYSTEM and the server's Administrators group have Full Control on this folder, subfolders, and files before changing inheritance.
2. For this NEW EMPTY folder, disable inheritance and convert the inherited entries to explicit entries. Review/remove broad staff grants such as Users/Authenticated Users/Everyone Full Control or Modify, while preserving administrative and required service access. Remove any CREATOR OWNER entry granting Full Control in this pilot. Do not use this as a blanket live-share permission reset.
3. Add the dedicated staff group with **Allow**, applying to **This folder, subfolders and files**. In advanced permissions allow Traverse/Execute, List/Read data, Read attributes, Read extended attributes, Create files/Write data, Create folders/Append data, Write attributes, Write extended attributes, and Read permissions. Leave Delete, Delete subfolders and files, Change permissions, and Take ownership unselected. Explorer may describe this combination as Special rather than Modify.
4. Add a separate entry for that same group with **Deny**, applying to **This folder, subfolders and files**, selecting **Delete** and **Delete subfolders and files** only. Both rights matter: deletion can be authorized on the file itself or through DELETE_CHILD on its parent.
5. Restrict file owners' ability to change permissions as well. Add the special identity **OWNER RIGHTS** (`S-1-3-4`) with **Allow Read permissions only**, applying to this folder, subfolders and files. Keep ordinary staff without Change permissions/Take ownership grants through any other identity. Microsoft documents that an OWNER RIGHTS ACE replaces the owner's implicit READ_CONTROL/WRITE_DAC rights; this matters for files newly created by staff. Test this entry on your actual Windows version and ensure admin access remains intact.
6. Use **Effective Access** for the pilot user and inspect representative file/subfolder ACLs. Confirm no delete, delete-child, Change permissions, or Take ownership access remains through other groups, explicit child entries, or privileged roles.

These NTFS permissions act only on the selected server directory tree, including access to that tree locally on the server. They do not distinguish SMB access from another route to that same directory. They do not apply to a staff PC's Desktop, Documents, or C: drive. If users can access the same files via another share, review that route too.

An inherited deny is not proof that every existing child is covered: explicit child permissions are processed before inherited permissions, and protected child ACLs can exclude inheritance entirely. For an existing live share, inventory and back up the entire ACL tree, then reconcile each object's effective permissions with this rule. Do not select a recursive permission replacement or run a volume-wide ACL command without reviewing the existing service/department permissions.

## 10. Test as an ordinary staff account

Use a physical domain PC logged in as the pilot user, with no administrative share credentials cached for this test. Open `\\ACTUAL-FILESERVER-NAME\FG-Pilot`.

| Operation on disposable files | Expected result |
| --- | --- |
| Create a new text file and subfolder | Allowed |
| Read and edit text in an existing file in place | Allowed |
| Delete a file created by an administrator | Denied |
| Delete a file just created by that same staff user | Denied |
| Delete a file inside a newly created subfolder | Denied |
| Delete a subfolder | Denied |
| Rename/move/replace an existing file | Often denied; test each application |
| Save an existing Word/Excel document | May fail when the save requires replace/delete |
| Change permissions on a staff-created file | Denied |
| Create/delete a disposable file on the PC's own Desktop | Behaves as before |

Confirm NTFS failure events in the server's Security log and recent device heartbeats in FileGuard. Validate the actual result on disk; a console access-check label alone is insufficient. NTFS enforcement must continue if the console is temporarily unavailable. Before testing that outage, make sure you can restore console service and are using only the pilot share.

Keep production rollout paused if the actual document workflows fail; Windows cannot universally allow all applications' normal replacement saves while denying those same delete/rename operations through a simple ACL. A different supported enforcement/content-management design is needed if seamless Office saves and an absolute no-delete rule are both required.

## 11. Enable automatic installation through GPO

After the manual two-device pilot succeeds, create an OU for pilot workstations and use the existing designated file-server OU. Preserve the organization's OU/GPO design; do not move domain controllers into the workstation OU.

In **Group Policy Management**:

1. Create a GPO named `FileGuard - Agent Startup` and link it to the pilot workstation OU. Also link to the intended file-server OU or use an equivalent separate server GPO containing the same bundle.
2. Use computer security filtering that grants the intended **computer accounts** Read and Apply Group Policy. Scope is determined by links/filtering, not by the bundle's `pilot` ring label.
3. Edit **Computer Configuration > Policies > Windows Settings > Scripts (Startup/Shutdown) > Startup > PowerShell Scripts**.
4. Choose **Show Files**, then copy all four files from `gpo-deployment` into this startup folder. Confirm the permissions restrict bundle read/write appropriately.
5. Choose **Add**, select `Startup-Agent.ps1`, and save. Copying files into SYSVOL without adding the startup-script entry is not sufficient.
6. In the pilot computer policy enable **Computer Configuration > Policies > Administrative Templates > System > Logon > Always wait for the network at computer startup and logon** where needed, so startup can read the domain policy. Account for the added boot wait on offline laptops.
7. Apply the certificate-trust policy before expecting agent HTTPS connectivity. On a pilot PC run `gpupdate /target:computer /force`, then restart during the pilot window.
8. Confirm policy scope with `gpresult /scope computer /r`, the task/state files, and the console heartbeat. Troubleshoot under **Applications and Services Logs > Microsoft > Windows > GroupPolicy > Operational** if the startup installer did not run.
9. Extend the validated policy link/filter to the intended workstation OUs and file-server OUs. Only the known file-server names in `deployment.json` receive file-server mode. New file servers must be added to that list or installed explicitly as fileserver.

After installation, the scheduled task starts at every device startup without a user signing in. The startup wrapper preserves the per-device key and skips reinstalling an unchanged agent/configuration. GPO is a startup deployment mechanism, not an immediate event handler for the instant a computer joins the domain.

## 12. Make new domain joins receive the policy automatically

A new computer must be created/moved into a GPO-covered OU and reboot with domain network access. The default AD **Computers** container is a CN container, not an OU to which this GPO can be directly linked.

Preferred: pre-stage computer accounts in the correct workstation OU or use the normal deployment tool's OU option. A local administrator can join a new PC with approved join credentials and an explicit OU, for example:

```powershell
Add-Computer -DomainName 'YOUR-DOMAIN-FQDN' -OUPath 'OU=FileGuard-Workstations,DC=YOURDOMAIN,DC=LOCAL' -Credential (Get-Credential) -Restart
```

Replace the entire domain and OU distinguished name with the real existing objects. After the reboot and successful policy processing, installation/enrollment occurs automatically. Windows domain join, GPO application, console reachability, certificate trust, and open enrollment must all succeed; it is not guaranteed at the exact instant the join completes.

For existing computers use AD Users and Computers to move their computer accounts to the already reviewed OU, refresh policy, and reboot. If automatic default placement is desired, the AD administrator can review Microsoft's `redircmp` procedure to redirect newly created computer accounts to an OU. This is a domain-wide provisioning decision and does not move existing computer accounts.

Continuous automatic enrollment requires `ENROLLMENT_ENABLED=1` and a valid token in the bundle. The current application authenticates bootstrap enrollment with that shared token, not an AD machine-certificate or domain-join attestation. Restrict network access and bundle access, and rotate the shared bootstrap token through your deployment process when necessary. Closing enrollment prevents new devices from enrolling; existing device keys keep working. The bundle generator's printed suggestion to close enrollment after a batch is incompatible with indefinitely open automatic onboarding, so choose the model deliberately.

## 13. Expand to existing shares with rollback prepared

After the disposable pilot passes, identify each exact share and local folder on FILESERVER_IP. Back up file contents and security information through the normal server backup process. As an additional DACL snapshot, for an example existing folder:

```powershell
New-Item -ItemType Directory -Path 'C:\FileGuardAclBackups' -Force | Out-Null
icacls 'D:\Shares\Finance' /save 'C:\FileGuardAclBackups\Finance-before.acl' /T
if ($LASTEXITCODE -ne 0) { throw 'ACL backup did not complete; investigate before changing permissions.' }
Get-SmbShareAccess -Name 'Finance' | Export-Clixml 'C:\FileGuardAclBackups\Finance-share-access.xml'
```

These are placeholders: use the actual share/local path. `icacls /save` saves DACLs, not file contents, owners, auditing SACLs, or SMB share configuration. Keep full backups for those. Record administrative, backup, scanning, and application-service access before changing any existing permission tree.

Review and apply the tested staff restriction only to approved share paths, preserve required service/admin access, and confirm every existing/new descendant is covered. Roll out one share/department at a time with the same ordinary-user tests. Do not replace all child permissions simply to remove exceptions.

To restore the example DACL snapshot, use an administrator account and the matching parent path:

```powershell
icacls 'D:\Shares' /restore 'C:\FileGuardAclBackups\Finance-before.acl'
```

Verify the restored permissions. Restore any SMB or audit settings separately from the recorded configuration/full security backup. Existing open handles may retain rights granted before an ACL change; test with newly opened files and fresh pilot sessions. Coordinate any necessary session closure with the affected user rather than disconnecting all users.

Unlinking the installation GPO does **not** remove an installed scheduled task or undo file-server ACLs. For a single pilot agent rollback, disable/stop that machine's `NileHopeFileControl` task after removing it from deployment scope, preserve its key/state securely, and remove only FileGuard's reviewed additions. Do not remove a broadly trusted CA or unrelated firewall rules.

## Troubleshooting

| Symptom | First checks |
| --- | --- |
| Port 8443 unavailable | Console awake; Docker/gateway running; correct console address; approved firewall scope/routing |
| TLS trust error | Matching host in URL/certificate; root imported into Local Computer; device clock |
| No task after domain join | Computer OU, GPO link, computer Read/Apply permissions, startup script registration, SYSVOL access, reboot |
| Enrollment 403 | Token matches console; enrollment is open; correct HTTPS gateway |
| Enrollment 409 | Duplicate hostname from a previous installation/reimage; do not clone key.txt |
| Device online, no share checks | Fileserver role, real hostname in UNC, registered share, audit policy enabled, fresh matching events |
| No blocked row for an NTFS denial | Known 5145-only collector limitation; inspect 4656 failure/SACL directly on file server |
| File can still be deleted | Parent DELETE_CHILD, explicit child grants, protected inheritance, other identities, admin session, existing open handles |
| Staff-created file is deletable or permissions editable | Creator/owner grants, OWNER RIGHTS entry, other group permissions, actual effective access |
| Word/Excel save fails | Replacement/rename/delete denied by design; halt expansion and resolve workflow/design |

## References

- [Microsoft: Group Policy scope](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/group-policy/group-policy-scope)
- [Microsoft: Redirect default computer containers](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/redirect-users-computers-containers)
- [Microsoft: Distribute certificates by Group Policy](https://learn.microsoft.com/en-us/windows-server/identity/ad-cs/distribute-certificates-group-policy)
- [Microsoft: DeleteFile and the alternative file/parent delete rights](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile)
- [Microsoft: icacls permissions and backup/restore](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls)
- [Microsoft: ACE evaluation order](https://learn.microsoft.com/en-us/windows/win32/secauthz/order-of-aces-in-a-dacl)
- [Microsoft: OWNER RIGHTS special identity](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-special-identities-groups)
- [Microsoft: Audit File System and SACL requirements](https://learn.microsoft.com/windows/security/threat-protection/auditing/audit-file-system)
- [Microsoft: Event 5145 and its share-level denial limitation](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-5145)
- [Microsoft: Event 4656](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4656)
- [Microsoft: Excel save workflow and required delete permissions](https://learn.microsoft.com/en-us/office/troubleshoot/excel/issue-when-save-excel-workbooks)
