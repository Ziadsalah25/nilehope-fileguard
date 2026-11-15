# Start on your Windows PC

## 1. Install Docker Desktop

Use the official [Docker Desktop Windows installer](https://docs.docker.com/desktop/setup/install/windows-install/). Select the WSL 2 backend, finish any Windows/virtualization prerequisites, and restart when requested. Open Docker Desktop and wait until the engine runs with **Linux containers**.

Docker Desktop is for your supported Windows PC. For a Windows Server deployment, run these Linux containers on a supported Linux Docker host/VM; run the Windows monitoring/recovery agents on their Windows hosts.

## 2. Download the project

On GitHub select **Code → Download ZIP** and extract it into a normal local folder. You can launch the project directly from File Explorer; Codex is optional. For help through a local Codex session, open that same folder and give the session terminal access to your PC.

## 3. Start the console

Double-click `Start-Console-Only.bat`. It checks Docker, generates private credentials, builds the frontend/backend images, starts MySQL and the service containers, and opens the browser after health checks pass.

To start only the console without installing the separate Windows monitoring agent, use PowerShell in the extracted project folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Local.ps1 -SkipWindowsAgent
```

`Start-Local.bat` additionally installs a separate read-only Windows monitor after a Windows administrator prompt. Start with the console-only launcher until you choose to add that agent.

The launcher needs no host Python or Node installation. Image downloads and the first build can take several minutes. Open `http://localhost:8080` on this same PC. Login details are opened from `.local\login.txt` and stored privately with `.env`.

If Docker Desktop is running but the launcher says it cannot find Docker, update the project code and retry. The launcher now checks both PATH and the standard system/per-user Docker Desktop folders, then uses the executable's full path. It adds Docker's command directory only to its own process environment. No permanent PATH change is needed. If the CLI files themselves are missing, complete or repair Docker Desktop setup.

## 4. Verify and stop

Check **System & database** for healthy connections. The first ordinary startup has no hospital device enrollment or recovery agent. Add devices after the local console works. The C# recovery lab additionally needs .NET 10; see the root README.

MySQL Workbench on this PC: host `127.0.0.1`, port `13306`, schema `nilehope_fileguard`; account details are in `.env`.

Use `Stop-Local.bat` to stop the stack. Startup diagnostics are in `.local\startup.log` and `.local\startup-errors.log`. If the browser cannot connect, first check that the frontend is healthy in Docker Desktop and that the launcher completed successfully.
