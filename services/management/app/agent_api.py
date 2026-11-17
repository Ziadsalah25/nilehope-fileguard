import hashlib
import hmac
import re
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, request

from . import audit, services
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
    q(
        "UPDATE devices SET win_user=?, department=COALESCE(?, department), ip=?, mac=?, agent_version=?, "
        "last_seen=? WHERE id=?",
        (
            _s(b.get("win_user"), 80),
            _s(b.get("department"), 80),
            _s(b.get("ip"), 45),
            _s(b.get("mac"), 20),
            _s(b.get("agent_version"), 20),
            audit.now(),
            dev["id"],
        ),
    )
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
    n = 0
    for e in items:
        if e.get("result") not in (
            "blocked",
            "allowed",
            "observed",
        ) or not event_in_scope(str(e.get("file", "")), dev):
            continue
        uid = str(e.get("event_id", ""))
        if uid and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", uid):
            return jsonify(error="Invalid event_id"), 400
        event_key = (
            hashlib.sha256(f"{dev['id']}:{uid}".encode()).hexdigest() if uid else None
        )
        try:
            q(
                "INSERT INTO file_events (ts, win_user, device, ip, action, file, process, result, event_key) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    _s(e.get("ts"), 20) or audit.now(),
                    _s(e.get("win_user"), 80),
                    dev["hostname"],
                    _s(e.get("ip"), 45),
                    _s(e.get("action"), 40) or "Delete",
                    _s(e.get("file"), 400),
                    _s(e.get("process"), 80),
                    e["result"],
                    event_key,
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
