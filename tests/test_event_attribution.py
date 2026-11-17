from app import audit, db


def enroll(client, hostname):
    response = client.post(
        "/api/agent/enroll",
        json={
            "token": "test-enrollment-token",
            "hostname": hostname,
            "ring": "pilot",
        },
    )
    assert response.status_code == 200
    return {"X-Device": hostname, "X-Api-Key": response.json["key"]}


def add_share(app):
    with app.app_context():
        db.q("INSERT INTO folders (path) VALUES (?)", (r"\\FS01\Finance",))


def console_headers(client):
    csrf = client.get("/api/console/session").json["csrf"]
    response = client.post(
        "/api/console/login",
        json={"username": "admin", "password": "TestPassword123!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json["csrf"]}


def windows_event(record_id, timestamp, ip):
    return {
        "event_id": f"win-{record_id}",
        "source_event_id": 4663,
        "record_id": str(record_id),
        "logon_id": "0x000000000000a123",
        "handle_id": "0x54",
        "access_mask": "0x10000",
        "share_name": "Finance",
        "ts": timestamp,
        "win_user": "NILEHOPE\\staff1",
        "ip": ip,
        "action": "Delete right used",
        "result": "allowed",
        "file": r"\\FS01\Finance\annual-report.xlsx",
        "process": "SMB",
    }


def test_event_time_ip_history_is_persisted_and_event_retry_is_idempotent(
    app, client
):
    server = enroll(client, "FS01")
    workstation = enroll(client, "WS01")
    add_share(app)
    assert client.post(
        "/api/agent/heartbeat",
        headers=workstation,
        json={"os_family": "windows", "ip": "192.0.2.164", "ips": ["192.0.2.164"]},
    ).status_code == 200

    with app.app_context():
        device_id = db.q(
            "SELECT id FROM devices WHERE hostname=?", ("WS01",), one=True
        )["id"]
        db.q("DELETE FROM device_ip_history WHERE device_id=?", (device_id,))
        db.q(
            "INSERT INTO device_ip_history (device_id,ip,seen_from,seen_to) VALUES (?,?,?,?)",
            (device_id, "192.0.2.164", "2026-11-17T10:00:00Z", "2026-11-17T11:00:00Z"),
        )
        db.q(
            "INSERT INTO device_ip_history (device_id,ip,seen_from,seen_to) VALUES (?,?,?,NULL)",
            (device_id, "192.0.2.165", "2026-11-17T11:00:00Z"),
        )

    matched = windows_event("7001", "2026-11-17T10:30:00Z", "::ffff:192.0.2.164")
    for _ in range(2):
        response = client.post(
            "/api/agent/events", headers=server, json={"events": [matched]}
        )
        assert response.status_code == 200
        assert response.json == {"stored": 1}

    unmatched = windows_event("7002", "2026-11-17T11:30:00Z", "192.0.2.164")
    assert client.post(
        "/api/agent/events", headers=server, json={"events": [unmatched]}
    ).json == {"stored": 1}

    with app.app_context():
        rows = db.q("SELECT * FROM file_events ORDER BY record_id")
        assert len(rows) == 2
        assert rows[0]["device"] == "FS01"
        assert rows[0]["client_device"] == "WS01"
        assert rows[0]["client_match"] == "ip_history"
        assert rows[0]["ip"] == "192.0.2.164"
        assert rows[0]["source_event_id"] == 4663
        assert rows[0]["record_id"] == "7001"
        assert rows[0]["logon_id"] == "0x000000000000a123"
        assert rows[0]["handle_id"] == "0x54"
        assert rows[0]["access_mask"] == "0x10000"
        assert rows[0]["share_name"] == "Finance"
        assert rows[1]["client_device"] is None
        assert rows[1]["client_match"] == "unmatched"

    console_headers(client)
    activity = client.get("/api/console/events?q=WS01").json
    assert activity["total"] == 1
    assert activity["items"][0]["source_event_id"] == 4663
    assert activity["items"][0]["client_device"] == "WS01"


def test_shared_ip_does_not_guess_a_client_device(app, client):
    server = enroll(client, "FS01")
    enroll(client, "WS01")
    enroll(client, "WS02")
    add_share(app)
    timestamp = audit.now()
    with app.app_context():
        for hostname in ("WS01", "WS02"):
            device_id = db.q(
                "SELECT id FROM devices WHERE hostname=?", (hostname,), one=True
            )["id"]
            db.q(
                "INSERT INTO device_ip_history (device_id,ip,seen_from,seen_to) VALUES (?,?,?,NULL)",
                (device_id, "192.0.2.164", "2026-01-01T00:00:00Z"),
            )

    response = client.post(
        "/api/agent/events",
        headers=server,
        json={"events": [windows_event("7003", timestamp, "192.0.2.164")]},
    )
    assert response.status_code == 200
    with app.app_context():
        row = db.q("SELECT client_device,client_match FROM file_events", one=True)
        assert row["client_device"] is None
        assert row["client_match"] == "ambiguous"


def test_heartbeat_closes_old_ip_interval_when_addresses_disappear(app, client):
    workstation = enroll(client, "WS01")
    assert client.post(
        "/api/agent/heartbeat",
        headers=workstation,
        json={"os_family": "windows", "ip": "192.0.2.164", "ips": ["192.0.2.164"]},
    ).status_code == 200
    assert client.post(
        "/api/agent/heartbeat",
        headers=workstation,
        json={"os_family": "windows", "ip": None, "ips": []},
    ).status_code == 200
    with app.app_context():
        row = db.q("SELECT seen_to FROM device_ip_history", one=True)
        assert row["seen_to"] is not None


def test_windows_event_requires_valid_address_and_time(app, client):
    server = enroll(client, "FS01")
    add_share(app)
    for invalid in (
        {"ip": "not-an-ip", "ts": "2026-11-17T10:00:00Z"},
        {"ip": "192.0.2.164", "ts": "2026-11-17 10:00:00"},
    ):
        event = windows_event("7004", invalid["ts"], invalid["ip"])
        assert client.post(
            "/api/agent/events", headers=server, json={"events": [event]}
        ).status_code == 400

