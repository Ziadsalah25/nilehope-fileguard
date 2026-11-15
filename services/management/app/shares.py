"""Share inventory imports register monitoring targets; they never modify Windows ACLs."""

import csv
import re

import click

from . import audit, db

UNC_RE = re.compile(
    r'^\\\\([A-Za-z0-9_.-]+)\\([^\\/<>:"|?*\x00-\x1f]+)(?:\\[^/<>:"|?*\x00-\x1f]+)*$'
)


def valid_share(path):
    match = UNC_RE.fullmatch(path)
    return bool(
        match
        and len(path) <= 400
        and all(p not in (".", "..") for p in path[2:].split("\\"))
    )


def server_matches(path, hostname):
    match = UNC_RE.fullmatch(path)
    return bool(
        match and match[1].split(".")[0].casefold() == hostname.split(".")[0].casefold()
    )


def configured_paths(hostname):
    return [
        r["path"]
        for r in db.q("SELECT path FROM folders ORDER BY path")
        if server_matches(r["path"], hostname)
    ]


def path_in_scope(path, hostname):
    if not valid_share(path) or not server_matches(path, hostname):
        return False
    # Hostnames may be recorded as FQDN or NetBIOS names. Compare the share and subpath.
    candidate = path.split("\\", 3)[3].rstrip("\\").casefold()
    for root in configured_paths(hostname):
        relative = root.split("\\", 3)[3].rstrip("\\").casefold()
        if candidate == relative or candidate.startswith(relative + "\\"):
            return True
    return False


def register_cli(app):
    @app.cli.command("import-shares")
    @click.argument("csv_file", type=click.File("r", encoding="utf-8-sig"))
    def import_shares(csv_file):
        """Import a CSV containing a Path column, as exported by Discover-Shares.ps1."""
        rows = list(csv.DictReader(csv_file))
        if not rows or "Path" not in rows[0]:
            raise click.ClickException("CSV needs at least one row and a Path column")
        paths = sorted(set(r.get("Path", "").strip().rstrip("\\") for r in rows))
        if any(not valid_share(p) for p in paths):
            raise click.ClickException(
                "Every Path must be an exact UNC share/subfolder path; wildcards are not supported"
            )
        count = 0
        with db.transaction():
            existing = {r["path"].casefold() for r in db.q("SELECT path FROM folders")}
            for path in paths:
                if path.casefold() not in existing:
                    db.q("INSERT INTO folders (path) VALUES (?)", (path,))
                    existing.add(path.casefold())
                    count += 1
        audit.log("cli", "shares.import", f"{count} monitoring targets")
        click.echo(
            f"Registered {count} new monitoring targets. No ACLs or file contents changed."
        )


def valid_linux_path(path):
    import posixpath

    return (
        isinstance(path, str)
        and 1 < len(path) <= 400
        and path.startswith("/")
        and not path.startswith("//")
        and posixpath.normpath(path) == path
        and not any(char in path for char in ("\x00", "\n", "\r", "*", "?", "["))
    )


def configured_linux_paths(hostname):
    return [
        r["path"]
        for r in db.q(
            "SELECT path FROM folders WHERE target_os='linux' AND LOWER(target_host)=LOWER(?) ORDER BY path",
            (hostname,),
        )
    ]


def event_in_scope(path, device):
    if device["os_family"] == "linux":
        if not valid_linux_path(path):
            return False
        return any(
            path == root or path.startswith(root + "/")
            for root in configured_linux_paths(device["hostname"])
        )
    return path_in_scope(path, device["hostname"])
