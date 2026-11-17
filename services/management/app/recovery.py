"""Metadata from locally configured recovery agents. No content or remote restore commands."""

import hashlib
import re
from datetime import UTC, datetime

from flask import g, jsonify, request

from . import audit, db

KINDS = {
    "version_captured", "restored", "restore_failed", "restore_conflict",
    "loop_suppressed", "delete_observed", "scan_failed",
}


def validate_event(value):
    if not isinstance(value, dict):
        raise ValueError("Each recovery event must be an object.")
    event_id = value.get("eventId", "")
    if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", event_id):
        raise ValueError("Invalid recovery event ID.")
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("Unknown recovery event kind.")
    path = value.get("relativePath", "")
    if not isinstance(path, str) or len(path) > 400 or "\x00" in path or ":" in path:
        raise ValueError("Invalid relative recovery path.")
    path = path.replace("\\", "/")
    if (not path and kind != "scan_failed") or (path and any(p in ("", ".", "..") for p in path.split("/"))):
        raise ValueError("Recovery paths must stay below the configured folder.")
    digest = value.get("sha256")
    version = value.get("versionId")
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise ValueError("Invalid SHA-256 digest.")
    if version is not None and (not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", version)):
        raise ValueError("Invalid version ID.")
    size = value.get("bytes")
    if size is not None and (type(size) is not int or not 0 <= size <= 1024**4):
        raise ValueError("Invalid version size.")
    if kind in {"version_captured", "restored"} and (not digest or not version or size is None):
        raise ValueError("Verified capture and restore events require a version, hash, and size.")
    try:
        timestamp = datetime.fromisoformat(str(value.get("ts", "")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError
        timestamp = timestamp.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (TypeError, ValueError):
        raise ValueError("Use a timezone-aware recovery timestamp.") from None
    message = value.get("message", "")
    if not isinstance(message, str) or len(message) > 1000:
        raise ValueError("Recovery messages must be at most 1000 characters.")
    return event_id, timestamp, kind, path, version, digest, size, message


def ingest(device, payload):
    items = payload.get("events")
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        return jsonify(error="Send between 1 and 100 recovery events."), 400
    try:
        validated = [validate_event(item) for item in items]
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    for event_id, timestamp, kind, path, version, digest, size, message in validated:
        key = hashlib.sha256(f"recovery:{device['id']}:{event_id}".encode()).hexdigest()
        try:
            with db.transaction():
                if db.q("SELECT id FROM recovery_events WHERE event_key=?", (key,), one=True):
                    continue
                db.q(
                    "INSERT INTO recovery_events (event_key,ts,device_id,kind,relative_path,version_id,sha256,bytes,message) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (key, timestamp, device["id"], kind, path, version, digest, size, message),
                )
                if kind != "version_captured":
                    audit.log(device["hostname"], "recovery." + kind, path or "scan", kind)
        except db.IntegrityError:
            if not db.q("SELECT id FROM recovery_events WHERE event_key=?", (key,), one=True):
                raise
    return jsonify(stored=len(validated))


def overview():
    search = request.args.get("q", "")[:100]
    where, params = "", ()
    if search:
        where, params = "WHERE (r.relative_path LIKE ? OR d.hostname LIKE ?)", (f"%{search}%", f"%{search}%")
    items = db.q(
        "SELECT r.id,r.ts,d.hostname AS device,r.kind,r.relative_path,r.version_id,r.sha256,r.bytes,r.message "
        "FROM recovery_events r JOIN devices d ON d.id=r.device_id " + where + " ORDER BY r.id DESC LIMIT 200", params,
    )
    counts = {r["kind"]: r["c"] for r in db.q("SELECT kind,COUNT(*) AS c FROM recovery_events GROUP BY kind")}
    return jsonify(
        items=[dict(row) for row in items],
        agents=[
            {**dict(row), "online": row["reported_at"] >= audit.since(90)}
            for row in db.q(
                "SELECT r.*,d.hostname AS device FROM recovery_agents r "
                "JOIN devices d ON d.id=r.device_id ORDER BY r.host_name"
            )
        ],
        stats={"versions": counts.get("version_captured", 0), "restored": counts.get("restored", 0),
               "issues": sum(counts.get(k, 0) for k in ("restore_failed", "restore_conflict", "loop_suppressed", "scan_failed"))},
        updated_at=audit.now(),
    )


def ingest_status(device, payload):
    """Self-reported local policy; this endpoint never issues a restore command."""
    mode = payload.get("mode")
    host = payload.get("hostName")
    root = payload.get("protectedRoot")
    status = payload.get("monitoringStatus")
    message = payload.get("message", "")
    if not isinstance(mode, str) or mode not in {"monitoring", "recovery"}:
        return jsonify(error="Invalid recovery mode."), 400
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", host):
        return jsonify(error="Invalid recovery host."), 400
    if (not isinstance(root, str) or not 1 < len(root) <= 400
            or any(ord(char) < 32 for char in root)):
        return jsonify(error="Invalid protected root."), 400
    if not isinstance(status, str) or status not in {"starting", "healthy", "degraded"}:
        return jsonify(error="Invalid recovery status."), 400
    if not isinstance(message, str) or len(message) > 1000:
        return jsonify(error="Invalid recovery status message."), 400
    with db.transaction():
        # Lock the existing parent row so concurrent reports cannot race the first insert.
        lock = " FOR UPDATE" if g.db_driver != "sqlite" else ""
        db.q("SELECT id FROM devices WHERE id=?" + lock, (device["id"],), one=True)
        previous = db.q("SELECT mode FROM recovery_agents WHERE device_id=?", (device["id"],), one=True)
        if previous:
            db.q(
                "UPDATE recovery_agents SET host_name=?,mode=?,protected_root=?,monitoring_status=?,message=?,reported_at=? WHERE device_id=?",
                (host, mode, root, status, message, audit.now(), device["id"]),
            )
        else:
            db.q(
                "INSERT INTO recovery_agents (device_id,host_name,mode,protected_root,monitoring_status,message,reported_at) VALUES (?,?,?,?,?,?,?)",
                (device["id"], host, mode, root, status, message, audit.now()),
            )
        if not previous or previous["mode"] != mode:
            audit.log(device["hostname"], "recovery.mode_reported", mode)
    return jsonify(ok=True)

