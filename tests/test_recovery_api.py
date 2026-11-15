from copy import deepcopy

import pytest
from app import db


def agent(client, host="RECOVERY-LAB01"):
    response = client.post("/api/agent/enroll", json={"hostname": host, "token": "test-enrollment-token"})
    return {"X-Device": host, "X-Api-Key": response.json["key"]}


def event():
    return {"eventId": "event_123456", "ts": "2026-11-15T02:00:00Z", "kind": "version_captured",
            "relativePath": "department/sample.txt", "versionId": "version_12345", "sha256": "a" * 64,
            "bytes": 20, "message": "Disposable lab data."}


def test_recovery_auth_validation_deduplication_and_device_identity(app, client):
    payload = {"events": [event()]}
    assert client.post("/api/agent/recovery-events", json=payload).status_code == 401
    one = agent(client)
    two = agent(client, "RECOVERY-LAB02")
    for headers in (one, one, two):
        assert client.post("/api/agent/recovery-events", headers=headers, json=payload).json == {"stored": 1}
    with app.app_context():
        assert db.q("SELECT COUNT(*) AS c FROM recovery_events", one=True)["c"] == 2
    assert client.get("/api/console/recovery").status_code == 401
    token = client.get("/api/console/session").json["csrf"]
    assert client.post("/api/console/login", json={"username": "admin", "password": "TestPassword123!"}, headers={"X-CSRF-Token": token}).status_code == 200
    response = client.get("/api/console/recovery").json
    assert response["stats"] == {"versions": 2, "restored": 0, "issues": 0}
    assert {row["device"] for row in response["items"]} == {"RECOVERY-LAB01", "RECOVERY-LAB02"}
    assert len(client.get("/api/console/recovery?q=LAB02").json["items"]) == 1


def test_recovery_health_states_map_to_console_and_restore_audit_deduplicates(app, client):
    headers = agent(client)
    for reported, expected in (("starting", "waiting"), ("degraded", "partial"), ("healthy", "healthy")):
        assert client.post("/api/agent/heartbeat", headers=headers, json={"monitoring_status": reported}).status_code == 200
        with app.app_context():
            assert db.q("SELECT monitoring_status FROM devices WHERE hostname=?", ("RECOVERY-LAB01",), one=True)["monitoring_status"] == expected
    restored = event()
    restored["kind"] = "restored"
    for _ in range(2):
        assert client.post("/api/agent/recovery-events", headers=headers, json={"events": [restored]}).status_code == 200
    with app.app_context():
        assert db.q("SELECT COUNT(*) AS c FROM audit WHERE action=?", ("recovery.restored",), one=True)["c"] == 1


@pytest.mark.parametrize("change", [
    {"relativePath": "../outside"}, {"relativePath": "C:/outside"}, {"relativePath": "/absolute"},
    {"kind": "unknown"}, {"kind": {}}, {"sha256": "invalid"}, {"bytes": True}, {"sha256": None},
    {"ts": "2026-11-15T02:00:00"}, {"relativePath": ""}, {"message": "x" * 1001},
])
def test_invalid_recovery_batch_is_rejected_before_writes(app, client, change):
    headers = agent(client)
    bad = deepcopy(event())
    bad.update(change)
    assert client.post("/api/agent/recovery-events", headers=headers, json={"events": [event(), bad]}).status_code == 400
    with app.app_context():
        assert db.q("SELECT COUNT(*) AS c FROM recovery_events", one=True)["c"] == 0
