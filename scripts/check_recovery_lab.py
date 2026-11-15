"""Exercise create/modify/delete/restore using a uniquely named disposable lab file."""

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def wait_for(check, description):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise RuntimeError("Timed out: " + description)


def main():
    lab = Path(__file__).resolve().parents[1] / ".local/recovery-lab"
    if not (lab / "recovery-config.json").exists():
        raise SystemExit("Start the recovery lab first.")
    sample = lab / "protected" / ("sample-report-" + uuid.uuid4().hex[:8] + ".txt")
    manifest = lab / "state/manifest.json"

    def versions():
        if not manifest.exists():
            return []
        return json.loads(manifest.read_text()).get(sample.name, {}).get("versions", [])

    sample.write_text("Disposable FileGuard lab report, version one.\n")
    wait_for(lambda: len(versions()) == 1, "initial protected copy")
    expected = b"Disposable FileGuard lab report, version two.\n"
    sample.write_bytes(expected)
    wait_for(lambda: len(versions()) == 2, "modified content version")
    digest = hashlib.sha256(expected).hexdigest()
    sample.unlink()
    started = time.monotonic()
    wait_for(lambda: sample.exists() and sample.read_bytes() == expected, "deleted-file recovery")
    actual = hashlib.sha256(sample.read_bytes()).hexdigest()
    assert digest == actual == versions()[-1]["sha256"], "Restored content hash mismatch"
    result = {"timestamp_utc": datetime.now(UTC).isoformat(), "sample": sample.name,
              "versions": len(versions()), "restored": True, "sha256": actual,
              "recovery_seconds": round(time.monotonic() - started, 3),
              "scope": "Disposable local lab only; no hospital connection"}
    (lab / "validation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
