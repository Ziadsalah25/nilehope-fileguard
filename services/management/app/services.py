import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

from . import audit
from .audit import FMT, now
from .db import q, transaction

ACTIONS = ("Delete", "Upload", "Send")
RINGS = ("pilot", "ring20", "ring50", "all")
DEFAULTS = {"approval_minutes": "30", "req_delete": "1", "req_upload": "1", "req_send": "1",
            "pol_delete": "1", "pol_usb": "1", "pol_cloud": "1", "pol_applocker": "0"}
USER_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}$")
HOST_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
FOLDER_RE = re.compile(r'^(\\\\[\w.$-]+\\[^<>"|?*]+|[A-Za-z]:\\[^<>"|?*]+)$')


def directory():
    return current_app.extensions["directory"]


def group_for(action):
    return f"{current_app.config['AD_GROUP_PREFIX']}{action}-Approved"


# ---------- settings ----------
def setting(key):
    r = q("SELECT value FROM settings WHERE key_name=?", (key,), one=True)
    return r["value"] if r else DEFAULTS[key]


def save_setting(key, value):
    with transaction():
        q("DELETE FROM settings WHERE key_name=?", (key,))
        q("INSERT INTO settings (key_name, value) VALUES (?,?)", (key, str(value)))


# ---------- approvals ----------
def create_request(requester, action, path, reason):
    requester, path, reason = requester.strip(), path.strip(), reason.strip()
    if not USER_RE.match(requester):
        raise ValueError("Enter your Windows username (letters, digits, dot, dash).")
    if action not in ACTIONS:
        raise ValueError("Unknown action.")
    if not (2 <= len(path) <= 400 and 3 <= len(reason) <= 300):
        raise ValueError("Please fill the file path and the reason.")
    if setting("req_" + action.lower()) != "1":
        raise ValueError(f"{action} does not need an approval right now.")
    rid = q("INSERT INTO requests (requester, action, path, reason, created_at) VALUES (?,?,?,?,?) RETURNING id",
            (requester, action, path, reason, now()), one=True)["id"]
    audit.log(requester, "request.create", f"#{rid} {action} {path}")
    return rid


def decide(rid, admin, approve):
    r = q("SELECT * FROM requests WHERE id=?", (rid,), one=True)
    if not r or r["status"] != "pending":
        raise ValueError("This request is not pending anymore.")
    if approve:
        if not current_app.config["ENABLE_DIRECTORY_WRITES"]:
            raise ValueError("Directory approvals are disabled. This deployment is in monitoring mode.")
        minutes = int(setting("approval_minutes"))
        expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime(FMT)
        try:
            directory().add(r["requester"], group_for(r["action"]))
        except Exception as exc:
            audit.log(admin, "request.approve", f"#{rid}", "error")
            raise ValueError(f"Directory error: {exc}")
        q("UPDATE requests SET status='approved', decided_by=?, decided_at=?, expires_at=? "
          "WHERE id=? AND status='pending'", (admin, now(), expires, rid))
    else:
        q("UPDATE requests SET status='rejected', decided_by=?, decided_at=? WHERE id=? AND status='pending'",
          (admin, now(), rid))
    audit.log(admin, "request.approve" if approve else "request.reject",
              f"#{rid} {r['requester']} {r['action']}")


def _end_grant(r, actor, new_status):
    still_needed = q("SELECT COUNT(*) AS c FROM requests WHERE status='approved' AND requester=? "
                     "AND action=? AND id<>? AND expires_at > ?",
                     (r["requester"], r["action"], r["id"], now()), one=True)["c"]
    try:
        if not still_needed:
            directory().remove(r["requester"], group_for(r["action"]))
    except Exception:
        audit.log(actor, "grant.remove", f"#{r['id']}", "error")  # worker will retry next round
        return False
    q("UPDATE requests SET status=?, revoked_at=? WHERE id=?", (new_status, now(), r["id"]))
    audit.log(actor, "grant." + new_status, f"#{r['id']} {r['requester']} {r['action']}")
    return True


def expire_grants():
    """Run by the worker every 30 seconds."""
    for r in q("SELECT * FROM requests WHERE status='approved' AND expires_at <= ?", (now(),)):
        _end_grant(r, "system", "expired")


