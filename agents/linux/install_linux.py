#!/usr/bin/env python3
"""Install the read-only Linux agent as a least-privilege systemd service."""

import argparse
import getpass
import json
import os
import pwd
import shutil
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--hostname")
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--department", default="")
    args = parser.parse_args()
    if os.geteuid() != 0 or not Path("/run/systemd/system").exists():
        parser.error(
            "Run as root on a Linux host using systemd. Unprivileged agent execution is also supported separately."
        )
    origin = urlparse(args.server)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path.rstrip("/")
    ):
        parser.error("Use a trusted HTTPS console origin URL.")
    if sys.version_info < (3, 10):
        parser.error("Python 3.10+ is required")
    if args.ca_file:
        ssl.create_default_context(cafile=str(args.ca_file))
    source = Path(__file__).with_name("linux_agent.py")
    if not source.is_file():
        parser.error("linux_agent.py must be beside this installer")
    try:
        account = pwd.getpwnam("nile-dlp-agent")
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--user-group",
                "--home-dir",
                "/var/lib/nile-file-control",
                "--no-create-home",
                "--shell",
                shutil.which("nologin") or "/bin/false",
                "nile-dlp-agent",
            ],
            check=True,
        )
        account = pwd.getpwnam("nile-dlp-agent")
    target, config_dir, state = (
        Path("/opt/nile-file-control"),
        Path("/etc/nile-file-control"),
        Path("/var/lib/nile-file-control"),
    )
    target.mkdir(parents=True, exist_ok=True)
    target.chmod(0o755)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dir.chmod(0o750)
    os.chown(config_dir, 0, account.pw_gid)
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    os.chown(state, account.pw_uid, account.pw_gid)
    shutil.copyfile(source, target / "linux_agent.py")
    (target / "linux_agent.py").chmod(0o644)
    config = {
        "server": args.server.rstrip("/"),
        "state_dir": str(state),
        "department": args.department,
    }
    if args.hostname:
        config["hostname"] = args.hostname
    if args.ca_file:
        certificate = config_dir / "console-ca.pem"
        shutil.copyfile(args.ca_file, certificate)
        certificate.chmod(0o644)
        config["ca_file"] = str(certificate)
    configuration = config_dir / "config.json"
    configuration.write_text(json.dumps(config, indent=2))
    configuration.chmod(0o640)
    os.chown(configuration, 0, account.pw_gid)
    if not (state / "key.json").exists():
        token = (
            args.token_file.read_text().strip()
            if args.token_file
            else getpass.getpass("Enrollment token: ").strip()
        )
        if not token:
            parser.error("An enrollment token is required for the first installation")
        token_file = state / "enroll-token.txt"
        token_file.write_text(token)
        token_file.chmod(0o600)
        os.chown(token_file, account.pw_uid, account.pw_gid)
    unit = f"""[Unit]
Description=Nile of Hope read-only Linux monitoring agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nile-dlp-agent
Group=nile-dlp-agent
ExecStart={sys.executable} /opt/nile-file-control/linux_agent.py --config /etc/nile-file-control/config.json
Restart=always
RestartSec=15
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=false
ReadWritePaths=/var/lib/nile-file-control
UMask=0077

[Install]
WantedBy=multi-user.target
"""
    unit_file = Path("/etc/systemd/system/nile-file-control.service")
    unit_file.write_text(unit)
    unit_file.chmod(0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "enable", "--now", "nile-file-control.service"], check=True
    )
    subprocess.run(["systemctl", "restart", "nile-file-control.service"], check=True)
    print(
        "Agent service started. Confirm a Linux heartbeat in the console, then assign selected directories to that hostname."
    )
    print(
        "The service account needs read/traverse permission on monitored folders. No folder permissions were changed."
    )


if __name__ == "__main__":
    main()
