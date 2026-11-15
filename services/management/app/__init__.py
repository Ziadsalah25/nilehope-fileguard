import os
import secrets
from datetime import timedelta

import click
from flask import Flask, abort, request, session
from werkzeug.security import generate_password_hash

from . import audit, db, directory


def create_app(config=None):
    app = Flask(__name__)
    prod = os.environ.get("FC_ENV") == "production"
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE_URL=os.environ.get("DATABASE_URL", "sqlite:///file_control.db"),
        ENROLL_TOKEN=os.environ.get("ENROLL_TOKEN", ""),
        AD_GROUP_PREFIX=os.environ.get("AD_GROUP_PREFIX", "FC-"),
        ENABLE_DIRECTORY_WRITES=os.environ.get("ENABLE_DIRECTORY_WRITES", "0") == "1",
        ENABLE_REMOTE_COMMANDS=os.environ.get("ENABLE_REMOTE_COMMANDS", "0") == "1",
        STAFF_REQUESTS_ENABLED=os.environ.get("STAFF_REQUESTS_ENABLED", "0") == "1",
        MAX_CONTENT_LENGTH=1024 * 1024,
        SERVICE_ROLE=os.environ.get("SERVICE_ROLE", "all"),
        AGENT_HEALTH_URL=os.environ.get("AGENT_HEALTH_URL", ""),
        CONSOLE_ENVIRONMENT=os.environ.get("CONSOLE_ENVIRONMENT", "local"),
        PUBLIC_CONSOLE_URL=os.environ.get("PUBLIC_CONSOLE_URL", "http://localhost:8080"),
        ENROLLMENT_ENABLED=os.environ.get("ENROLLMENT_ENABLED", "1") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=prod,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    )
    if config:
        app.config.update(config)
    if prod:
        if len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"].startswith("replace_"):
            raise RuntimeError("Set a random SECRET_KEY of at least 32 characters in production")
        if len(app.config["ENROLL_TOKEN"]) < 32:
            raise RuntimeError("Set a random ENROLL_TOKEN of at least 32 characters in production")

    db.init_app(app)
    app.extensions["directory"] = directory.from_env()
    if prod and app.config["ENABLE_DIRECTORY_WRITES"] and isinstance(app.extensions["directory"], directory.MockDirectory):
        raise RuntimeError("Live directory approvals require a configured LDAPS connection")

    from .shares import register_cli
    register_cli(app)

    from .agent_api import api
    from .console_api import console
    from .routes import bp
    role = app.config["SERVICE_ROLE"]
    if role not in ("all", "console", "agent"):
        raise RuntimeError("SERVICE_ROLE must be all, console, or agent")
    if role in ("all", "console"):
        app.register_blueprint(bp)
        app.register_blueprint(console)
    if role in ("all", "agent"):
        app.register_blueprint(api)
    from .routes import healthz
    app.add_url_rule("/healthz", "healthz", healthz)

    @app.before_request
    def csrf_protect():
        # Agents use API keys, everything else that changes data needs the CSRF token.
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.path.startswith("/api/agent/"):
            sent, expected = request.headers.get("X-CSRF-Token", request.form.get("csrf", "")), session.get("csrf", "")
            if not expected or not secrets.compare_digest(sent.encode(), expected.encode()):
                abort(400, "Bad CSRF token")

    @app.context_processor
    def inject():
        session.setdefault("csrf", secrets.token_hex(16))
        lang = session.get("lang", "ar")
        ctx = {"csrf": session["csrf"], "lang": lang,
               "remote_commands_enabled": app.config["ENABLE_REMOTE_COMMANDS"],
               "directory_writes_enabled": app.config["ENABLE_DIRECTORY_WRITES"]}
        if session.get("admin"):
            from . import services
            ctx.update(pending=services.pending_count(), device_count=services.device_count())
        return ctx

    @app.after_request
    def security_headers(resp):
        if request.path.startswith("/api/console/"):
            resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; font-src 'self' data:; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; frame-ancestors 'none'"
        return resp

    @app.cli.command("init-db")
    def init_db_cmd():
        """Create the tables (safe to run many times)."""
        db.init_schema()
        click.echo("database ready")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    def create_admin_cmd(username, password):
        """Create or reset an admin: flask --app app create-admin alice"""
        if len(password) < 12:
            raise click.ClickException("Use at least 12 characters")
        if not 1 <= len(username) <= 64:
            raise click.ClickException("Username must have 1–64 characters")
        with db.transaction():
            db.q("DELETE FROM admins WHERE username=?", (username,))
            db.q("INSERT INTO admins (username, password_hash, created_at) VALUES (?,?,?)",
                 (username, generate_password_hash(password), audit.now()))
        audit.log("cli", "admin.create", username)
        click.echo("admin saved")

    return app
