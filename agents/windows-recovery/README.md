# C# recovery worker

Supported .NET 10 with Windows Service hosting support. Cloud tests run the same engine in Linux foreground mode; they do not establish Windows NTFS or service readiness.

```powershell
dotnet publish agents/windows-recovery/FileGuard.Recovery.csproj -c Release -r win-x64 --self-contained false -o .local/windows-recovery
```

Install matching .NET and ASP.NET Core runtimes on Windows for this framework-dependent build, or use an approved self-contained publish. Copy `config.example.json` to a protected local configuration file, create its three separate lab directories, and set the local URL/token. Auto-restore defaults off; enable it only for the chosen disposable lab.

```powershell
.local/windows-recovery/FileGuard.Recovery.exe --config C:\FileGuardLab\recovery-config.json
```

Stop the foreground process before registering the executable with Windows Service Control Manager. Specify the same absolute `--config` path. Use a dedicated account with service-logon rights, read access to configuration/live files, and approved write rights to the lab recovery/repository/state. Ordinary share users must not modify configuration, state, or protected copies. Building does not install a service.

Temporary/database working files, links/reparse points, and files above 100 MiB are excluded. Only content and modification timestamps are preserved. Rename/move identity, directory restore, full metadata, crash consistency, hardened storage, retention, and performance need further development and Windows tests.
