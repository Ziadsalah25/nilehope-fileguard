#!/usr/bin/env python3
"""Read-only Linux inventory and selected-directory metadata monitoring. Python 3.10+."""

import argparse
import getpass
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import socket
import ssl
import stat
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger("nile-linux-agent")
VERSION = "1.3.0-linux"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_private(path, data):
    path = Path(path)
    descriptor = os.open(
        str(path) + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(str(path) + ".tmp", path)
    path.chmod(0o600)


def release_name():
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return f"Linux {platform.release()}"


class SystemMetrics:
    def __init__(self):
        self.previous = None

    def collect(self):
        result = {
            "os_family": "linux",
            "os_version": release_name(),
            "architecture": platform.machine(),
            "agent_version": VERSION,
            "win_user": getpass.getuser(),
        }
        try:
            values = [
                int(x)
                for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]
            ]
            total, idle = sum(values), values[3] + values[4]
            if self.previous and total > self.previous[0]:
                result["cpu_percent"] = round(
                    max(
                        0,
                        min(
                            100,
                            100
                            * (
                                1
                                - (idle - self.previous[1]) / (total - self.previous[0])
                            ),
                        ),
                    ),
                    1,
                )
            self.previous = total, idle
        except (OSError, ValueError, IndexError):
            pass
        try:
            memory = {
                line.split(":", 1)[0]: int(line.split()[1])
                for line in Path("/proc/meminfo").read_text().splitlines()
                if ":" in line
            }
            total = memory["MemTotal"]
            available = memory.get("MemAvailable", memory.get("MemFree", 0))
            result.update(
                memory_total_mb=total // 1024,
                memory_used_mb=max(0, (total - available) // 1024),
            )
        except (OSError, ValueError, KeyError):
            pass
        try:
            usage = shutil.disk_usage("/")
            result.update(
                disk_total_mb=usage.total // 1048576, disk_used_mb=usage.used // 1048576
            )
            result["uptime_seconds"] = int(
                float(Path("/proc/uptime").read_text().split()[0])
            )
        except (OSError, ValueError, IndexError):
            pass
        try:
            for interface in sorted(Path("/sys/class/net").iterdir()):
                if (
                    interface.name != "lo"
                    and (interface / "operstate").read_text().strip() == "up"
                ):
                    result["mac"] = (interface / "address").read_text().strip()
                    break
        except OSError:
            pass
        return result


def scan_directory(root, max_files=10000, excluded=None):
    """Only lstat/scandir: file contents are never opened. Symlink targets are not followed."""
    root = Path(root)
    excluded = Path(excluded).resolve() if excluded else None
    entries, warnings, directories = {}, [], [root]
    if not root.is_dir() or root.is_symlink():
        return {}, False, "Selected directory is missing, unreadable, or a symlink."
    while directories:
        directory = directories.pop()
        try:
            with os.scandir(directory) as children:
                for child in children:
                    path = Path(child.path)
                    if excluded and (path == excluded or excluded in path.parents):
                        continue
                    try:
                        metadata = child.stat(follow_symlinks=False)
                    except OSError:
                        warnings.append("Some metadata could not be read.")
                        continue
                    if stat.S_ISDIR(metadata.st_mode):
                        directories.append(path)
                    elif stat.S_ISREG(metadata.st_mode):
                        if len(entries) >= max_files:
                            return (
                                entries,
                                False,
                                f"File limit ({max_files}) reached; increase the configured limit or narrow the target.",
                            )
                        entries[str(path)] = [
                            metadata.st_mtime_ns,
                            metadata.st_size,
                            metadata.st_ino,
                            stat.S_IMODE(metadata.st_mode),
                        ]
        except OSError:
            warnings.append("Some directories could not be read.")
    return entries, not warnings, " ".join(sorted(set(warnings)))


def compare_snapshots(previous, current):
    changes = []
    for path in sorted(current.keys() - previous.keys()):
        changes.append(("Created", path))
    for path in sorted(previous.keys() - current.keys()):
        changes.append(("Deleted", path))
    for path in sorted(current.keys() & previous.keys()):
        if current[path] != previous[path]:
            changes.append(("Modified", path))
    return changes


class Agent:
    def __init__(
        self,
        server,
        hostname,
        state_dir,
        token_file=None,
        ring="pilot",
        department="",
        ca_file=None,
        allow_insecure_localhost=False,
        max_files=10000,
        interval=30,
    ):
        url = urllib.parse.urlparse(server)
        if (
            url.username
            or url.password
            or url.query
            or url.fragment
            or url.path.rstrip("/")
        ):
            raise ValueError(
                "Use a console origin URL without credentials, a path, or query parameters."
            )
        if url.scheme != "https" and not (
            allow_insecure_localhost
            and url.scheme == "http"
            and url.hostname in ("localhost", "127.0.0.1", "::1")
        ):
            raise ValueError(
                "Use trusted HTTPS. HTTP is allowed only for an explicitly selected loopback test."
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", hostname):
            raise ValueError(
                "Use a unique short hostname containing letters, digits, underscores or hyphens."
            )
        if not 1 <= interval <= 3600 or not 1 <= max_files <= 1000000:
            raise ValueError("Interval or file limit is outside the supported range.")
        self.server, self.hostname = server.rstrip("/"), hostname
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_dir.chmod(0o700)
        self.key_file, self.state_file = (
            self.state_dir / "key.json",
            self.state_dir / "watch-state.json",
        )
        self.token_file = (
            Path(token_file) if token_file else self.state_dir / "enroll-token.txt"
        )
        self.ring, self.department, self.interval, self.max_files = (
            ring,
            department,
            interval,
            max_files,
        )
        self.tls = ssl.create_default_context(cafile=ca_file)
        self.tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self.metrics = SystemMetrics()
        self.state = {
            "server": self.server,
            "hostname": hostname,
            "snapshots": {},
            "pending": [],
        }
        if self.state_file.exists():
            loaded = json.loads(self.state_file.read_text())
            if (
                loaded.get("server") != self.server
                or loaded.get("hostname") != hostname
            ):
                raise ValueError(
                    "State belongs to another console or hostname; select a separate state directory."
                )
            self.state = loaded
        self.key = None
        if self.key_file.exists():
            identity = json.loads(self.key_file.read_text())
            if identity["server"] != self.server or identity["hostname"] != hostname:
                raise ValueError(
                    "Device key belongs to another console/hostname. Coordinate re-enrollment before changing it."
                )
            self.key = identity["key"]

    def request(self, endpoint, payload=None, authenticated=True):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers.update({"X-Device": self.hostname, "X-Api-Key": self.key or ""})
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.server + "/api/agent/" + endpoint,
            data=data,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, context=self.tls, timeout=20) as response:
            return json.load(response)

    def enroll(self):
        if self.key:
            return
        if not self.token_file.exists():
            raise RuntimeError(
                "Enrollment token file is missing. Use the installer or provide a protected --token-file."
            )
        token = self.token_file.read_text().strip()
        result = self.request(
            "enroll",
            {"hostname": self.hostname, "token": token, "ring": self.ring},
            authenticated=False,
        )
        self.key = result["key"]
        write_private(
            self.key_file,
            {"server": self.server, "hostname": self.hostname, "key": self.key},
        )
        self.token_file.unlink()
        LOG.info("Enrolled Linux device %s.", self.hostname)

    def ip_address(self):
        try:
            host = urllib.parse.urlparse(self.server).hostname
            addresses = socket.getaddrinfo(
                host, None, socket.AF_INET, socket.SOCK_DGRAM
            )
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((addresses[0][4][0], 9))
                ip = sock.getsockname()[0]
            return ip
        except OSError:
            return None

    def monitor(self, folders):
        messages = (
            [self.state["coverage_warning"]]
            if self.state.get("coverage_warning")
            else []
        )
        partial = bool(messages)
        snapshots = self.state["snapshots"]
        new_events = []
        for root in folders:
            # Configuration is still validated locally before traversing any path.
            if (
                not isinstance(root, str)
                or not root.startswith("/")
                or root == "/"
                or ".." in Path(root).parts
            ):
                messages.append("Invalid or unsupported monitoring target.")
                partial = True
                continue
            if Path(root).resolve() != Path(root):
                messages.append(f"{root}: symlinked roots are not followed.")
                partial = True
                continue
            current, complete, warning = scan_directory(
                root, self.max_files, self.state_dir
            )
            if not complete:
                partial = True
                messages.append(f"{root}: {warning}")
                continue  # Never turn an incomplete scan or lost mount into false deletion events.
            if root in snapshots:
                for action, path in compare_snapshots(snapshots[root], current):
                    new_events.append(
                        {
                            "event_id": uuid.uuid4().hex,
                            "ts": now(),
                            "win_user": getpass.getuser(),
                            "action": action,
                            "file": path,
                            "process": "linux-agent",
                            "result": "observed",
                        }
                    )
            snapshots[root] = current
        # Discard baselines for explicitly removed targets, but do not alter their files.
        self.state["snapshots"] = {
            root: value for root, value in snapshots.items() if root in folders
        }
        if len(self.state["pending"]) + len(new_events) > 20000:
            partial = True
            self.state["coverage_warning"] = (
                "The pending-event limit was reached; some changes were not retained. Review and acknowledge this coverage gap."
            )
            messages.append(self.state["coverage_warning"])
        capacity = max(0, 20000 - len(self.state["pending"]))
        self.state["pending"].extend(new_events[:capacity])
        write_private(self.state_file, self.state)
        while self.state["pending"]:
            batch = self.state["pending"][:200]
            result = self.request("events", {"events": batch})
            if result.get("stored") != len(batch):
                partial = True
                messages.append(
                    "Some queued events are no longer in the configured server scope."
                )
            self.state["pending"] = self.state["pending"][len(batch) :]
            write_private(self.state_file, self.state)
        status = "partial" if partial else "healthy" if folders else "waiting"
        message = "; ".join(messages) or (
            f"{len(folders)} selected directories monitored; file contents are not collected."
            if folders
            else "No Linux directories are configured yet."
        )
        return status, message[:1000]

    def handle_command(self, command, telemetry):
        if not command:
            return
        result = {
            "command_id": command["id"],
            "success": command["command"] == "collect_logs",
            "output": json.dumps(
                {
                    "kind": "Linux agent status",
                    "telemetry": telemetry,
                    "note": "System log contents were not collected.",
                }
            )[:1000]
            if command["command"] == "collect_logs"
            else "This Windows command is not supported by the read-only Linux agent.",
        }
        self.state.setdefault("command_results", []).append(result)
        write_private(self.state_file, self.state)
        self.flush_results()

    def flush_results(self):
        while self.state.get("command_results"):
            self.request("command-result", self.state["command_results"][0])
            self.state["command_results"] = self.state["command_results"][1:]
            write_private(self.state_file, self.state)

    def cycle(self):
        self.enroll()
        self.flush_results()
        # Establish OS identity before requesting the platform-specific folder configuration.
        initial = {
            **self.metrics.collect(),
            "department": self.department,
            "ip": self.ip_address(),
        }
        first = self.request("heartbeat", initial)
        self.handle_command(first.get("command"), initial)
        config = self.request("config")
        status, message = self.monitor(config.get("folders", []))
        telemetry = {
            **initial,
            "monitoring_status": status,
            "monitoring_message": message,
        }
        response = self.request("heartbeat", telemetry)
        self.handle_command(response.get("command"), telemetry)
        LOG.info("Heartbeat sent: %s, %s.", self.hostname, status)
        return telemetry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--server")
    parser.add_argument("--hostname")
    parser.add_argument("--state-dir")
    parser.add_argument("--token-file")
    parser.add_argument("--ca-file")
    parser.add_argument("--department")
    parser.add_argument("--interval", type=int)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--allow-insecure-localhost", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--clear-coverage-warning", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else {}
    for name in (
        "server",
        "hostname",
        "state_dir",
        "token_file",
        "ca_file",
        "department",
        "interval",
        "max_files",
    ):
        if getattr(args, name) is not None:
            config[name] = getattr(args, name)
    default_host = platform.node().split(".")[0]
    if "microsoft" in platform.release().lower():
        default_host = default_host[:57] + "-LINUX"
    config.setdefault("hostname", default_host)
    config.setdefault("state_dir", str(Path.home() / ".local/state/nile-file-control"))
    config.setdefault("department", "")
    if args.allow_insecure_localhost:
        config["allow_insecure_localhost"] = True
    if not config.get("server"):
        parser.error("--server or a configuration file with a server URL is required")
    agent = Agent(**config)
    if args.clear_coverage_warning:
        agent.state.pop("coverage_warning", None)
        write_private(agent.state_file, agent.state)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    handler = logging.handlers.RotatingFileHandler(
        agent.state_dir / "agent.log", maxBytes=5 * 1024 * 1024, backupCount=2
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    while True:
        try:
            agent.cycle()
        except Exception as error:
            # Do not print tokens, request bodies or full credential-bearing configuration.
            LOG.error(
                "Monitoring cycle failed (%s): %s", type(error).__name__, str(error)
            )
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        time.sleep(agent.interval)


if __name__ == "__main__":
    main()