def revoke(rid, admin):
    r = q("SELECT * FROM requests WHERE id=?", (rid,), one=True)
    if not r or r["status"] != "approved":
        raise ValueError("Only an active approval can be revoked.")
    if not _end_grant(r, admin, "revoked"):
        raise ValueError("Directory error; try again.")


def pending_count():
    return q("SELECT COUNT(*) AS c FROM requests WHERE status='pending'", one=True)["c"]


def list_requests(tab="all", limit=200):
    where = {"pending": "WHERE status='pending'",
             "approved": "WHERE status IN ('approved','expired','revoked')",
             "rejected": "WHERE status='rejected'"}.get(tab, "")
    return q(f"SELECT * FROM requests {where} ORDER BY id DESC LIMIT {int(limit)}")


def tab_counts():
    rows = q("SELECT status, COUNT(*) AS c FROM requests GROUP BY status")
    c = {r["status"]: r["c"] for r in rows}
    return {"all": sum(c.values()), "pending": c.get("pending", 0), "rejected": c.get("rejected", 0),
            "approved": c.get("approved", 0) + c.get("expired", 0) + c.get("revoked", 0)}


# ---------- devices ----------
def device_count():
    return q("SELECT COUNT(*) AS c FROM devices", one=True)["c"]


def enroll_device(hostname, ring):
    """Called by the agent the first time it runs. Returns the device's secret API key (shown once)."""
    if not HOST_RE.match(hostname) or ring not in RINGS:
        raise ValueError("bad hostname or ring")
    if q("SELECT 1 AS x FROM devices WHERE hostname=?", (hostname,), one=True):
        raise ValueError("device already enrolled")
    key = secrets.token_urlsafe(32)
    q("INSERT INTO devices (hostname, ring, api_key_hash, created_at) VALUES (?,?,?,?)",
      (hostname, ring, hashlib.sha256(key.encode()).hexdigest(), now()))
    audit.log("agent", "device.enroll", f"{hostname} ({ring})")
    return key


def device_by_key(hostname, key):
    d = q("SELECT * FROM devices WHERE hostname=?", (hostname,), one=True)
    ok = d and hmac.compare_digest(d["api_key_hash"], hashlib.sha256(key.encode()).hexdigest())
    return d if ok else None


def ring_progress():
    cutoff = audit.since(90)
    out = []
    for ring, label in zip(RINGS, ("Pilot", "Ring 20", "Ring 50", "Everyone else")):
        t = q("SELECT COUNT(*) AS c FROM devices WHERE ring=?", (ring,), one=True)["c"]
        o = q("SELECT COUNT(*) AS c FROM devices WHERE ring=? AND last_seen >= ?", (ring, cutoff), one=True)["c"]
        out.append({"ring": ring, "label": label, "total": t, "online": o})
    return out


# ---------- device remote commands ----------
COMMANDS = ("sync_policy", "lock_usb", "restore_usb", "isolate_smb", "collect_logs")


def queue_device_command(device_id, command, actor="admin"):
    if not current_app.config["ENABLE_REMOTE_COMMANDS"]:
        raise ValueError("Remote commands are disabled in monitoring mode.")
    if command not in COMMANDS:
        raise ValueError("Unsupported command.")
    d = q("SELECT hostname FROM devices WHERE id=?", (device_id,), one=True)
    if not d:
        raise ValueError("Unknown device.")
    q("INSERT INTO device_commands (device_id, command, status, created_at) VALUES (?,?,'pending',?)",
      (device_id, command, now()))
    audit.log(actor, "device.command", f"{d['hostname']}: {command}")


def get_pending_command(device_id):
    if not current_app.config["ENABLE_REMOTE_COMMANDS"]:
        return None
    from flask import g
    with transaction():
        suffix = "" if g.db_driver == "sqlite" else " FOR UPDATE SKIP LOCKED"
        cmd = q("SELECT * FROM device_commands WHERE device_id=? AND status='pending' "
                "ORDER BY id ASC LIMIT 1" + suffix, (device_id,), one=True)
        if cmd:
            q("UPDATE device_commands SET status='sent' WHERE id=?", (cmd["id"],))
            return {"id": cmd["id"], "command": cmd["command"]}
    return None


