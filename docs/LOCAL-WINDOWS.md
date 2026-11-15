> Earlier monitoring deployment reference. The root README and ARCHITECTURE.md define the current FileGuard scope. Recovery is configured separately in its disposable lab.

# Run the console on your Windows PC

The earlier cloud-workspace localhost address was not your Windows PC. This bundle contains a launcher that starts the services on the machine where you run it.

## Start locally

1. Extract this entire bundle into a new folder on your Windows PC. Keep `apps/console/dist`, `app`, `agent`, and the Compose files together.
2. Start Docker Desktop using its Linux-container / WSL 2 backend. The launcher checks this and reports a clear prerequisite error if Docker is missing. Python and Node do not need to be installed on the Windows host.
3. Double-click **Start-Local.bat**. The first run builds/downloads the container images and can take several minutes. The services must become healthy before the launcher opens the browser.
4. Open **http://localhost:8080** on that same Windows PC. The launcher opens the browser and the private `.local\login.txt` file containing your generated login.
5. Windows will show its normal administrator prompt to install a separate local-test monitoring agent on this PC. Its task is `NileHopeFileControl-LocalTest` and state folder is `%ProgramData%\NileHopeLocalAgent`. It does not replace a hospital agent task or its device key.

A successful start is verified using the actual frontend and database-backed health endpoints. Build output is in `.local\startup.log` and `.local\startup-errors.log`. The application data is retained in its MySQL Docker volume. Credentials stay in the protected local `.env`; the bundle contains no preselected passwords.

The local app uses a separate Compose project identity (`nile-local-pc`) and loopback-only ports. MySQL Workbench on this PC can use `127.0.0.1:13306`, schema `nilehope_fileguard`, and the application database credentials in `.env`. It does not replace an existing server on port 3306.

Advanced options from PowerShell:

```powershell
.\Start-Local.ps1 -Port 8090
# Start the app without installing its local-test Windows agent:
.\Start-Local.ps1 -SkipWindowsAgent
```

Synthetic demo devices are optional, never installed as real hospital inventory. For an isolated demo, use a fresh bundle folder and `-Demo` (separate Compose project `nile-local-demo`). The default local installation starts without simulated devices.

## What Windows and Linux monitoring includes

- OS family/version, architecture, reported user context, IP/MAC where available, agent version, CPU, memory, system-volume usage, uptime, and heartbeat time.
- Windows file-server mode forwards configured SMB audit access checks. Monitoring does not enable auditing or alter NTFS/GPO/USB permissions.
- Linux agents observe file creation, metadata modification and deletion in specific directories assigned to that enrolled hostname. File contents are not opened or uploaded.
- Linux events appear as **Observed change**, rather than allowed/blocked checks. Host-scoped paths let different Linux devices monitor `/srv/shared` independently.

## Connect devices over your local network

Other computers cannot reach your PC through their own `localhost`. Give them the Windows PC's LAN IP or resolvable DNS name using the optional trusted HTTPS endpoint.

In an elevated PowerShell window, from this bundle:

```powershell
.\deploy\local\Enable-LanAgents.ps1 -AgentHost YOUR_PC_LAN_IP_OR_NAME `
  -AllowedClientNetworks YOUR_APPROVED_CLIENT_IP_OR_SUBNET
```

Replace both values with your actual network details. This adds the separate gateway on TCP 8443 and a Windows firewall rule scoped to the supplied client addresses. It does not change the file-server DNS record, SMB, database publication, or file permissions.

It prints the agent URL `https://YOUR_PC_LAN_IP_OR_NAME:8443` and exports only the public CA certificate to `.local\console-root-ca.crt`. Trust that certificate on Windows clients, or pass it as `--ca-file` on Linux. Do not export the Caddy private key. A corporate PKI certificate can replace the local CA for later deployment.

## Install a Linux agent

Use **Devices → Connect endpoint → Linux → Download Linux agent**, or copy `agents/linux/linux_agent.py` and `agents/linux/install_linux.py` from this bundle.

On a Linux system with Python 3.10+ and systemd:

```sh
sudo python3 install_linux.py \
  --server https://YOUR_PC_LAN_IP_OR_NAME:8443 \
  --ca-file console-root-ca.crt
```

Enter the enrollment token locally when prompted; it is `ENROLL_TOKEN` in the PC's protected `.env`. The installer creates the unprivileged `nile-dlp-agent` account and a systemd service. It needs read/traverse permission on selected directories and does not grant itself access or modify their ACLs.

Once the Linux device appears in the console, open **Shared folders → Register share**, choose **Linux directory**, select that enrolled device, and enter an exact directory such as `/srv/shared`. Its next poll establishes a baseline. Subsequent metadata changes appear in File activity. Different hosts can register the same directory path.

The first CPU sample may be unavailable until the next interval. Reported user on Linux is the agent's execution account, not an assertion about every interactive login. In containers, health metrics reflect the kernel/proc view available to the agent.

Polling defaults to 30 seconds and 10,000 files per directory. It does not follow symlink targets or selected roots that resolve through symlinks. Incomplete scans are reported as partial and do not generate invented deletions. Changes created and removed between polls, or same-size changes with restored timestamps, can be missed; this is metadata observation, not tamper-proof content hashing. The protected agent state folder is excluded to avoid self-generated events. A bounded pending queue retries with idempotent event IDs; an overflow reports a coverage gap.

For a loopback-only unprivileged Linux test, the agent also supports `--allow-insecure-localhost --once`. This does not allow plain HTTP to remote LAN addresses. WSL Linux defaults to a `-LINUX` hostname suffix to avoid colliding with the Windows PC's hostname.

## Connect another Windows device

Download the Windows agent from the same dialog. Trust the public console CA on that machine, then run the supplied installer as Administrator using the LAN HTTPS URL and local enrollment token. Use `-Role fileserver` only on a file server that should forward its Security audit events.

## Stop and restart

Double-click **Stop-Local.bat** to stop this local project's containers while keeping database volumes. Stopping the separate SYSTEM-owned local-test agent task can require Administrator rights. Start with **Start-Local.bat** again; initialization preserves the existing administrator, data and enrollment keys.

## Scope of verification

The container stack and Linux agent are tested in the cloud workspace. A Windows PC cannot be launched remotely from this chat without a configured remote session. The supplied PowerShell scripts are syntax-checked; Docker Desktop, UAC, scheduled-task execution and actual Windows metrics must be verified when you run the launcher on your PC.
