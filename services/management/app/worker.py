"""Background worker: removes expired approvals every 30 seconds. Run: python -m app.worker"""
import time

from . import audit, create_app
from .services import expire_grants, save_setting

app = create_app()
while True:
    try:
        with app.app_context():
            if app.config["ENABLE_DIRECTORY_WRITES"]:
                expire_grants()
            save_setting("_worker_heartbeat", audit.now())
    except Exception as exc:  # never die: log and try again
        print("worker error:", exc, flush=True)
    time.sleep(30)
