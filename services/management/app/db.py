"""Explicit database selection. A failed configured database never changes storage."""

import os
import sqlite3
from contextlib import contextmanager
from urllib.parse import unquote, urlparse

from flask import current_app, g

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    pymysql = None
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None


def get_driver_name():
    scheme = urlparse(current_app.config["DATABASE_URL"]).scheme
    if scheme in ("mysql", "mysql+pymysql"):
        if pymysql is None:
            raise RuntimeError("Install PyMySQL for the configured MySQL database")
        return "mysql"
    if scheme in ("postgres", "postgresql"):
        if psycopg is None:
            raise RuntimeError("Install psycopg for the configured PostgreSQL database")
        return "postgres"
    if scheme == "sqlite":
        return "sqlite"
    raise RuntimeError("DATABASE_URL must use sqlite, mysql or postgresql")


def get_db():
    if "db" not in g:
        url = current_app.config["DATABASE_URL"]
        driver = get_driver_name()
        if driver == "mysql":
            p = urlparse(url)
            conn = pymysql.connect(
                host=p.hostname or "127.0.0.1",
                port=p.port or 3306,
                user=unquote(p.username or ""),
                password=unquote(p.password or ""),
                database=p.path.lstrip("/"),
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=5,
            )
        elif driver == "postgres":
            conn = psycopg.connect(
                url, row_factory=dict_row, autocommit=True, connect_timeout=5
            )
        else:
            if not url.startswith("sqlite:///"):
                raise RuntimeError("Use sqlite:/// followed by a database path")
            path = url[len("sqlite:///") :]
            conn = sqlite3.connect(path, timeout=15, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
        g.db, g.db_driver = conn, driver
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


@contextmanager
def transaction():
    conn = get_db()
    if g.get("in_transaction", False):
        yield conn
        return
    g.in_transaction = True
    try:
        with conn.cursor() if g.db_driver != "sqlite" else _sqlite_cursor(conn) as cur:
            cur.execute("BEGIN IMMEDIATE" if g.db_driver == "sqlite" else "BEGIN")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        g.in_transaction = False


@contextmanager
def _sqlite_cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def q(sql, params=(), one=False):
    conn = get_db()
    driver = g.db_driver
    if driver in ("mysql", "postgres"):
        sql = sql.replace("?", "%s")
    returning_id = "RETURNING id" in sql and driver == "mysql"
    if returning_id:
        sql = sql.replace("RETURNING id", "")
    cur = conn.cursor()
    try:
        cur.execute(sql, params) if params else cur.execute(sql)
        if returning_id:
            return {"id": cur.lastrowid}
        if cur.description:
            rows = cur.fetchall()
            return (rows[0] if rows else None) if one else rows
        return cur.rowcount
    finally:
        cur.close()


def init_schema():
    get_db()
    pk = {
        "mysql": "INT AUTO_INCREMENT PRIMARY KEY",
        "postgres": "BIGSERIAL PRIMARY KEY",
        "sqlite": "INTEGER PRIMARY KEY AUTOINCREMENT",
    }[g.db_driver]
    if g.db_driver == "sqlite":
        q("PRAGMA journal_mode=WAL")
    path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(path, encoding="utf-8") as source:
        sql = (
            source.read()
            .replace("{PK}", pk)
            .replace(
                "{PATH_TYPE}",
                "VARCHAR(400) COLLATE utf8mb4_bin"
                if g.db_driver == "mysql"
                else "VARCHAR(400)",
            )
        )
    for statement in sql.split(";"):
        if statement.strip():
            q(statement.strip())
    migrate_monitoring()


_errors = [sqlite3.IntegrityError]
if pymysql is not None:
    _errors.append(pymysql.err.IntegrityError)
if psycopg is not None:
    _errors.append(psycopg.IntegrityError)
IntegrityError = tuple(_errors)


def _columns(table):
    if g.db_driver == "sqlite":
        return {r["name"] for r in q(f"PRAGMA table_info({table})")}
    if g.db_driver == "mysql":
        return {r["Field"] for r in q(f"SHOW COLUMNS FROM {table}")}
    return {
        r["column_name"]
        for r in q(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=?",
            (table,),
        )
    }


def migrate_monitoring():
    """Add nullable telemetry/target fields without replacing any existing records."""
    from .telemetry import FIELDS

    changes = {
        "devices": FIELDS,
        "folders": {
            "target_os": "VARCHAR(16) NOT NULL DEFAULT 'windows'",
            "target_host": "VARCHAR(63) NOT NULL DEFAULT ''",
        },
        "file_events": {"event_key": "VARCHAR(64)"},
    }
    for table, fields in changes.items():
        existing = _columns(table)
        for field, definition in fields.items():
            if field not in existing:
                q(f"ALTER TABLE {table} ADD COLUMN {field} {definition}")
    migrate_folder_identity()
    if g.db_driver == "sqlite":
        found = any(
            r["unique"]
            and [x["name"] for x in q(f"PRAGMA index_info('{r['name']}')")]
            == ["event_key"]
            for r in q("PRAGMA index_list(file_events)")
        )
    elif g.db_driver == "mysql":
        found = any(
            r["Column_name"] == "event_key" and not r["Non_unique"]
            for r in q("SHOW INDEX FROM file_events")
        )
    else:
        found = bool(
            q(
                "SELECT 1 AS x FROM pg_indexes WHERE schemaname=current_schema() "
                "AND tablename='file_events' AND indexdef LIKE '%UNIQUE%' AND indexdef LIKE '%(event_key)%'",
                one=True,
            )
        )
    if not found:
        q("CREATE UNIQUE INDEX uq_file_event_key ON file_events(event_key)")


def migrate_folder_identity():
    """Preserve folder IDs while replacing legacy path-only uniqueness with host-scoped identity."""
    if g.db_driver == "sqlite":
        indexes = q("PRAGMA index_list(folders)")
        path_only = any(
            r["unique"]
            and [x["name"] for x in q(f"PRAGMA index_info('{r['name']}')")] == ["path"]
            for r in indexes
        )
        if path_only:
            with transaction():
                q("ALTER TABLE folders RENAME TO folders_legacy_identity")
                q(
                    "CREATE TABLE folders (id INTEGER PRIMARY KEY AUTOINCREMENT, path VARCHAR(400) NOT NULL, "
                    "state VARCHAR(40) NOT NULL DEFAULT 'Monitored', target_os VARCHAR(16) NOT NULL DEFAULT 'windows', "
                    "target_host VARCHAR(63) NOT NULL DEFAULT '', UNIQUE(path,target_os,target_host))"
                )
                q(
                    "INSERT INTO folders (id,path,state,target_os,target_host) SELECT id,path,state,target_os,COALESCE(target_host,'') FROM folders_legacy_identity"
                )
                q("DROP TABLE folders_legacy_identity")
        return
    if g.db_driver == "mysql":
        groups = {}
        for row in q("SHOW INDEX FROM folders"):
            if not row["Non_unique"]:
                groups.setdefault(row["Key_name"], []).append(row["Column_name"])
        for name, columns in groups.items():
            if columns == ["path"]:
                name = name.replace("`", "``")
                q(f"ALTER TABLE folders DROP INDEX `{name}`")
        q("UPDATE folders SET target_host='' WHERE target_host IS NULL")
        q(
            "ALTER TABLE folders MODIFY path VARCHAR(400) COLLATE utf8mb4_bin NOT NULL, MODIFY target_host VARCHAR(63) NOT NULL DEFAULT ''"
        )
        if ["path", "target_os", "target_host"] not in groups.values():
            q(
                "CREATE UNIQUE INDEX uq_folder_target ON folders(path,target_os,target_host)"
            )
        return
    constraints = q(
        "SELECT conname FROM pg_constraint WHERE conrelid='folders'::regclass "
        "AND contype='u' AND pg_get_constraintdef(oid)='UNIQUE (path)'"
    )
    for row in constraints:
        name = row["conname"].replace('"', '""')
        q(f'ALTER TABLE folders DROP CONSTRAINT "{name}"')
    q("UPDATE folders SET target_host='' WHERE target_host IS NULL")
    q(
        "ALTER TABLE folders ALTER COLUMN target_host SET DEFAULT '', ALTER COLUMN target_host SET NOT NULL"
    )
    found = q(
        "SELECT 1 AS x FROM pg_indexes WHERE schemaname=current_schema() AND tablename='folders' "
        "AND indexdef LIKE '%UNIQUE%' AND indexdef LIKE '%(path, target_os, target_host)%'",
        one=True,
    )
    if not found:
        q("CREATE UNIQUE INDEX uq_folder_target ON folders(path,target_os,target_host)")
