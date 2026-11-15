"""Explicitly labelled synthetic agents for the isolated container test only."""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER = os.environ.get("LAB_SERVER", "http://backend:8000")
TOKEN = os.environ["ENROLL_TOKEN"]
STORE = Path("/lab/keys.json")
HOSTS = [
    {
        "hostname": "SIM-FILE01",
        "department": "Training · File services",
        "ip": "192.0.2.10",
        "win_user": "LAB\\file-service",
        "mac": "02:00:00:00:00:10",
    },
    {
        "hostname": "SIM-NURSE01",
        "department": "Training · Nursing",
        "ip": "192.0.2.21",
        "win_user": "LAB\\training-nurse",
        "mac": "02:00:00:00:00:21",
    },
    {
        "hostname": "SIM-LAB02",
        "department": "Training · Diagnostics",
        "ip": "192.0.2.22",
        "win_user": "LAB\\training-lab",
        "mac": "02:00:00:00:00:22",
    },
    {
        "hostname": "SIM-DESK03",
        "department": "Training · Reception",
        "ip": "192.0.2.23",
        "win_user": "LAB\\training-desk",
        "mac": "02:00:00:00:00:23",
    },
]


def post(endpoint, payload, host=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers.update({"X-Device": host, "X-Api-Key": key})
    request = urllib.request.Request(
        SERVER + "/api/agent/" + endpoint,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main():
    if os.environ.get("CONSOLE_ENVIRONMENT") != "test":
        raise RuntimeError("Synthetic agents require CONSOLE_ENVIRONMENT=test")
    from app import audit, create_app, db

    app = create_app()
    keys = json.loads(STORE.read_text()) if STORE.exists() else {}
    for device in HOSTS:
        host = device["hostname"]
        if host not in keys:
            keys[host] = post(
                "enroll", {"hostname": host, "token": TOKEN, "ring": "pilot"}
            )["key"]
            STORE.write_text(json.dumps(keys))
            STORE.chmod(0o600)
        post(
            "heartbeat",
            {
                **device,
                "agent_version": "SIM-1.3",
                "os_family": "linux"
                if host in ("SIM-LAB02", "SIM-DESK03")
                else "windows",
                "os_version": "Synthetic training OS",
                "architecture": "x86_64",
                "cpu_percent": 12,
                "memory_total_mb": 4096,
                "memory_used_mb": 1024,
                "disk_total_mb": 20000,
                "disk_used_mb": 7000,
                "uptime_seconds": 86400,
            },
            host,
            keys[host],
        )
    with app.app_context():
        root = r"\\SIM-FILE01\Training"
        if not db.q("SELECT id FROM folders WHERE path=?", (root,), one=True):
            db.q("INSERT INTO folders (path) VALUES (?)", (root,))
        if not db.q(
            "SELECT id FROM file_events WHERE process=?", ("SIMULATOR",), one=True
        ):
            for day in range(6, -1, -1):
                for i in range(12 + (6 - day) * 3):
                    stamp = (
                        datetime.now(timezone.utc) - timedelta(days=day, minutes=i * 9)
                    ).strftime(audit.FMT)
                    filename = [
                        "training-roster.csv",
                        "sample-inventory.xlsx",
                        "demo-schedule.pdf",
                        "sandbox-notes.txt",
                    ][i % 4]
                    db.q(
                        "INSERT INTO file_events (ts,win_user,device,ip,action,file,process,result) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            stamp,
                            "LAB\\training-user",
                            "SIM-FILE01",
                            "192.0.2.21",
                            "Delete access check",
                            root + "\\" + filename,
                            "SIMULATOR",
                            "blocked" if i % 7 == 0 else "allowed",
                        ),
                    )
            audit.log("lab", "lab.seed", "Synthetic training observations only")
        db.q(
            "UPDATE devices SET last_seen=? WHERE hostname=?",
            (
                (datetime.now(timezone.utc) - timedelta(hours=4)).strftime(audit.FMT),
                "SIM-DESK03",
            ),
        )
    print(
        "Synthetic lab fleet is running: 3 online, 1 deliberately offline. No Windows commands are executed.",
        flush=True,
    )
    while True:
        for device in HOSTS[:3]:
            post(
                "heartbeat",
                {
                    **device,
                    "agent_version": "SIM-1.3",
                    "os_family": "linux"
                    if device["hostname"] == "SIM-LAB02"
                    else "windows",
                    "os_version": "Synthetic training OS",
                    "architecture": "x86_64",
                    "cpu_percent": 12,
                    "memory_total_mb": 4096,
                    "memory_used_mb": 1024,
                    "disk_total_mb": 20000,
                    "disk_used_mb": 7000,
                    "uptime_seconds": 86400,
                },
                device["hostname"],
                keys[device["hostname"]],
            )
        time.sleep(20)


if __name__ == "__main__":
    main()
