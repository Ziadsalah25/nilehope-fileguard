"""Hash-chained audit log. Each row stores the hash of the previous row."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from .db import IntegrityError, q

FMT = "%Y-%m-%dT%H:%M:%SZ"
GENESIS = "0" * 64


def now():
    return datetime.now(timezone.utc).strftime(FMT)


def since(seconds):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime(FMT)


def _digest(prev_hash, entry):
    # sort_keys + fixed separators = the SAME text every time, so the same hash every time
    body = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def log(actor, action, target="-", outcome="success", dedupe=0):
    """Append one entry. 'actor' is None for anonymous visitors.
    dedupe=60 skips an identical anonymous entry written in the last 60 s (stops log flooding)."""
    target = target or "-"
    if dedupe and q("SELECT 1 AS x FROM audit WHERE actor IS NULL AND action=? AND target=? "
                    "AND outcome=? AND ts >= ? LIMIT 1", (action, target, outcome, since(dedupe)), one=True):
        return
    for _ in range(10):
        last = q("SELECT hash FROM audit ORDER BY id DESC LIMIT 1", one=True)
        prev = last["hash"] if last else GENESIS
        entry = {"ts": now(), "actor": actor, "action": action, "target": target, "outcome": outcome}
        try:
            q("INSERT INTO audit (ts, actor, action, target, outcome, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
              (entry["ts"], actor, action, target, outcome, prev, _digest(prev, entry)))
            return
        except IntegrityError:
            continue  # someone else appended first; read the new last hash and try again
    raise RuntimeError("audit log is too busy")


def verify():
    """Return (True, None) or (False, id_of_first_broken_entry)."""
    prev = GENESIS
    for r in q("SELECT * FROM audit ORDER BY id"):
        entry = {k: r[k] for k in ("ts", "actor", "action", "target", "outcome")}
        if r["prev_hash"] != prev or r["hash"] != _digest(prev, entry):
            return False, r["id"]
        prev = r["hash"]
    return True, None
