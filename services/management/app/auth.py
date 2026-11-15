from functools import wraps

from flask import abort, redirect, request, session, url_for

from . import audit
from .db import q


def locked(username):
    """True after 5 failed logins for this username in the last 15 minutes."""
    r = q("SELECT COUNT(*) AS c FROM audit WHERE action='login' AND outcome='failed' "
          "AND target=? AND ts >= ?", (username, audit.since(900)), one=True)
    return r["c"] >= 5


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/partials/"):
                abort(401)  # background refresh: no log entry, the page will redirect to /login
            audit.log(None, "access", request.path, "denied_unauthenticated", dedupe=60)
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)
    return wrapped
