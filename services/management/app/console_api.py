"""Same-origin JSON API for the standalone console frontend."""

import csv
import io
import secrets
from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, request, session
from werkzeug.security import check_password_hash

from . import audit, auth, db, services
from .shares import valid_linux_path, valid_share

console = Blueprint("console", __name__, url_prefix="/api/console")


def authenticated(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return jsonify(error="Sign in to continue."), 401
        return view(*args, **kwargs)

    return wrapped


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


@console.errorhandler(ValueError)
def validation_error(exc):
    return jsonify(error=str(exc)), 400


@console.get("/session")
def session_info():
    session.setdefault("csrf", secrets.token_hex(24))
    return jsonify(
        user=session.get("admin"),
        csrf=session["csrf"],
        environment=current_app.config["CONSOLE_ENVIRONMENT"],
        remote_commands=current_app.config["ENABLE_REMOTE_COMMANDS"],
        directory_writes=current_app.config["ENABLE_DIRECTORY_WRITES"],
        upload_approval_enabled=current_app.config["UPLOAD_APPROVAL_ENABLED"],
    )


@console.post("/login")
def login():
    data = body()
    username = str(data.get("username", "")).strip()[:64]
    password = str(data.get("password", ""))
    if auth.locked(username):
        return jsonify(error="Too many attempts. Try again in 15 minutes."), 429
    admin = db.q(
        "SELECT password_hash FROM admins WHERE username=?", (username,), one=True
    )
    if not admin or not check_password_hash(admin["password_hash"], password):
        audit.log(None, "login", username or "-", "failed")
        return jsonify(error="The username or password is incorrect."), 401
    session.clear()
    session.permanent = True
    session["admin"], session["csrf"] = username, secrets.token_hex(24)
    audit.log(username, "login", "-", "success")
    return jsonify(user=username, csrf=session["csrf"])


@console.post("/logout")
@authenticated
def logout():
    audit.log(session["admin"], "logout")
    session.clear()
    return jsonify(ok=True)


def device_rows():
    # Never return api_key_hash to the browser or CSV export.
    rows = db.q(
        "SELECT id,hostname,win_user,department,ip,mac,agent_version,ring,last_seen,created_at, "
        "os_family,os_version,architecture,cpu_percent,memory_total_mb,memory_used_mb,disk_total_mb,disk_used_mb,uptime_seconds,telemetry_at,monitoring_status,monitoring_message FROM devices ORDER BY hostname"
    )
    cutoff = audit.since(90)
    return [
        {
            **dict(r),
            "online": bool(r["last_seen"] and r["last_seen"] >= cutoff),
            "simulated": str(r["agent_version"] or "").startswith("SIM-"),
        }
        for r in rows
    ]


def folder_rows():
    rows = []
    for row in db.q("SELECT * FROM folders ORDER BY path"):
        probe = db.q(
            "SELECT ts,result FROM probes WHERE folder=? ORDER BY id DESC LIMIT 1",
            (row["path"],),
            one=True,
        )
        rows.append({**dict(row), "probe": dict(probe) if probe else None})
    return rows


@console.get("/overview")
@authenticated
def overview():
    stats = services.stats()
    stats.update(
        events=db.q("SELECT COUNT(*) AS c FROM file_events", one=True)["c"],
        shares=db.q("SELECT COUNT(*) AS c FROM folders", one=True)["c"],
    )
    return jsonify(
        stats=stats,
        week=services.week_activity(),
        devices=device_rows()[:6],
        activity=[
            dict(r) for r in db.q("SELECT * FROM file_events ORDER BY id DESC LIMIT 6")
        ],
        rings=services.ring_progress(),
        requests=[dict(r) for r in services.list_requests("all", 5)],
        folders=folder_rows(),
        updated_at=audit.now(),
    )


@console.get("/devices")
@authenticated
def devices():
    return jsonify(
        items=device_rows(),
        commands=[dict(r) for r in services.list_device_commands(50)],
    )


@console.get("/recovery")
@authenticated
def recovery_overview():
    from .recovery import overview

    return overview()


@console.get("/uploads")
@authenticated
def upload_list():
    from .uploads import listing
    return listing()


@console.post("/uploads")
@authenticated
def upload_submit():
    from .uploads import submit
    return submit()


@console.post("/uploads/<int:identifier>/<decision>")
@authenticated
def upload_decide(identifier, decision):
    from .uploads import decide
    return decide(identifier, decision)


@console.get("/uploads/<int:identifier>/download")
@authenticated
def upload_download(identifier):
    from .uploads import download
    return download(identifier)


@console.post("/devices/<int:device_id>/ring")
@authenticated
def change_ring(device_id):
    ring = body().get("ring")
    if ring not in services.RINGS:
        raise ValueError("Choose a valid deployment ring.")
    if not db.q("SELECT id FROM devices WHERE id=?", (device_id,), one=True):
        return jsonify(error="Device not found."), 404
    db.q("UPDATE devices SET ring=? WHERE id=?", (ring, device_id))
    audit.log(session["admin"], "device.ring", f"#{device_id} -> {ring}")
    return jsonify(ok=True)


@console.post("/devices/<int:device_id>/commands")
@authenticated
def command(device_id):
    services.queue_device_command(
        device_id, body().get("command", ""), session["admin"]
    )
    return jsonify(ok=True), 201


def event_query():
    query = request.args.get("q", "").strip()[:200]
    result = request.args.get("result", "")
    where, params = "WHERE 1=1", []
    if query:
        where += " AND (device LIKE ? OR win_user LIKE ? OR file LIKE ?)"
        params.extend([f"%{query}%"] * 3)
    if result in ("blocked", "allowed", "observed"):
        where += " AND result=?"
        params.append(result)
    return where, tuple(params)


@console.get("/events")
@authenticated
def events():
    where, params = event_query()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        raise ValueError("Invalid page number.") from None
    total = db.q(f"SELECT COUNT(*) AS c FROM file_events {where}", params, one=True)[
        "c"
    ]
    rows = db.q(
        f"SELECT * FROM file_events {where} ORDER BY id DESC LIMIT 25 OFFSET ?",
        params + ((page - 1) * 25,),
    )
    return jsonify(items=[dict(r) for r in rows], total=total, page=page, page_size=25)


@console.get("/events/export")
@authenticated
def export_events():
    where, params = event_query()
    rows = db.q(
        f"SELECT ts,device,win_user,action,file,result,process FROM file_events {where} ORDER BY id DESC LIMIT 10000",
        params,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    columns = ("ts", "device", "win_user", "action", "file", "result", "process")
    writer.writerow(columns)
    for row in rows:
        values = []
        for col in columns:
            value = str(row[col] or "")
            # Spreadsheet applications must treat untrusted metadata as text, not formulas.
            values.append(
                "'" + value
                if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                else value
            )
        writer.writerow(values)
    audit.log(session["admin"], "events.export", f"{len(rows)} rows")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="file-activity.csv"'},
    )


@console.get("/shares")
@authenticated
def shares():
    return jsonify(items=folder_rows())


@console.post("/shares")
@authenticated
def add_share():
    data = body()
    family = data.get("target_os", "windows")
    path = (
        str(data.get("path", "")).strip().rstrip("\\" if family == "windows" else "/")
    )
    host = str(data.get("target_host", "")).strip()
    if family == "linux":
        if not valid_linux_path(path) or not services.HOST_RE.fullmatch(host):
            raise ValueError(
                "Linux monitoring needs an absolute directory below / and a valid enrolled hostname."
            )
    elif family != "windows" or not valid_share(path):
        raise ValueError(r"Enter an exact UNC path, for example \\EXAMPLE-FILE01\E.")
    existing = db.q(
        "SELECT id FROM folders WHERE target_os=? AND LOWER(target_host)=LOWER(?) AND "
        + ("path=?" if family == "linux" else "LOWER(path)=LOWER(?)"),
        (family, host if family == "linux" else "", path),
        one=True,
    )
    if existing:
        return jsonify(error="This share is already registered."), 409
    try:
        db.q(
            "INSERT INTO folders (path,target_os,target_host) VALUES (?,?,?)",
            (path, family, host if family == "linux" else ""),
        )
    except db.IntegrityError:
        return jsonify(error="This share is already registered."), 409
    audit.log(session["admin"], "folder.add", path)
    return jsonify(ok=True), 201


@console.delete("/shares/<int:folder_id>")
@authenticated
def remove_share(folder_id):
    row = db.q("SELECT path FROM folders WHERE id=?", (folder_id,), one=True)
    if not row:
        return jsonify(error="Share not found."), 404
    db.q("DELETE FROM folders WHERE id=?", (folder_id,))
    audit.log(session["admin"], "folder.remove", row["path"])
    return jsonify(ok=True)


@console.get("/requests")
@authenticated
def requests():
    return jsonify(
        items=[dict(r) for r in services.list_requests()], counts=services.tab_counts()
    )


@console.post("/requests")
@authenticated
def add_request():
    data = body()
    rid = services.create_request(
        *(str(data.get(key, "")) for key in ("requester", "action", "path", "reason"))
    )
    return jsonify(id=rid), 201


@console.post("/requests/<int:request_id>/<action>")
@authenticated
def decide_request(request_id, action):
    if action == "revoke":
        services.revoke(request_id, session["admin"])
    elif action in ("approve", "reject"):
        services.decide(request_id, session["admin"], action == "approve")
    else:
        return jsonify(error="Unknown decision."), 404
    return jsonify(ok=True)


@console.get("/audit")
@authenticated
def audit_trail():
    ok, broken = audit.verify()
    return jsonify(
        items=[
            dict(r)
            for r in db.q(
                "SELECT id,ts,actor,action,target,outcome FROM audit ORDER BY id DESC LIMIT 200"
            )
        ],
        integrity=ok,
        broken_at=broken,
    )


@console.get("/system")
@authenticated
def system():
    db.get_db()
    from flask import g

    driver = g.db_driver
    if driver == "mysql":
        version = db.q("SELECT VERSION() AS version", one=True)["version"]
    elif driver == "postgres":
        version = db.q("SELECT version() AS version", one=True)["version"]
    else:
        version = db.q("SELECT sqlite_version() AS version", one=True)["version"]
    heartbeat = db.q(
        "SELECT value FROM settings WHERE key_name=?", ("_worker_heartbeat",), one=True
    )
    worker_seen = heartbeat["value"] if heartbeat else None
    table_names = (
        "devices",
        "file_events",
        "folders",
        "probes",
        "requests",
        "device_commands",
        "audit",
        "admins",
        "settings",
        "recovery_events",
        "recovery_agents",
        "upload_requests",
    )
    tables = [
        {"name": name, "rows": db.q(f"SELECT COUNT(*) AS c FROM {name}", one=True)["c"]}
        for name in table_names
    ]
    agent_connected = current_app.config["SERVICE_ROLE"] == "all"
    url = current_app.config.get("AGENT_HEALTH_URL")
    if url:
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                agent_connected = json.load(response).get("ok") is True
        except (OSError, ValueError):
            agent_connected = False
    return jsonify(
        agent={"connected": agent_connected},
        database={
            "engine": driver,
            "version": version,
            "connected": True,
            "tables": tables,
        },
        worker={
            "online": bool(worker_seen and worker_seen >= audit.since(90)),
            "last_seen": worker_seen,
        },
        configuration={
            "monitoring_only": not current_app.config["ENABLE_REMOTE_COMMANDS"]
            and not current_app.config["ENABLE_DIRECTORY_WRITES"],
            "remote_commands": current_app.config["ENABLE_REMOTE_COMMANDS"],
            "directory_writes": current_app.config["ENABLE_DIRECTORY_WRITES"],
            "enrollment": current_app.config["ENROLLMENT_ENABLED"],
            "environment": current_app.config["CONSOLE_ENVIRONMENT"],
            "console_url": current_app.config["PUBLIC_CONSOLE_URL"],
        },
        updated_at=audit.now(),
    )


@console.get("/settings")
@authenticated
def settings():
    return jsonify(values={k: services.setting(k) for k in services.DEFAULTS})


@console.post("/settings")
@authenticated
def save_settings():
    data = body()
    try:
        minutes = int(data.get("approval_minutes", 30))
    except (TypeError, ValueError):
        raise ValueError("Approval duration must be a number.") from None
    if not 5 <= minutes <= 120:
        raise ValueError("Approval duration must be between 5 and 120 minutes.")
    with db.transaction():
        services.save_setting("approval_minutes", minutes)
        for key in services.DEFAULTS:
            if key != "approval_minutes" and key in data:
                if data[key] not in (True, False, "0", "1"):
                    raise ValueError(f"Invalid setting: {key}")
                services.save_setting(key, "1" if data[key] in (True, "1") else "0")
    audit.log(session["admin"], "settings.save", f"approval {minutes} min")
    return jsonify(ok=True)


@console.get("/system/schema")
@authenticated
def schema_download():
    from pathlib import Path

    source = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    sql = (
        "-- Nile of Hope File Control: MySQL schema\nUSE nilehope_fileguard;\n\n"
        + source.replace("{PK}", "INT AUTO_INCREMENT PRIMARY KEY").replace(
            "{PATH_TYPE}", "VARCHAR(400) COLLATE utf8mb4_bin"
        )
    )
    return Response(
        sql,
        mimetype="application/sql",
        headers={"Content-Disposition": 'attachment; filename="nile-hope-schema.sql"'},
    )
