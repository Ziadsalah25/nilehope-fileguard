"""Exercise the local Docker upload queue and a disposable foreground recovery worker."""

import argparse
import hashlib
import http.cookiejar
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", required=True)
    parser.add_argument("--worker", required=True, help="Published FileGuard.Recovery.dll")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    values = dict(line.split("=", 1) for line in (project / ".env").read_text().splitlines()
                  if line and not line.startswith("#"))
    if values.get("FC_ENV") != "testing":
        raise SystemExit("Run this check only against the local testing stack.")
    origin = "http://127.0.0.1:" + values.get("FRONTEND_PORT", "8080")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = ""

    def call(path, method="GET", data=None, content_type="application/json", expected=200):
        body = json.dumps(data).encode() if data is not None and not isinstance(data, bytes) else data
        headers = {"X-CSRF-Token": csrf, "Content-Type": content_type}
        req = urllib.request.Request(origin + "/api/console" + path, body, headers, method=method)
        try:
            response = opener.open(req, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            if response.status != expected:
                raise AssertionError(f"{method} {path}: expected {expected}, got {response.status}")
            raw = response.read()
            return json.loads(raw) if response.headers.get_content_type() == "application/json" else raw

    session = call("/session")
    csrf = session["csrf"]
    if not session.get("upload_approval_enabled"):
        raise SystemExit("Enable UPLOAD_APPROVAL_ENABLED in the local stack before this check.")
    login = call("/login", "POST", {"username": values.get("BOOTSTRAP_ADMIN_USER", "admin"),
                                   "password": values["BOOTSTRAP_ADMIN_PASSWORD"]})
    csrf = login["csrf"]
    content = b"Disposable upload approval validation."
    for decision in ("approve", "reject"):
        boundary = "FileGuard" + uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"reason\"\r\n\r\nLocal automated pilot validation\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"pilot-check.txt\"\r\n"
                "Content-Type: text/plain\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        result = call("/uploads", "POST", body, f"multipart/form-data; boundary={boundary}", 201)
        path = f"/uploads/{result['id']}"
        call(path + "/download", expected=403)
        call(path + "/" + decision, "POST", {})
        downloaded = call(path + "/download", expected=200 if decision == "approve" else 403)
        if decision == "approve":
            assert downloaded == content
    print("PASS: live Docker upload queue enforces pending, approved, and rejected download access.", flush=True)

    lab = project / ".local" / ("recovery-check-" + uuid.uuid4().hex)
    for name in ("protected", "repository", "state"):
        (lab / name).mkdir(parents=True)
    hostname = "QA-RECOVERY-" + uuid.uuid4().hex[:10]
    config = {"protectedRoot": str(lab / "protected"), "repositoryRoot": str(lab / "repository"),
              "stateRoot": str(lab / "state"), "autoRestore": False, "scanSeconds": 1,
              "settleMilliseconds": 100, "serverUrl": origin, "allowInsecureLoopback": True,
              "enrollmentToken": values["ENROLL_TOKEN"], "hostname": hostname}
    config_path = lab / "config.json"
    sample = lab / "protected" / "disposable.txt"

    def wait(check, message):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(0.25)
        raise AssertionError(message)

    def captured(digest):
        path = lab / "state" / "manifest.json"
        if not path.exists():
            return False
        history = json.loads(path.read_text()).get("disposable.txt", {})
        versions = history.get("versions", [])
        return bool(versions and versions[-1]["sha256"] == digest)

    def reported(kind, mode):
        data = call("/recovery?q=" + hostname)
        return (any(item["device"] == hostname and item["kind"] == kind for item in data["items"])
                and any(agent["device"] == hostname and agent["mode"] == mode for agent in data["agents"]))

    for recover in (False, True):
        config["autoRestore"] = recover
        config_path.write_text(json.dumps(config))
        config_path.chmod(0o600)
        with (lab / "worker.log").open("ab") as log:
            worker = subprocess.Popen([args.dotnet, args.worker, "--config", str(config_path)],
                                      stdout=log, stderr=subprocess.STDOUT)
            try:
                if not recover:
                    sample.write_bytes(b"version one")
                    wait(lambda: captured(hashlib.sha256(b"version one").hexdigest()), "First snapshot not captured.")
                    sample.write_bytes(b"version two")
                    wait(lambda: captured(hashlib.sha256(b"version two").hexdigest()), "Updated snapshot not captured.")
                    sample.unlink()
                    wait(lambda: reported("delete_observed", "monitoring"), "Monitoring report was not ingested.")
                    assert not sample.exists()
                    print("PASS: monitoring preserves versions and reports deletion without restoring.", flush=True)
                else:
                    wait(lambda: sample.exists() and sample.read_bytes() == b"version two", "Latest version was not restored.")
                    wait(lambda: reported("restored", "recovery"), "Verified restore was not reported to the console.")
                    print("PASS: explicit recovery restores the latest version and reports its mode and verified restore.", flush=True)
            finally:
                worker.terminate()
                worker.wait(timeout=15)
    print("Local checks complete. The physical file-server service/SMB test is still required.")


if __name__ == "__main__":
    main()
