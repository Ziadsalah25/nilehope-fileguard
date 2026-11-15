import secrets

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from . import audit, auth, services
from .auth import login_required
from .db import q
from .shares import valid_share

bp = Blueprint("main", __name__)


def healthz():
    try:
        q("SELECT COUNT(*) AS c FROM settings")
    except Exception:
        return {"ok": False, "error": "Configured database or schema is unavailable"}, 503
    return {"ok": True}


# ---------- login ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user, pw = request.form.get("username", "").strip()[:64], request.form.get("password", "")
        if auth.locked(user):
            audit.log(None, "login", user or "-", "locked")
            flash("Too many failed attempts. Try again in 15 minutes.", "error")
        else:
            row = q("SELECT * FROM admins WHERE username=?", (user,), one=True)
            if row and check_password_hash(row["password_hash"], pw):
                session.clear()
                session.permanent = True
                session["admin"], session["csrf"] = user, secrets.token_hex(16)
                audit.log(user, "login", "-", "success")
                return redirect(url_for("main.overview"))
            audit.log(None, "login", user or "-", "failed")
            flash("Wrong username or password.", "error")
    return render_template("login.html")


@bp.post("/logout")
@login_required
def logout():
    audit.log(session["admin"], "logout")
    session.clear()
    return redirect(url_for("main.login"))


# ---------- overview ----------
def _overview_data():
    return dict(s=services.stats(), week=services.week_activity(), layers=services.layers(),
                latest=services.list_requests("all", 5))


@bp.get("/")
@login_required
def overview():
    return render_template("overview.html", **_overview_data())


@bp.get("/partials/overview")
@login_required
def overview_partial():
    return render_template("_overview.html", **_overview_data())


# ---------- approvals ----------
@bp.get("/approvals")
@login_required
def approvals():
    tab = request.args.get("tab", "all")
    return render_template("approvals.html", tab=tab, rows=services.list_requests(tab), counts=services.tab_counts())


@bp.post("/approvals/<int:rid>/<verb>")
@login_required
def approval_action(rid, verb):
    if verb not in ("approve", "reject", "revoke"):
        abort(404)
    try:
        if verb == "revoke":
            services.revoke(rid, session["admin"])
        else:
            services.decide(rid, session["admin"], verb == "approve")
        flash("Done.", "ok")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.approvals"))


# Staff form (no admin login). In production put it behind your intranet / Windows SSO.
@bp.route("/request", methods=["GET", "POST"])
def request_form():
    if not current_app.config["STAFF_REQUESTS_ENABLED"] and not session.get("admin"):
        abort(403, "Staff requests are disabled until authenticated staff access is configured.")
    if request.method == "POST":
        try:
            rid = services.create_request(request.form.get("requester", ""), request.form.get("action", ""),
                                          request.form.get("path", ""), request.form.get("reason", ""))
            flash(f"Request #{rid} sent. An administrator will review it.", "ok")
            return redirect(url_for("main.request_form"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("request.html", actions=services.ACTIONS)


# ---------- devices ----------
@bp.get("/devices")
@login_required
def devices():
    rows = q("SELECT * FROM devices ORDER BY hostname")
    cmds = services.list_device_commands(10)
    return render_template("devices.html", rows=rows, rings=services.ring_progress(), commands=cmds, cutoff=audit.since(90))


@bp.post("/devices/<int:did>/ring")
@login_required
def device_ring(did):
    ring = request.form.get("ring", "")
    if ring not in services.RINGS:
        abort(400)
    q("UPDATE devices SET ring=? WHERE id=?", (ring, did))
    audit.log(session["admin"], "device.ring", f"#{did} -> {ring}")
    return redirect(url_for("main.devices"))


@bp.post("/devices/<int:did>/command")
@login_required
def device_send_command(did):
    cmd = request.form.get("command", "").strip()
    try:
        services.queue_device_command(did, cmd, session["admin"])
        flash(f"Command '{cmd}' queued. Device will execute on next heartbeat.", "ok")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.devices"))


@bp.post("/set-lang")
def set_language():
    lang = request.form.get("lang", "ar")
    session["lang"] = "ar" if lang == "ar" else "en"
    return redirect(url_for("main.overview") if session.get("admin") else url_for("main.login"))


@bp.post("/devices/<int:did>/remove")
@login_required
def device_remove(did):
    q("DELETE FROM device_commands WHERE device_id=?", (did,))
    q("DELETE FROM devices WHERE id=?", (did,))
    audit.log(session["admin"], "device.remove", f"#{did}")
    flash("Device removed. It can enroll again.", "ok")
    return redirect(url_for("main.devices"))


# ---------- audit ----------
@bp.get("/audit", endpoint="audit_page")
@login_required
def audit_page():
    term = request.args.get("q", "").strip()
    action = request.args.get("action", "")
    like = f"%{term}%"
    events = q("SELECT * FROM file_events WHERE (win_user LIKE ? OR device LIKE ? OR ip LIKE ? OR file LIKE ?) "
               "ORDER BY id DESC LIMIT 100", (like, like, like, like))
    sql, params = "SELECT * FROM audit WHERE (COALESCE(actor,'') LIKE ? OR target LIKE ?)", [like, like]
    if action:
        sql, params = sql + " AND action=?", params + [action]
    trail = q(sql + " ORDER BY id DESC LIMIT 100", tuple(params))
    actions = [r["action"] for r in q("SELECT DISTINCT action FROM audit ORDER BY action")]
    ok, broken_at = audit.verify()
    return render_template("audit.html", events=events, trail=trail, actions=actions, term=term,
                           action=action, ok=ok, broken_at=broken_at)


# ---------- settings ----------
@bp.get("/settings")
@login_required
def settings():
    s = {k: services.setting(k) for k in services.DEFAULTS}
    return render_template("settings.html", s=s, folders=q("SELECT * FROM folders ORDER BY path"))


@bp.post("/settings/save")
@login_required
def settings_save():
    try:
        minutes = max(5, min(120, int(request.form.get("approval_minutes", "30"))))
    except ValueError:
        minutes = 30
    services.save_setting("approval_minutes", minutes)
    for key in services.DEFAULTS:
        if key != "approval_minutes":
            services.save_setting(key, "1" if request.form.get(key) else "0")
    audit.log(session["admin"], "settings.save", f"approval {minutes} min")
    flash("Settings saved. Policy switches are informational: Windows enforces them.", "ok")
    return redirect(url_for("main.settings"))


@bp.post("/settings/folders/add")
@login_required
def folder_add():
    path = request.form.get("path", "").strip().rstrip("\\")
    if not valid_share(path):
        flash(r"Use a UNC path like \\FILESRV\Finance or a drive path like D:\Shares\Finance.", "error")
    elif q("SELECT 1 AS x FROM folders WHERE path=?", (path,), one=True):
        flash("Folder already listed.", "error")
    else:
        q("INSERT INTO folders (path) VALUES (?)", (path,))
        audit.log(session["admin"], "folder.add", path)
        flash("Folder added.", "ok")
    return redirect(url_for("main.settings"))


@bp.post("/settings/folders/<int:fid>/remove")
@login_required
def folder_remove(fid):
    row = q("SELECT path FROM folders WHERE id=?", (fid,), one=True)
    if row:
        q("DELETE FROM folders WHERE id=?", (fid,))
        audit.log(session["admin"], "folder.remove", row["path"])
    return redirect(url_for("main.settings"))


# ---------- search ----------
@bp.get("/search")
@login_required
def search():
    term = request.args.get("q", "").strip()
    devices, events = services.search(term) if term else ([], [])
    return render_template("search.html", term=term, devices=devices, events=events)
