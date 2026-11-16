# NileHope FileGuard — Complete Project Handoff

**Updated:** 2026-11-16  
**Purpose:** Consolidated requirements, implementation record, deployment instructions, troubleshooting, and next steps.  
**Application and launcher baseline:** `37030d18d01d16ac4419dfdf5a854ffab5454ab0`  
**Current status:** Prototype implemented and tested; startup on the user's Windows PC is still awaiting confirmation.

## 1. Current position

The public project repository is available at:

- [GitHub repository](https://github.com/Ziadsalah25/nilehope-fileguard)
- [Latest source ZIP](https://github.com/Ziadsalah25/nilehope-fileguard/archive/refs/heads/main.zip)
- [Validated application/launcher baseline ZIP](https://github.com/Ziadsalah25/nilehope-fileguard/archive/37030d18d01d16ac4419dfdf5a854ffab5454ab0.zip)
- [Successful baseline CI run](https://github.com/Ziadsalah25/nilehope-fileguard/actions/runs/43705535904)

The backend, database, frontend, monitoring agents, and recovery prototype have been built and tested. The user's Windows screenshots established that Docker Desktop is installed and that the launcher can locate its CLI. Two launcher defects were corrected: Docker CLI discovery and numeric SID formatting for Windows permissions.

**The latest Windows attempt stopped at the Docker engine-type check.** The launcher did not receive exactly `linux`. Its actual raw output has not yet been supplied, so Windows-container mode is a possible cause, not a confirmed diagnosis. There is no confirmed successful browser login or healthy FileGuard stack on that PC yet.

Earlier isolated Docker and recovery tests ran in the assistant's remote Linux workspace. That test application was subsequently stopped. There is no public application preview deployed and no confirmed hospital connection.

## 2. Requirements and accepted decisions

| Topic | Accepted direction |
|---|---|
| Product | NileHope FileGuard: monitoring, version history, and recovery after deletion |
| First deployment | Run the console on the user's Windows PC using Docker Desktop |
| Hosting preference | Local/server deployment; no ongoing cloud application hosting |
| Server packaging | Docker Compose with separate frontend, console API, ingestion API, background worker, and MySQL containers |
| Web stack | Retain React/TypeScript, Python/Flask, and MySQL |
| Recovery agent | Add a C#/.NET 10 Windows-Service-capable worker |
| Device monitoring | Windows and Linux |
| Linux file monitoring | Observe changes in selected folders, in addition to system health |
| First recovery scope | One disposable lab folder, with separate repository and state directories |
| Recovery behavior | Preserve stable versions and restore after deletion according to local policy |
| Initial controls | Monitoring first; remote restrictions and directory writes disabled |
| Database inspection | MySQL Workbench on the user's PC |
| Repository | Public repository owned by `Ziadsalah25` |
| Working preference | Explain steps and ask about meaningful feature, scope, and architecture choices |

The long-term request includes a central console for hospital devices and approved file shares. That goal does not mean hospital agents are currently installed or that file-share integration is complete. Broad share monitoring and automatic recovery are separate scopes; recovery starts with the disposable lab.

The supplied product plan is proposal/reference material. The user chose to retain Python and MySQL rather than adopt every suggested technology in that document. Proposed phases and suggested commands are not evidence that a feature has been implemented or deployed.

## 3. What FileGuard does

### Monitoring and console

- Administrator sign-in, CSRF protection, session handling, and login lockout.
- Device enrollment and individual device API keys, stored as hashes on the server.
- Device inventory, heartbeats, operating-system information, and supported telemetry.
- Windows monitoring agent for endpoint information and scoped SMB audit metadata.
- Linux monitoring agent for health and selected-folder create/modify/delete observations.
- Folder registration, searchable file activity, CSV export, administrator audit, and database inspection.
- A React interface with responsive layouts, a dark theme, and Arabic/RTL support in the existing console views.
- A Recovery & versions page showing actual agent-reported version and restore metadata.

Windows SMB event 5145 describes an access check. An allowed access check is not proof that deletion occurred. Linux observations and recovery-agent events are reported separately.

### Recovery prototype

- Capture stable file contents in a separate version repository.
- Preserve version identifiers, SHA-256 hashes, sizes, and basic modification timestamps.
- Restore a missing file when the local lab policy enables automatic recovery.
- Verify repository content before restoring and verify the restored copy.
- Preserve existing destinations through no-overwrite promotion and conflict handling.
- Persist a manifest, local audit records, and an outgoing event queue.
- Continue the local scan/recovery loop during a management API outage.
- Pause on unavailable roots or incomplete scans instead of treating all missing entries as deletions.
- Limit repeated automatic restores per file; the default is three restores per minute.
- Exclude links/reparse points and temporary/database working files; apply a default 100 MiB file-size limit.

An oversized current file can suspend protection rather than cause an older version to be silently restored. Review the agent's status and recovery reports.

**This is recovery after deletion, not guaranteed pre-delete blocking.** A file can disappear before it is restored. Only versions already captured successfully can be recovered.

## 4. Architecture and source layout

```text
Browser / React console
          |
       Nginx
       /   \
Console API  Agent API <--- Windows / Linux monitoring agents
       \   /          <--- C# recovery agent: metadata only
        MySQL
          ^
   Background worker

C# recovery agent on its protected host:
  one lab folder <--> recovery engine --> separate version repository
                              |
                       manifest / audit / outbox
```

| Container service | Role |
|---|---|
| `frontend` | Nginx serving the compiled React app and proxying API requests |
| `backend` | Flask console API and administrator functions |
| `agent-api` | Separate Flask ingestion process for agents |
| `worker` | Background processing and worker health |
| `database` | MySQL 8.4 with a persistent named volume |
| `initialize` | One-time/idempotent schema and initial account setup; exits after success |
| `lab-agents` | Optional, explicitly synthetic demonstration devices |

The three Python service processes share a package and database. They are separate container roles, not independently owned domain services with separate persistence.

The native monitoring/recovery agents run on their device or file server. They are not automatically installed on hospital PCs by starting the web containers.

```text
apps/console/                   React dashboard
services/management/app/        Python APIs, audit, schema, and worker
agents/windows-monitor/        PowerShell monitoring agent and deployment tools
agents/windows-recovery/       C# recovery engine and Windows Service hosting support
agents/linux/                  Linux health and selected-folder monitoring
deploy/containers/             Frontend images and proxy configuration
deploy/local/                  Windows Docker discovery, permissions, and local helpers
deploy/windows/                Earlier native Windows monitoring deployment tools/templates
scripts/                       Configuration, lab launch, and browser validation
tests/                         Python, C#, and native Windows launcher checks
docs/                          Product plan, architecture, setup, evidence, and roadmap
```

## 5. Windows, Linux containers, and WSL

The first console is hosted on a **Windows PC**, while its Docker images require a **Linux container engine**. Choosing a Windows host does not make these images Windows containers.

Docker Desktop can provide the Linux environment through WSL 2, or through its Hyper-V backend on supported Windows editions. The launcher does not install WSL itself. Docker Desktop's backend setup may request it.

Windows endpoint agents run natively and do not need WSL. A Linux Docker server can run the server containers directly. For a Windows Server deployment, use a supported Linux Docker host/VM for these images; Docker Desktop on a Windows PC is the current testing route.

## 6. Immediate next step: resolve the current engine check

Open **PowerShell on the Windows PC** and run:

```powershell
& "C:\Program Files\Docker\Docker\resources\bin\docker.exe" info --format '{{.OSType}}'
```

| Result | Next action |
|---|---|
| `linux` | Linux mode is selected. Capture the exact output/context and investigate the launcher's mismatch before changing engines. |
| `windows` | The selected Docker endpoint is a Windows engine. For this deployment, select the intended local Linux engine. |
| Error, blank, or another value | Inspect Docker Desktop's readiness and the selected Docker context; do not assume the engine type. |

Read-only checks if needed:

```powershell
$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
& $docker version
& $docker compose version
& $docker context show
```

For Docker Desktop, right-click the whale icon in the Windows notification area. If the menu offers **Switch to Linux containers...**, that is the relevant mode change. If it offers **Switch to Windows containers...**, Desktop is already in Linux mode. Account for other running containers before switching engine modes on a shared machine.

**Do not mark this blocker resolved until the raw engine response and successful startup are observed.**

## 7. Start the Windows console

1. Download/extract the current project code, including its `deploy/local/` helpers.
2. Keep Docker Desktop running with the intended Linux container engine.
3. In the extracted folder containing `docker-compose.yml`, double-click **`Start-Console-Only.bat`**.

Equivalent command from PowerShell in that folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Local.ps1 -SkipWindowsAgent
```

The launcher:

1. Locates Docker on PATH or in standard system/per-user installation folders.
2. Checks the engine and Compose v2; starts Desktop if appropriate and waits for it.
3. Protects `.local` and `.env` using Windows permissions.
4. Generates random local credentials if `.env` does not already exist.
5. Uses the Compose project name `nile-local-pc` for the ordinary local installation.
6. Builds and starts MySQL, initialization, APIs, worker, and frontend.
7. Waits for service health and checks the API/frontend health endpoints.
8. Opens the browser and the private local login file after success.

The console-only launcher does not install the Windows agent. `Start-Local.bat` also attempts a separate Windows monitoring-agent installation after the console starts and requests normal Windows elevation for that step.

The Docker console requires no host Python or Node installation. The first image download/build can take several minutes. The C# recovery lab has additional requirements described below.

### Local addresses and files

| Item | Default |
|---|---|
| Browser | `http://localhost:8080` on the PC running Docker |
| API/database health | `http://localhost:8080/healthz` |
| Frontend health | `http://localhost:8080/frontend-health` |
| Login details | `.local\login.txt` |
| Runtime credentials/settings | `.env` |
| Startup output | `.local\startup.log` |
| Startup error output | `.local\startup-errors.log` |

These files/logs appear only after startup reaches the corresponding stage. The last screenshot stopped before the container build stage.

Codex is optional for manual startup. A Codex session needs actual terminal access to the PC to operate it directly. The assistant session used in this conversation has a remote Linux terminal; authorization alone does not give it access to the user's Windows machine.

## 8. Windows launcher fixes already delivered

| Observed failure | Cause / response | Code baseline |
|---|---|---|
| Docker Desktop installed but launcher could not find `docker.exe` | Added system/per-user installation discovery, full-path invocation, and process-local PATH setup for Docker helpers. | `d516315` |
| Older Windows PowerShell could misread Unicode scripts | Saved affected Unicode scripts with a UTF-8 BOM. | `d59b3a3` |
| `No mapping between account names and security IDs was done` | Corrected numeric SID grants by adding the `*` prefix required by `icacls`; shared helper protects both `.local` and `.env`. | `37030d1` |
| `Switch to Linux containers` message | Still being diagnosed. The formatted engine response was not exactly `linux`; raw output is required. | Unresolved runtime state |

Permission tests apply real Windows ACLs to disposable files and verify access for the current user, SYSTEM, and Administrators, restricted child-file inheritance, content preservation, and repeatability. Startup does not intentionally loosen permissions to bypass an error.

When updating an installation that already has credentials or data, preserve `.env`, `.local`, and database volumes. Update the launcher and its helper files together.

## 9. MySQL and Workbench

| Workbench setting | Windows local test |
|---|---|
| Method | Standard TCP/IP |
| Host | `127.0.0.1` on the Docker host |
| Port | `13306` |
| Schema | `nilehope_fileguard` |
| Account | `MYSQL_USER` / `MYSQL_PASSWORD` from the private `.env` |

The SQL download is also available through **System & database**. The fresh MySQL schema is in `deploy/windows/schema.mysql.sql`.

Current tables: `admins`, `devices`, `file_events`, `requests`, `audit`, `settings`, `folders`, `probes`, `device_commands`, and `recovery_events`.

```sql
SELECT hostname, os_family, agent_version, last_seen
FROM devices ORDER BY hostname;

SELECT kind, COUNT(*) AS event_count
FROM recovery_events GROUP BY kind;

SELECT ts, relative_path, kind, sha256
FROM recovery_events ORDER BY id DESC LIMIT 100;
```

Workbench on another PC needs an approved route or tunnel to the Docker host. A remote workspace's `localhost` cannot be opened on the user's PC to reach that workspace. MySQL remains bound to loopback in the default test setup.

## 10. Devices, shares, and initial operating mode

First establish a healthy local console. Then choose one Windows test PC and enroll its monitoring agent. The separate local-test installer is `deploy/local/Install-ThisPC.ps1`; it requires administrator access and should be selected deliberately after the console works.

Windows monitoring and the C# recovery service are separate components. Linux monitoring uses `agents/linux/`, selected folders, and a dedicated service identity. Remote devices require a reachable HTTPS endpoint and trusted certificates. The optional local LAN configuration uses Caddy on port 8443 with explicitly scoped client-network firewall rules; it is not enabled by ordinary console startup.

Default behavior:

- Remote restriction commands: disabled.
- Directory membership writes: disabled.
- Anonymous staff request entry: disabled.
- No hospital share registered by default.
- No automated hospital-wide agent deployment.
- No hospital recovery scope enabled by starting the console.

The retained Windows command allowlist includes Group Policy refresh, USB storage blocking, restoration of the saved USB storage setting, SMB session disconnection, and diagnostic collection. These are separate controls, disabled in the initial Compose configuration. USB restoration uses a value previously saved by the agent, not a guessed setting.

Optional `demo` mode creates clearly labeled `SIM-*` devices and synthetic activity. Those records do not establish connectivity to real PCs or hospital servers.

## 11. Recovery lab after the console works

The supplied lab launcher requires Python and the supported .NET 10 SDK on the lab host, in addition to the running console. These are additional lab tooling requirements, not requirements for starting the Docker console.

From the project folder:

```powershell
python scripts/start_recovery_lab.py
```

Keep the worker running, then open another terminal:

```powershell
python scripts/check_recovery_lab.py
```

The lab uses only:

```text
.local/recovery-lab/protected/    Disposable live files
.local/recovery-lab/repository/   Protected version copies
.local/recovery-lab/state/        Manifest, audit, credentials, and outbox
```

The validation creates a unique sample, preserves its initial and modified versions, deletes it, checks restored bytes/SHA-256, and writes `.local/recovery-lab/validation.json`. Results should appear under **Recovery & versions**. Stop the foreground agent with Ctrl+C. This command does not install a Windows Service.

The generic recovery configuration sample defaults `autoRestore` to false. The explicit disposable-lab launcher enables it for its own lab scope. Neither setting enables recovery across hospital shares.

Windows Service hosting support is implemented, but a signed installer, dedicated service-account deployment, and real Windows Server service installation remain future work. See `agents/windows-recovery/README.md` for publishing/runtime details.

## 12. Validation completed and its limits

| Check | Recorded result |
|---|---|
| Python API tests | 48 passed with SQLite; the same 48 passed against a separate disposable MySQL schema |
| C# recovery engine | 10 Linux scenarios; Windows-compatible scenarios also passed on a Windows CI runner |
| Frontend | TypeScript/Vite production build passed; runtime Nginx image built |
| Backend | Container image built; console and agent roles exercised |
| Existing browser flows | 11 browser test groups passed |
| Recovery page | Actual reports, search, desktop rendering, mobile layout, and no JavaScript errors verified |
| Offline operation | A disposable file restored during an API outage; three queued reports drained after reconnection |
| Docker discovery | Regression checks passed in Windows PowerShell 5.1 and PowerShell 7 |
| Local configuration permissions | Real native Windows ACL checks passed in both PowerShell versions |
| CI baseline | All jobs in run `43705535904` succeeded |
| User's Windows PC | Docker detection observed; full application startup/login not yet confirmed |
| Hospital deployment | Not completed or validated |

The isolated Docker workspace used an existing lab MySQL container with separate FileGuard application/test schemas and an independent account to fit its limited disk. The public Compose file uses upstream `mysql:8.4` and its own named volume. Those environment-specific test overrides and credentials are not in the public repository.

An observed 0.2-second sample recovery check is not a recovery-time guarantee. CI and disposable tests do not prove clinical workload consistency, sustained performance, or production readiness.

## 13. Current limitations and planned work

- Stable content and basic timestamps are preserved; full NTFS ACLs, ownership, alternate streams, and application consistency are not validated.
- Rename/move currently appear as a new path plus a missing old path. Auto-restore can recreate the old name. Complete identity-aware rename/move handling is future work.
- Directory recovery requires review; the prototype does not automatically rebuild missing parent trees.
- Local backup folders are a proof-of-concept repository, not hardened ransomware protection.
- Destructive retention cleanup and remote restore commands are not implemented. Lab capacity must be managed deliberately.
- USN Journal integration, crash/power-loss drills, and large-volume stress tests remain.
- Windows Service installation, dedicated service-account permissions, signing, and secure updates remain.
- Full administrator/operator/auditor RBAC and reliable initiating-user/process attribution remain.
- Central policy assignment, maintenance modes, advanced incident workflows, and hardened/immutable backup integration remain.

Do not infer the deleting user from a service account, and do not equate a displayed monitoring target with active content recovery.

## 14. Diagnostics, stopping, and data preservation

After startup has reached the build stage, inspect local logs from PowerShell in the project folder:

```powershell
Get-Content -LiteralPath .local\startup.log -Tail 80
Get-Content -LiteralPath .local\startup-errors.log -Tail 80
```

Inspect the ordinary Windows stack without creating a second Compose project:

```powershell
$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
& $docker compose -p nile-local-pc -f docker-compose.yml -f compose.local.yml ps
& $docker compose -p nile-local-pc -f docker-compose.yml -f compose.local.yml logs --tail 80 backend agent-api frontend database worker
```

Demo mode uses a different project name, `nile-local-demo`. The local launcher records its actual project in `.local/compose-project.txt`.

Use **`Stop-Local.bat`** to stop the local application. It retains database volumes and credentials. Avoid using `down -v` as a routine troubleshooting command because it removes named volumes. Back up the database and protected recovery data before any intentional reset or migration.

Public source excludes runtime passwords, device keys, databases, populated hospital profiles, and device inventories. Keep `.env`, `.local/login.txt`, enrollment credentials, repository contents, and populated deployment profiles private.

## 15. Next actions and decisions

1. Obtain the exact Docker engine-type response from the user's Windows PC.
2. Resolve engine selection/readiness or launcher parsing based on that evidence.
3. Rerun the latest console-only launcher and confirm healthy containers, browser access, and login.
4. Confirm MySQL Workbench reaches the same local schema.
5. Select and enroll one Windows monitoring test device.
6. Run the disposable recovery lab and record Windows-specific results.
7. Choose retention/version limits, storage capacity, hardened repository location, service identity, and a non-critical Windows file-server pilot folder.
8. Plan trusted HTTPS/LAN enrollment and Linux devices after the first Windows test works.
9. Expand to approved hospital shares only after the pilot, operational scope, and rollback are reviewed.

Earlier Drive/email bundle delivery was cancelled. Repository delivery remains the current method; do not resume cancelled transfers. No ongoing public web preview or cloud-hosted hospital console is requested.

## 16. Short continuation brief

> Continue NileHope FileGuard from application baseline `37030d1`. Keep React/Python/MySQL and the C# recovery prototype. The immediate goal is a healthy console on the user's Windows PC using Docker Desktop's Linux engine. Docker executable discovery and numeric SID permission bugs are fixed and Windows regression checks pass. The latest screenshot stops at the strict engine-type comparison; raw output from `docker.exe info --format '{{.OSType}}'` has not been received. Do not assume Windows-container mode or claim the site is already running on the PC. First gather that read-only result, then resolve the actual blocker. Keep monitoring first, recovery limited to disposable lab data, credentials private, and hospital controls disabled. Explain steps and ask about meaningful deployment/feature choices. The current assistant terminal is remote Linux, not the Windows PC.
