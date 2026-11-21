import hashlib
import hmac
import ipaddress
import re
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, request

from . import audit, db, services
from .db import IntegrityError, q
from .shares import configured_linux_paths, configured_paths, event_in_scope
from .telemetry import validate as validate_telemetry

api = Blueprint("api", __name__, url_prefix="/api/agent")


def agent_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        dev = services.device_by_key(
            request.headers.get("X-Device", ""), request.headers.get("X-Api-Key", "")
        )
        if not dev:
            audit.log(
                None,
                "agent.auth",
                request.headers.get("X-Device", "-")[:64],
                "denied",
                dedupe=60,
            )
            return jsonify(error="unauthorized"), 401
        return view(dev, *args, **kwargs)

    return wrapped


def _s(value, n):
    return None if value is None else str(value)[:n]


def _normalized_ip(value, *, strict=False):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        if strict:
            raise ValueError("IP addresses must be strings")
        return None
    raw = value.strip().split("%", 1)[0]
    if not raw or raw == "-":
        return None
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError:
        if strict:
            raise ValueError("Invalid IP address") from None
        return None
    if getattr(parsed, "ipv4_mapped", None):
        parsed = parsed.ipv4_mapped
    if parsed.is_unspecified or parsed.is_loopback:
        return None
    return parsed.compressed


def _event_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _record_device_ips(device_id, ips, seen_at):
    with db.transaction():
        open_rows = db.q(
            "SELECT id,ip FROM device_ip_history WHERE device_id=? AND seen_to IS NULL",
            (device_id,),
        )
        current = set(ips)
        for row in open_rows:
            if row["ip"] not in current:
                db.q(
                    "UPDATE device_ip_history SET seen_to=? WHERE id=? AND seen_to IS NULL",
                    (seen_at, row["id"]),
                )
        open_ips = {row["ip"] for row in open_rows if row["ip"] in current}
        for ip in current - open_ips:
            db.q(
                "INSERT INTO device_ip_history(device_id,ip,seen_from,seen_to) VALUES(?,?,?,NULL)",
                (device_id, ip, seen_at),
            )


def _match_client_device(ip, event_time):
    normalized = _normalized_ip(ip)
    stamp = _event_time(event_time)
    if not normalized or not stamp:
        return None, "unmatched"
    rows = db.q(
        "SELECT DISTINCT d.id,d.hostname FROM device_ip_history h "
        "JOIN devices d ON d.id=h.device_id "
        "WHERE h.ip=? AND h.seen_from<=? AND (h.seen_to IS NULL OR h.seen_to>?)",
        (normalized, stamp, stamp),
    )
    if len(rows) == 1:
        return rows[0]["hostname"], "ip_history"
    if len(rows) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, "Expected a JSON object")
    return body


@api.get("/config")
@agent_required
def agent_config(dev):
    return jsonify(
        folders=configured_linux_paths(dev["hostname"])
        if dev["os_family"] == "linux"
        else configured_paths(dev["hostname"]),
        remote_commands_enabled=current_app.config["ENABLE_REMOTE_COMMANDS"],
    )


