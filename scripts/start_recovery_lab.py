"""Run the real C# worker against this installation's disposable local lab."""

import argparse
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", default=shutil.which("dotnet"))
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--enable-recovery", action="store_true", help="Explicitly restore missing files in this disposable lab; default is monitoring.")
    args = parser.parse_args()
    if not args.dotnet:
        raise SystemExit("Install the supported .NET 10 SDK, or supply --dotnet <path>.")
    root = Path(__file__).resolve().parents[1]
    envfile = root / ".env"
    if not envfile.exists():
        raise SystemExit("Configure and start the local Docker console first.")
    values = dict(line.split("=", 1) for line in envfile.read_text().splitlines() if line and not line.startswith("#"))
    if values.get("FC_ENV") != "testing" or values.get("FRONTEND_BIND_ADDRESS", "127.0.0.1") != "127.0.0.1":
        raise SystemExit("This launcher requires an isolated loopback test stack.")
    server = "http://127.0.0.1:" + values.get("FRONTEND_PORT", "8080")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(server + "/healthz", timeout=5) as response:
        if not json.load(response).get("ok"):
            raise SystemExit("Console health check failed.")
    lab = root / ".local/recovery-lab"
    for folder in (lab / "protected", lab / "repository", lab / "state"):
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = lab / "recovery-config.json"
    if not config.exists():
        config.write_text(json.dumps({
            "protectedRoot": str(lab / "protected"), "repositoryRoot": str(lab / "repository"),
            "stateRoot": str(lab / "state"), "autoRestore": args.enable_recovery, "scanSeconds": 1,
            "settleMilliseconds": 300, "serverUrl": server,
            "enrollmentToken": values["ENROLL_TOKEN"], "hostname": "RECOVERY-LAB01",
            "allowInsecureLoopback": True,
        }, indent=2))
        config.chmod(0o600)
    else:
        existing = json.loads(config.read_text())
        if existing.get("protectedRoot") != str(lab / "protected") or existing.get("serverUrl") != server:
            raise SystemExit("Existing lab configuration differs; review it before restarting.")
        existing["autoRestore"] = args.enable_recovery
        config.write_text(json.dumps(existing, indent=2))
    project = root / "agents/windows-recovery/FileGuard.Recovery.csproj"
    if not args.no_build:
        subprocess.run([args.dotnet, "build", str(project), "-c", "Release", "--nologo"], check=True)
    binary = project.parent / "bin/Release/net10.0/FileGuard.Recovery.dll"
    if not binary.exists():
        raise SystemExit("Build the recovery agent before using --no-build.")
    print(f"{'Recovery enabled' if args.enable_recovery else 'Monitoring only'} for disposable lab data: {lab / 'protected'}", flush=True)
    print("Ctrl+C stops the worker. No Windows service is installed by this command.", flush=True)
    child = subprocess.Popen([args.dotnet, str(binary), "--config", str(config)], cwd=root)
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        return child.wait(timeout=20)


if __name__ == "__main__":
    raise SystemExit(main())
