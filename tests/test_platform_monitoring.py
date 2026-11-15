import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from app import create_app, db, services

spec = importlib.util.spec_from_file_location(
    "linux_monitor", Path(__file__).resolve().parents[1] / "agents/linux/linux_agent.py"
)
linux = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linux)


def admin(client):
    token = client.get("/api/console/session").json["csrf"]
    response = client.post(
        "/api/console/login",
        json={"username": "admin", "password": "TestPassword123!"},
        headers={"X-CSRF-Token": token},
    )
    return {"X-CSRF-Token": response.json["csrf"]}


def enroll(client, name):
    response = client.post(
        "/api/agent/enroll",
        json={"token": "test-enrollment-token", "hostname": name, "ring": "pilot"},
    )
    assert response.status_code == 200
    headers = {"X-Device": name, "X-Api-Key": response.json["key"]}
    assert (
        client.post(
            "/api/agent/heartbeat",
            headers=headers,
            json={"os_family": "linux", "agent_version": "1.3.0-linux"},
        ).status_code
        == 200
    )
    return headers


def test_cross_platform_telemetry_and_validation(app, client):
    headers = enroll(client, "LINUX01")
    telemetry = {
        "os_family": "linux",
        "os_version": "Test Linux",
        "architecture": "x86_64",
        "cpu_percent": 12.5,
        "memory_total_mb": 4096,
        "memory_used_mb": 1024,
        "disk_total_mb": 20000,
        "disk_used_mb": 5000,
        "uptime_seconds": 1234,
        "monitoring_status": "healthy",
        "monitoring_message": "1 selected directory monitored.",
    }
    assert (
        client.post("/api/agent/heartbeat", headers=headers, json=telemetry).status_code
        == 200
    )
    admin(client)
    row = client.get("/api/console/devices").json["items"][0]
    assert (
        row["os_family"] == "linux"
        and row["cpu_percent"] == 12.5
        and row["memory_used_mb"] == 1024
    )
    assert row["telemetry_at"] and "api_key_hash" not in row
    for bad in (
        {"cpu_percent": 101},
        {"cpu_percent": True},
        {"memory_total_mb": 100, "memory_used_mb": 101},
        {"os_family": "other"},
    ):
        assert (
            client.post("/api/agent/heartbeat", headers=headers, json=bad).status_code
            == 400
        )
    with app.app_context():
        assert db.q("SELECT '50%' AS value", one=True)["value"] == "50%"


def test_linux_folder_identity_scope_and_event_deduplication(app, client):
    one = enroll(client, "LINUX01")
    two = enroll(client, "LINUX02")
    csrf = admin(client)
    for host in ("LINUX01", "LINUX02"):
        assert (
            client.post(
                "/api/console/shares",
                headers=csrf,
                json={"path": "/srv/shared", "target_os": "linux", "target_host": host},
            ).status_code
            == 201
        )
    assert (
        client.post(
            "/api/console/shares",
            headers=csrf,
            json={"path": "/srv/other", "target_os": "linux", "target_host": "LINUX02"},
        ).status_code
        == 201
    )
    assert client.get("/api/agent/config", headers=one).json["folders"] == [
        "/srv/shared"
    ]
    assert client.get("/api/agent/config", headers=two).json["folders"] == [
        "/srv/other",
        "/srv/shared",
    ]
    event = {
        "event_id": "test_event_1234",
        "action": "Modified",
        "result": "observed",
        "file": "/srv/shared/example.txt",
        "process": "linux-agent",
    }
    for _ in range(2):
        assert client.post(
            "/api/agent/events", headers=one, json={"events": [event]}
        ).json == {"stored": 1}
    assert client.post(
        "/api/agent/events",
        headers=one,
        json={
            "events": [
                {**event, "event_id": "test_event_5678", "file": "/srv/other/no.txt"}
            ]
        },
    ).json == {"stored": 0}
    with app.app_context():
        assert db.q("SELECT COUNT(*) AS c FROM file_events", one=True)["c"] == 1
        assert sum(day["observed"] for day in services.week_activity()) == 1


