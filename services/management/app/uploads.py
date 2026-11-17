"""An optional administrator upload queue, independent of AD access approvals."""

import hashlib
import re
import uuid
from pathlib import Path

from flask import abort, current_app, jsonify, request, send_file, session
from werkzeug.utils import secure_filename

from . import audit, db

MAX_BYTES = 10 * 1024 * 1024


def enabled():
    return current_app.config["UPLOAD_APPROVAL_ENABLED"]


def require_enabled():
    if not enabled():
        abort(404, description="Upload approval is disabled.")


def storage():
    path = Path(current_app.config["UPLOAD_STORAGE_ROOT"])
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("Use a private absolute upload-storage directory.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def listing():
    require_enabled()
    rows = db.q(
        "SELECT id,file_name,sha256,bytes,reason,status,submitted_by,created_at,decided_by,decided_at "
        "FROM upload_requests ORDER BY id DESC LIMIT 200"
    )
    return jsonify(items=[dict(row) for row in rows], max_bytes=MAX_BYTES)


def submit():
    require_enabled()
    upload = request.files.get("file")
    reason = request.form.get("reason", "").strip()
    if not upload or not upload.filename:
        return jsonify(error="Choose a file."), 400
    name = secure_filename(upload.filename)[:255]
    if not name or not 1 <= len(reason) <= 1000 or "\x00" in reason:
        return jsonify(error="Use a valid filename and a reason of 1–1000 characters."), 400
    key = uuid.uuid4().hex
    path = storage() / (key + ".blob")
    size, digest = 0, hashlib.sha256()
    try:
        with path.open("xb") as output:
            while chunk := upload.stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    abort(413, description="Files must be at most 10 MiB.")
                digest.update(chunk)
                output.write(chunk)
        if not size:
            path.unlink()
            return jsonify(error="Empty files cannot be submitted."), 400
        with db.transaction():
            row = db.q(
                "INSERT INTO upload_requests (storage_key,file_name,sha256,bytes,reason,status,submitted_by,created_at) "
                "VALUES (?,?,?,?,?,'pending',?,?) RETURNING id",
                (key, name, digest.hexdigest(), size, reason, session["admin"], audit.now()), one=True,
            )
            audit.log(session["admin"], "upload.submitted", str(row["id"]))
        return jsonify(id=row["id"], status="pending"), 201
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def decide(identifier, decision):
    require_enabled()
    if decision not in {"approve", "reject"}:
        return jsonify(error="Choose approve or reject."), 400
    state = "approved" if decision == "approve" else "rejected"
    with db.transaction():
        changed = db.q(
            "UPDATE upload_requests SET status=?,decided_by=?,decided_at=? WHERE id=? AND status='pending'",
            (state, session["admin"], audit.now(), identifier),
        )
        if changed != 1:
            row = db.q("SELECT id FROM upload_requests WHERE id=?", (identifier,), one=True)
            return jsonify(error="Already decided." if row else "Upload not found."), 409 if row else 404
        audit.log(session["admin"], "upload." + state, str(identifier))
    return jsonify(ok=True, status=state)


def download(identifier):
    require_enabled()
    row = db.q("SELECT * FROM upload_requests WHERE id=?", (identifier,), one=True)
    if not row:
        return jsonify(error="Upload not found."), 404
    if row["status"] != "approved":
        return jsonify(error="Only approved files can be downloaded."), 403
    key = row["storage_key"]
    if not re.fullmatch(r"[a-f0-9]{32}", key):
        return jsonify(error="Stored file reference is invalid."), 409
    path = storage() / (key + ".blob")
    if path.is_symlink():
        return jsonify(error="Stored file integrity check failed."), 409
    try:
        source = path.open("rb")
    except FileNotFoundError:
        return jsonify(error="The approved file is missing from storage."), 409
    try:
        digest, size = hashlib.sha256(), 0
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        if size != row["bytes"] or digest.hexdigest() != row["sha256"]:
            source.close()
            return jsonify(error="Stored file integrity check failed."), 409
        source.seek(0)
        audit.log(session["admin"], "upload.downloaded", str(identifier))
        response = send_file(source, as_attachment=True, download_name=row["file_name"],
                             mimetype="application/octet-stream", max_age=0)
        response.headers["Cache-Control"] = "no-store"
        response.call_on_close(source.close)
        return response
    except BaseException:
        source.close()
        raise