def finish_device_command(device_id, cmd_id, output, success=True):
    status = "completed" if success else "failed"
    changed = q("UPDATE device_commands SET status=?, output=?, executed_at=? "
                "WHERE id=? AND device_id=? AND status='sent'",
                (status, output[:1000], now(), cmd_id, device_id))
    if changed == 1:
        return True
    existing = q("SELECT status, output FROM device_commands WHERE id=? AND device_id=?",
                 (cmd_id, device_id), one=True)
    return bool(existing and existing["status"] == status and existing["output"] == output[:1000])


def list_device_commands(limit=20):
    return q("SELECT c.*, d.hostname FROM device_commands c JOIN devices d ON c.device_id=d.id ORDER BY c.id DESC LIMIT ?",
             (limit,))


# ---------- overview numbers ----------
def stats():
    day, cutoff = now()[:10], audit.since(90)
    total = device_count()
    online = q("SELECT COUNT(*) AS c FROM devices WHERE last_seen >= ?", (cutoff,), one=True)["c"]
    blocked = q("SELECT COUNT(*) AS c FROM file_events WHERE result='blocked' AND ts >= ?", (day,), one=True)["c"]
    decisions = q("SELECT COUNT(*) AS c FROM requests WHERE decided_at >= ?", (day,), one=True)["c"]
    return {"total": total, "online": online, "offline": total - online, "pending": pending_count(),
            "blocked": blocked, "decisions": decisions}


def week_activity():
    days = [(datetime.now(timezone.utc) - timedelta(days=i)).date() for i in range(6, -1, -1)]
    rows = q("SELECT substr(ts,1,10) AS d, result, COUNT(*) AS c FROM file_events WHERE ts >= ? GROUP BY 1, 2",
             (days[0].isoformat(),))
    counts = {(r["d"], r["result"]): r["c"] for r in rows}
    return [{"label": d.strftime("%a"), "blocked": counts.get((d.isoformat(), "blocked"), 0),
             "allowed": counts.get((d.isoformat(), "allowed"), 0), "observed": counts.get((d.isoformat(), "observed"), 0)} for d in days]


def layers():
    """Report observations without equating an ACL heuristic with effective protection."""
    folders = q("SELECT path FROM folders")
    checked = 0
    warnings = 0
    for f in folders:
        p = q("SELECT result FROM probes WHERE folder=? AND ts >= ? ORDER BY id DESC LIMIT 1",
              (f["path"], audit.since(86400)), one=True)
        checked += bool(p)
        warnings += bool(p and p["result"] in ("broad_delete_detected", "not_enforced", "unreadable"))
    s = stats()
    dir_ok, dir_msg = directory().ping()
    return [
        {"name": "Share ACL observations", "ok": False,
         "line1": "Effective user access and prevention require Windows validation",
         "line2": f"{checked} of {len(folders)} targets checked in 24h; {warnings} warnings. Protection is not verified."},
        {"name": "Logging layer", "ok": s["online"] > 0,
         "line1": "Agent heartbeats and forwarded file events",
         "line2": f"{s['online']} of {s['total']} agents connected"},
        {"name": "Approval layer", "ok": bool(dir_ok) and directory().name != MOCK_NAME and current_app.config["ENABLE_DIRECTORY_WRITES"],
         "line1": "Directory writes enabled" if current_app.config["ENABLE_DIRECTORY_WRITES"] else "Directory writes disabled (monitoring mode)",
         "line2": f"Directory adapter: {dir_msg}"},
    ]


MOCK_NAME = "mock (lab mode)"


def search(term):
    like = f"%{term}%"
    devices = q("SELECT * FROM devices WHERE hostname LIKE ? OR win_user LIKE ? OR ip LIKE ? LIMIT 50",
                (like, like, like))
    events = q("SELECT * FROM file_events WHERE win_user LIKE ? OR file LIKE ? OR device LIKE ? "
               "ORDER BY id DESC LIMIT 50", (like, like, like))
    return devices, events
