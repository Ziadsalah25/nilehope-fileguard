import io

import pytest
from app import db


@pytest.fixture
def uploads(app, client, tmp_path):
    app.config.update(UPLOAD_APPROVAL_ENABLED=True, UPLOAD_STORAGE_ROOT=str(tmp_path / "uploads"),
                      MAX_CONTENT_LENGTH=11 * 1024 * 1024)
    csrf = client.get("/api/console/session").json["csrf"]
    result = client.post("/api/console/login", json={"username": "admin", "password": "TestPassword123!"},
                         headers={"X-CSRF-Token": csrf})
    return {"X-CSRF-Token": result.json["csrf"]}


def submit(client, headers, content=b"disposable content", filename="sample.txt"):
    return client.post("/api/console/uploads", headers=headers,
                       data={"file": (io.BytesIO(content), filename), "reason": "Disposable pilot"})


def test_uploads_require_enabled_module_auth_and_csrf(client, app, uploads):
    app.config["UPLOAD_APPROVAL_ENABLED"] = False
    assert client.get("/api/console/uploads").status_code == 404
    app.config["UPLOAD_APPROVAL_ENABLED"] = True
    assert submit(client, {}).status_code == 400
    client.post("/api/console/logout", headers=uploads, json={})
    assert client.get("/api/console/uploads").status_code == 401
    assert client.get("/api/console/uploads/1/download").status_code == 401


def test_pending_approval_download_and_terminal_decision(client, app, uploads):
    response = submit(client, uploads, filename="../../sample.txt")
    assert response.status_code == 201
    identifier = response.json["id"]
    url = f"/api/console/uploads/{identifier}"
    assert client.get(url + "/download").status_code == 403
    listed = client.get("/api/console/uploads").json["items"][0]
    assert listed["file_name"] == "sample.txt" and "storage_key" not in listed
    assert client.post(url + "/approve", headers=uploads, json={}).json["status"] == "approved"
    response = client.get(url + "/download")
    assert response.status_code == 200 and response.data == b"disposable content"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "no-store" in response.headers["Cache-Control"]
    response.close()
    assert client.post(url + "/reject", headers=uploads, json={}).status_code == 409
    with app.app_context():
        assert db.q("SELECT COUNT(*) AS c FROM audit WHERE action LIKE 'upload.%'", one=True)["c"] == 3


def test_rejected_or_corrupt_files_cannot_be_downloaded(client, app, uploads):
    one = submit(client, uploads).json["id"]
    assert client.post(f"/api/console/uploads/{one}/reject", headers=uploads, json={}).status_code == 200
    assert client.get(f"/api/console/uploads/{one}/download").status_code == 403
    two = submit(client, uploads).json["id"]
    client.post(f"/api/console/uploads/{two}/approve", headers=uploads, json={})
    with app.app_context():
        key = db.q("SELECT storage_key FROM upload_requests WHERE id=?", (two,), one=True)["storage_key"]
    from pathlib import Path
    (Path(app.config["UPLOAD_STORAGE_ROOT"]) / (key + ".blob")).write_bytes(b"tampered")
    assert client.get(f"/api/console/uploads/{two}/download").status_code == 409


@pytest.mark.parametrize("content,status", [(b"", 400), (b"x" * (10 * 1024 * 1024 + 1), 413)], ids=["empty", "oversize"])
def test_invalid_upload_does_not_leave_files_or_rows(client, app, uploads, content, status):
    from pathlib import Path
    assert submit(client, uploads, content=content).status_code == status
    with app.app_context():
        assert db.q("SELECT COUNT(*) AS c FROM upload_requests", one=True)["c"] == 0
    assert not list(Path(app.config["UPLOAD_STORAGE_ROOT"]).glob("*.blob"))