def test_legacy_sqlite_schema_migrates_without_losing_devices_or_folder_ids(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("FC_ENV", raising=False)
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""CREATE TABLE devices (id INTEGER PRIMARY KEY AUTOINCREMENT,hostname TEXT UNIQUE NOT NULL,win_user TEXT,department TEXT,ip TEXT,mac TEXT,agent_version TEXT,ring TEXT NOT NULL DEFAULT 'pilot',api_key_hash TEXT NOT NULL,last_seen TEXT,created_at TEXT NOT NULL);
        CREATE TABLE folders (id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT UNIQUE NOT NULL,state TEXT NOT NULL DEFAULT 'Monitored');
        INSERT INTO devices (hostname,api_key_hash,created_at) VALUES ('LEGACY01','unchanged-hash','2026-01-01');
        INSERT INTO folders (id,path) VALUES (7,'\\\\LEGACY01\\E');""")
    application = create_app({"DATABASE_URL": f"sqlite:///{path}"})
    with application.app_context():
        db.init_schema()
        db.init_schema()
        device = db.q("SELECT * FROM devices", one=True)
        assert (
            device["api_key_hash"] == "unchanged-hash"
            and device["os_family"] == "unknown"
        )
        assert db.q("SELECT id FROM folders", one=True)["id"] == 7
        db.q(
            "INSERT INTO folders (path,target_os,target_host) VALUES (?,?,?)",
            ("/srv/shared", "linux", "LINUX01"),
        )
        db.q(
            "INSERT INTO folders (path,target_os,target_host) VALUES (?,?,?)",
            ("/srv/shared", "linux", "LINUX02"),
        )
        assert db.q("SELECT COUNT(*) AS c FROM folders", one=True)["c"] == 3


def test_linux_scan_observes_metadata_and_does_not_follow_symlinks(tmp_path):
    root = tmp_path / "selected"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("outside-scope")
    sample = root / "sample.txt"
    sample.write_text("original")
    (root / "external-link").symlink_to(outside, target_is_directory=True)
    with patch(
        "builtins.open", side_effect=AssertionError("File contents must not be opened")
    ):
        before, complete, _ = linux.scan_directory(root)
    assert complete and list(before) == [str(sample)]
    sample.write_text("modified-longer")
    (root / "created.txt").write_text("new")
    after, complete, _ = linux.scan_directory(root)
    changes = linux.compare_snapshots(before, after)
    assert ("Modified", str(sample)) in changes and (
        "Created",
        str(root / "created.txt"),
    ) in changes
    sample.unlink()
    final, _, _ = linux.scan_directory(root)
    assert ("Deleted", str(sample)) in linux.compare_snapshots(after, final)
    assert (outside / "private.txt").read_text() == "outside-scope"


def test_partial_scan_keeps_baseline_and_does_not_invent_deletions(
    tmp_path, monkeypatch
):
    root = tmp_path / "selected"
    root.mkdir()
    (root / "file.txt").write_text("example")
    agent = linux.Agent(
        "http://127.0.0.1:8080",
        "LINUX01",
        tmp_path / "state",
        allow_insecure_localhost=True,
    )
    monkeypatch.setattr(
        agent,
        "request",
        lambda endpoint, payload=None, **kwargs: (
            {"stored": len(payload["events"])} if endpoint == "events" else {}
        ),
    )
    assert agent.monitor([str(root)])[0] == "healthy"
    baseline = agent.state["snapshots"][str(root)].copy()
    monkeypatch.setattr(
        linux, "scan_directory", lambda *a, **k: ({}, False, "Temporary read failure")
    )
    assert agent.monitor([str(root)])[0] == "partial"
    assert (
        agent.state["snapshots"][str(root)] == baseline and not agent.state["pending"]
    )
    assert agent.state_file.stat().st_mode & 0o777 == 0o600


def test_linux_polling_limit_and_https_defaults(tmp_path):
    root = tmp_path / "selected"
    root.mkdir()
    for i in range(3):
        (root / f"{i}.txt").write_text("example")
    _, complete, message = linux.scan_directory(root, max_files=2)
    assert not complete and "limit" in message
    with pytest.raises(ValueError, match="trusted HTTPS"):
        linux.Agent("http://192.0.2.10", "LINUX01", tmp_path / "state")


def test_linux_agent_reports_unsupported_windows_command_without_execution(
    tmp_path, monkeypatch
):
    agent = linux.Agent(
        "http://127.0.0.1:8080",
        "LINUX01",
        tmp_path / "state",
        allow_insecure_localhost=True,
    )
    results = []
    monkeypatch.setattr(
        agent,
        "request",
        lambda endpoint, payload=None, **kwargs: (
            results.append((endpoint, payload)) or {"ok": True}
        ),
    )
    agent.handle_command({"id": 1, "command": "lock_usb"}, {"os_family": "linux"})
    assert results[0][0] == "command-result" and results[0][1]["success"] is False
    assert not agent.state["command_results"]