@api.post("/enroll")
def enroll():
    if not current_app.config["ENROLLMENT_ENABLED"]:
        return jsonify(error="Enrollment is closed"), 403
    body = _body()
    expected = current_app.config["ENROLL_TOKEN"]
    if not expected or not hmac.compare_digest(
        str(body.get("token", "")).encode(), expected.encode()
    ):
        audit.log(
            None,
            "agent.enroll",
            _s(body.get("hostname"), 64) or "-",
            "denied",
            dedupe=60,
        )
        return jsonify(error="bad token"), 403
    try:
        key = services.enroll_device(
            str(body.get("hostname", "")), str(body.get("ring", "pilot"))
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 409
    return jsonify(key=key)


@api.post("/heartbeat")
@agent_required
def heartbeat(dev):
    b = _body()
    try:
        telemetry = validate_telemetry(b)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    reported_ips = b.get("ips", [])
    if reported_ips is None:
        reported_ips = []
    if not isinstance(reported_ips, list) or len(reported_ips) > 16:
        return jsonify(error="ips must be a list of at most 16 addresses"), 400
    try:
        primary_ip = _normalized_ip(b.get("ip"), strict=True)
        ips = sorted(
            {
                normalized
                for value in [b.get("ip"), *reported_ips]
                if (normalized := _normalized_ip(value, strict=True)) is not None
            }
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    seen_at = audit.now()
    q(
        "UPDATE devices SET win_user=?, department=COALESCE(?, department), ip=?, mac=?, agent_version=?, "
        "last_seen=? WHERE id=?",
        (
            _s(b.get("win_user"), 80),
            _s(b.get("department"), 80),
            primary_ip,
            _s(b.get("mac"), 20),
            _s(b.get("agent_version"), 20),
            seen_at,
            dev["id"],
        ),
    )
    if "ip" in b or "ips" in b:
        _record_device_ips(dev["id"], ips, seen_at)
    if telemetry:
        fields = ",".join(f"{field}=COALESCE(?,{field})" for field in telemetry)
        q(f"UPDATE devices SET {fields} WHERE id=?", (*telemetry.values(), dev["id"]))
    pending_cmd = services.get_pending_command(dev["id"])
    return jsonify(ok=True, command=pending_cmd)


@api.post("/command-result")
@agent_required
def command_result(dev):
    b = _body()
    cmd_id = b.get("command_id")
    output = str(b.get("output", ""))
    if type(cmd_id) is not int or cmd_id < 1:
        return jsonify(error="command_id must be a positive integer"), 400
    if type(b.get("success", True)) is not bool:
        return jsonify(error="success must be a boolean"), 400
    if not services.finish_device_command(
        dev["id"], cmd_id, output, b.get("success", True)
    ):
        return jsonify(error="No sent command belongs to this device with that ID"), 409
    return jsonify(ok=True)


@api.post("/events")
@agent_required
def events(dev):
    items = _body().get("events", [])
    if (
        not isinstance(items, list)
        or len(items) > 200
        or any(not isinstance(e, dict) for e in items)
    ):
        return jsonify(error="events must be an array of at most 200 objects"), 400
    prepared = []
    allowed_windows_ids = {4656, 4660, 4663, 5145}
    for e in items:
        if e.get("result") not in ("blocked", "allowed", "observed"):
            continue
        path = str(e.get("file", ""))
        if not event_in_scope(path, dev):
            continue
        uid = str(e.get("event_id", ""))
        if uid and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", uid):
            return jsonify(error="Invalid event_id"), 400

        source_event_id = e.get("source_event_id")
        if source_event_id is not None and (
            type(source_event_id) is not int or source_event_id not in allowed_windows_ids
        ):
            return jsonify(error="Invalid Windows Security event ID"), 400
        record_id = e.get("record_id")
        if record_id is not None and (
            not isinstance(record_id, str) or not re.fullmatch(r"[0-9]{1,32}", record_id)
        ):
            return jsonify(error="Invalid Windows event record ID"), 400
        if source_event_id is not None and record_id is None:
            return jsonify(error="Windows audit events require a record_id"), 400

        def optional_hex(field, max_digits=16):
            value = e.get(field)
            if value is None:
                return None
            if not isinstance(value, str) or not re.fullmatch(
                rf"(?:0[xX])?[0-9a-fA-F]{{1,{max_digits}}}", value
            ):
                raise ValueError(f"Invalid {field}")
            return value.lower()

        try:
            logon_id = optional_hex("logon_id")
            handle_id = optional_hex("handle_id")
            access_mask = optional_hex("access_mask", 8)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        share_name = e.get("share_name")
        if share_name is not None and (
            not isinstance(share_name, str)
            or not 1 <= len(share_name) <= 128
            or any(ord(char) < 32 for char in share_name)
        ):
            return jsonify(error="Invalid share_name"), 400

        raw_ts = e.get("ts")
        ts = _event_time(raw_ts)
        if source_event_id is not None and not ts:
            return jsonify(error="Windows audit events require a timezone-aware timestamp"), 400
        ts = ts or audit.now()
        try:
            source_ip = _normalized_ip(e.get("ip"), strict=True)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        client_device, client_match = (None, None)
        if source_event_id is not None or source_ip:
            client_device, client_match = _match_client_device(source_ip, ts)
        prepared.append(
            {
                "uid": uid,
                "ts": ts,
                "path": path,
                "source_event_id": source_event_id,
                "record_id": record_id,
                "logon_id": logon_id,
                "handle_id": handle_id,
                "access_mask": access_mask,
                "share_name": share_name,
                "client_device": client_device,
                "client_match": client_match,
                "user": _s(e.get("win_user"), 80),
                "ip": source_ip,
                "action": _s(e.get("action"), 40) or "File activity",
                "process": _s(e.get("process"), 80),
                "result": e["result"],
            }
        )

    n = 0
    for e in prepared:
        event_key = (
            hashlib.sha256(f"{dev['id']}:{e['uid']}".encode()).hexdigest()
            if e["uid"]
            else None
        )
        try:
            q(
                "INSERT INTO file_events (ts,win_user,device,ip,action,file,process,result,event_key,"
                "source_event_id,record_id,logon_id,handle_id,access_mask,share_name,client_device,client_match) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    e["ts"],
                    e["user"],
                    dev["hostname"],
                    e["ip"],
                    e["action"],
                    e["path"][:400],
                    e["process"],
                    e["result"],
                    event_key,
                    e["source_event_id"],
                    e["record_id"],
                    e["logon_id"],
                    e["handle_id"],
                    e["access_mask"],
                    e["share_name"],
                    e["client_device"],
                    e["client_match"],
                ),
            )
        except IntegrityError:
            if not event_key or not q(
                "SELECT id FROM file_events WHERE event_key=?", (event_key,), one=True
            ):
                raise
            # A retried, acknowledged Linux batch must not duplicate its observations.
        n += 1
    return jsonify(stored=n)


@api.post("/probe")
@agent_required
def probe(dev):
    b = _body()
    folder, result = str(b.get("folder", "")), b.get("result")
    if result not in (
        "review_required",
        "broad_delete_detected",
        "unreadable",
    ) or folder not in configured_paths(dev["hostname"]):
        return jsonify(error="unknown folder or result"), 400
    q(
        "INSERT INTO probes (ts, folder, result) VALUES (?,?,?)",
        (audit.now(), folder, result),
    )
    return jsonify(ok=True)


@api.post("/recovery-events")
@agent_required
def recovery_events(dev):
    from .recovery import ingest

    return ingest(dev, _body())


@api.post("/recovery-status")
@agent_required
def recovery_status(dev):
    from .recovery import ingest_status

    return ingest_status(dev, _body())

